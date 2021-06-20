from datetime import datetime, timedelta
from io import IOBase
from typing import Dict, Generic, List, Optional, Tuple, TypeVar

from injector import inject, singleton

from .backupscheme import GenerationalScheme, OldestScheme, DeleteAfterUploadScheme
from backup.config import Config, Setting, CreateOptions
from backup.exceptions import DeleteMutlipleSnapshotsError, SimulatedError
from backup.util import GlobalInfo, Estimator, DataCache
from .snapshots import AbstractSnapshot, Snapshot
from .dummysnapshot import DummySnapshot
from backup.time import Time
from backup.worker import Trigger
from backup.logger import getLogger

logger = getLogger(__name__)

T = TypeVar('T')


class SnapshotSource(Trigger, Generic[T]):
    def __init__(self):
        super().__init__()
        pass

    def name(self) -> str:
        return "Unnamed"

    def title(self) -> str:
        return "Default"

    def enabled(self) -> bool:
        return True

    def needsConfiguration(self) -> bool:
        return not self.enabled()

    def upload(self) -> bool:
        return True

    def icon(self) -> str:
        return "sd_card"

    def freeSpace(self):
        return None

    async def create(self, options: CreateOptions) -> T:
        pass

    async def get(self) -> Dict[str, T]:
        pass

    async def delete(self, snapshot: T):
        pass

    async def ignore(self, snapshot: T, ignore: bool):
        pass

    async def save(self, snapshot: AbstractSnapshot, bytes: IOBase) -> T:
        pass

    async def read(self, snapshot: T) -> IOBase:
        pass

    async def retain(self, snapshot: T, retain: bool) -> None:
        pass

    def maxCount(self) -> None:
        return 0

    def postSync(self) -> None:
        return

    # Gets called after reading state but before any changes are made
    # to check for additional errors.
    def checkBeforeChanges(self) -> None:
        pass


class SnapshotDestination(SnapshotSource):
    def isWorking(self):
        return False


@singleton
class Model():
    @inject
    def __init__(self, config: Config, time: Time, source: SnapshotSource, dest: SnapshotDestination, info: GlobalInfo, estimator: Estimator, data_cache: DataCache):
        self.config: Config = config
        self.time = time
        self.source: SnapshotSource = source
        self.dest: SnapshotDestination = dest
        self.reinitialize()
        self.snapshots: Dict[str, Snapshot] = {}
        self.firstSync = True
        self.info = info
        self.simulate_error = None
        self.estimator = estimator
        self.waiting_for_startup = False
        self.ignore_startup_delay = False
        self._data_cache = data_cache

    def enabled(self):
        if self.source.needsConfiguration():
            return False
        if self.dest.needsConfiguration():
            return False
        return True

    def allSources(self):
        return [self.source, self.dest]

    def reinitialize(self):
        self._time_of_day: Optional[Tuple[int, int]] = self._parseTimeOfDay()

        # SOMEDAY: this should be cached in config and regenerated on config updates, not here
        self.generational_config = self.config.getGenerationalConfig()

    def getTimeOfDay(self):
        return self._time_of_day

    def _nextSnapshot(self, now: datetime, last_snapshot: Optional[datetime]) -> Optional[datetime]:
        timeofDay = self.getTimeOfDay()
        if self.config.get(Setting.DAYS_BETWEEN_SNAPSHOTS) <= 0:
            next = None
        elif self.dest.needsConfiguration():
            next = None
        elif not last_snapshot:
            next = now - timedelta(minutes=1)
        elif not timeofDay:
            next = last_snapshot + timedelta(days=self.config.get(Setting.DAYS_BETWEEN_SNAPSHOTS))
        else:
            newest_local: datetime = self.time.toLocal(last_snapshot)
            time_that_day_local = datetime(newest_local.year, newest_local.month,
                                           newest_local.day, timeofDay[0], timeofDay[1], tzinfo=self.time.local_tz)
            if newest_local < time_that_day_local:
                # Latest snapshot is before the snapshot time for that day
                next = self.time.toUtc(time_that_day_local)
            else:
                # return the next snapshot after the delta
                next = self.time.toUtc(
                    time_that_day_local + timedelta(days=self.config.get(Setting.DAYS_BETWEEN_SNAPSHOTS)))

        # Don't snapshot X minutes after startup, since that can put an unreasonable amount of strain on
        # system just booting up.
        if next is not None and next < now and now < self.info.snapshotCooldownTime() and not self.ignore_startup_delay:
            self.waiting_for_startup = True
            return self.info.snapshotCooldownTime()
        else:
            self.waiting_for_startup = False
            return next

    def nextSnapshot(self, now: datetime):
        latest = max(filter(lambda s: not s.ignore(), self.snapshots.values()),
                     default=None, key=lambda s: s.date())
        if latest:
            latest = latest.date()
        return self._nextSnapshot(now, latest)

    async def sync(self, now: datetime):
        if self.simulate_error is not None:
            if self.simulate_error.startswith("test"):
                raise Exception(self.simulate_error)
            else:
                raise SimulatedError(self.simulate_error)
        await self._syncSnapshots([self.source, self.dest])

        self.source.checkBeforeChanges()
        self.dest.checkBeforeChanges()

        if not self.dest.needsConfiguration():
            if self.source.enabled():
                await self._purge(self.source)
            if self.dest.enabled():
                await self._purge(self.dest)

        self._handleSnapshotDetails()
        next_snapshot = self.nextSnapshot(now)
        if next_snapshot and now >= next_snapshot and self.source.enabled() and not self.dest.needsConfiguration():
            if self.config.get(Setting.DELETE_BEFORE_NEW_SNAPSHOT):
                await self._purge(self.source, pre_purge=True)
            await self.createSnapshot(CreateOptions(now, self.config.get(Setting.SNAPSHOT_NAME)))
            await self._purge(self.source)
            self._handleSnapshotDetails()

        if self.dest.enabled() and self.dest.upload():
            # get the snapshots we should upload
            uploads = []
            for snapshot in self.snapshots.values():
                if snapshot.getSource(self.source.name()) is not None and snapshot.getSource(self.source.name()).uploadable() and snapshot.getSource(self.dest.name()) is None and not snapshot.ignore():
                    uploads.append(snapshot)
            uploads.sort(key=lambda s: s.date())
            uploads.reverse()
            for upload in uploads:
                # only upload if doing so won't result in it being deleted next
                dummy = DummySnapshot(
                    "", upload.date(), self.dest.name(), "dummy_slug_name")
                proposed = list(self.snapshots.values())
                proposed.append(dummy)
                if self._nextPurge(self.dest, proposed) != dummy:
                    if self.config.get(Setting.DELETE_BEFORE_NEW_SNAPSHOT):
                        await self._purge(self.dest, pre_purge=True)
                    upload.addSource(await self.dest.save(upload, await self.source.read(upload)))
                    await self._purge(self.dest)
                    self._handleSnapshotDetails()
                else:
                    break
            if self.config.get(Setting.DELETE_AFTER_UPLOAD):
                await self._purge(self.source)
        self._handleSnapshotDetails()
        self.source.postSync()
        self.dest.postSync()
        self._data_cache.saveIfDirty()

    def isWorkingThroughUpload(self):
        return self.dest.isWorking()

    async def createSnapshot(self, options):
        if not self.source.enabled():
            return

        self.estimator.refresh()
        self.estimator.checkSpace(list(self.snapshots.values()))
        created = await self.source.create(options)
        snapshot = Snapshot(created)
        self.snapshots[snapshot.slug()] = snapshot

    async def deleteSnapshot(self, snapshot, source):
        if not snapshot.getSource(source.name()):
            return
        slug = snapshot.slug()
        await source.delete(snapshot)
        snapshot.removeSource(source.name())
        if snapshot.isDeleted():
            del self.snapshots[slug]

    def getNextPurges(self):
        purges = {}
        for source in [self.source, self.dest]:
            purges[source.name()] = self._nextPurge(
                source, self.snapshots.values(), findNext=True)
        return purges

    def _parseTimeOfDay(self) -> Optional[Tuple[int, int]]:
        from_config = self.config.get(Setting.SNAPSHOT_TIME_OF_DAY)
        if len(from_config) == 0:
            return None
        parts = from_config.split(":")
        if len(parts) != 2:
            return None
        try:
            hour: int = int(parts[0])
            minute: int = int(parts[1])
            if hour < 0 or minute < 0 or hour > 23 or minute > 59:
                return None
            return (hour, minute)
        except ValueError:
            # Parse error
            return None

    async def _syncSnapshots(self, sources: List[SnapshotSource]):
        for source in sources:
            if source.enabled():
                from_source: Dict[str, AbstractSnapshot] = await source.get()
            else:
                from_source: Dict[str, AbstractSnapshot] = {}
            for snapshot in from_source.values():
                if snapshot.slug() not in self.snapshots:
                    self.snapshots[snapshot.slug()] = Snapshot(snapshot)
                else:
                    self.snapshots[snapshot.slug()].addSource(snapshot)
            for snapshot in list(self.snapshots.values()):
                if snapshot.slug() not in from_source:
                    slug = snapshot.slug()
                    snapshot.removeSource(source.name())
                    if snapshot.isDeleted():
                        del self.snapshots[slug]
        self.firstSync = False

    def _buildDeleteScheme(self, source, findNext=False):
        count = source.maxCount()
        if findNext:
            count -= 1
        if source == self.source and self.config.get(Setting.DELETE_AFTER_UPLOAD):
            return DeleteAfterUploadScheme(source.name(), [self.dest.name()])
        elif self.generational_config:
            return GenerationalScheme(
                self.time, self.generational_config, count=count)
        else:
            return OldestScheme(count=count)

    def _buildNamingScheme(self):
        source = max(filter(SnapshotSource.enabled, self.allSources()), key=SnapshotSource.maxCount)
        return self._buildDeleteScheme(source)

    def _handleSnapshotDetails(self):
        self._buildNamingScheme().handleNaming(self.snapshots.values())

    def _nextPurge(self, source: SnapshotSource, snapshots, findNext=False):
        """
        Given a list of snapshots, decides if one should be purged.
        """
        if not source.enabled() or len(snapshots) == 0:
            return None
        if source.maxCount() == 0 and not self.config.get(Setting.DELETE_AFTER_UPLOAD):
            return None

        scheme = self._buildDeleteScheme(source, findNext=findNext)
        consider_purging = []
        for snapshot in snapshots:
            source_snapshot = snapshot.getSource(source.name())
            if source_snapshot is not None and source_snapshot.considerForPurge() and not snapshot.ignore():
                consider_purging.append(snapshot)
        if len(consider_purging) == 0:
            return None
        return scheme.getOldest(consider_purging)

    async def _purge(self, source: SnapshotSource, pre_purge=False):
        while True:
            purge = self._getPurgeList(source, pre_purge)
            if len(purge) <= 0:
                return
            if len(purge) > 1 and (self.config.get(Setting.CONFIRM_MULTIPLE_DELETES) and not self.info.isPermitMultipleDeletes()):
                raise DeleteMutlipleSnapshotsError(self._getPurgeStats())
            await self.deleteSnapshot(purge[0], source)

    def _getPurgeStats(self):
        ret = {}
        for source in [self.source, self.dest]:
            ret[source.name()] = len(self._getPurgeList(source))
        return ret

    def _getPurgeList(self, source: SnapshotSource, pre_purge=False):
        if not source.enabled():
            return []
        candidates = list(self.snapshots.values())
        purges = []
        while True:
            next_purge = self._nextPurge(source, candidates, findNext=pre_purge)
            if next_purge is None:
                return purges
            else:
                purges.append(next_purge)
                candidates.remove(next_purge)
