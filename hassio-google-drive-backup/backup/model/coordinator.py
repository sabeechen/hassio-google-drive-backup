from asyncio import CancelledError, Task, create_task, wait, Event
from datetime import timedelta
from threading import Lock
from typing import Dict, List

from injector import inject, singleton

from backup.config import Config, Setting, CreateOptions
from backup.exceptions import (KnownError, LogicError, NoSnapshot, PleaseWait,
                               UserCancelledError)
from backup.util import GlobalInfo, Backoff, Estimator
from backup.time import Time
from backup.worker import Trigger
from backup.logger import getLogger
from backup.creds.creds import Creds
from .model import Model
from .snapshots import AbstractSnapshot, Snapshot, SOURCE_HA

logger = getLogger(__name__)


@singleton
class Coordinator(Trigger):
    @inject
    def __init__(self, model: Model, time: Time, config: Config, global_info: GlobalInfo, estimator: Estimator):
        super().__init__()
        self._model = model
        self._time = time
        self._config = config
        self._lock: Lock = Lock()
        self._global_info: GlobalInfo = global_info
        self._sources = {
            self._model.source.name(): self._model.source,
            self._model.dest.name(): self._model.dest
        }
        self._backoff = Backoff(initial=0, base=10, max=60 * 60)
        self._estimator = estimator
        self._busy = False
        self._sync_task: Task = None
        self._sync_start = Event()
        self._sync_wait = Event()
        self._sync_wait.set()
        self._global_info.triggerSnapshotCooldown(timedelta(minutes=self._config.get(Setting.SNAPSHOT_STARTUP_DELAY_MINUTES)))
        self.trigger()

    def saveCreds(self, creds: Creds):
        if not self._model.dest.enabled():
            # Since this is the first time saving credentials (eg the addon was just enabled).  Hold off on
            # automatic snapshots for a few minutes to give the user a little while to figure out whats going on.
            self._global_info.triggerSnapshotCooldown(timedelta(minutes=self._config.get(Setting.SNAPSHOT_STARTUP_DELAY_MINUTES)))

        self._model.dest.saveCreds(creds)
        self._global_info.credsSaved()

    def name(self):
        return "Coordinator"

    def enabled(self) -> bool:
        return self._model.enabled()

    def isWaitingForStartup(self):
        return self._model.waiting_for_startup

    def ignoreStartupDelay(self):
        self._model.ignore_startup_delay = True

    def check(self) -> bool:
        if self._time.now() >= self.nextSyncAttempt():
            self.reset()
            return True
        else:
            return super().check()

    async def sync(self):
        await self._withSoftLock(lambda: self._sync_wrapper())

    def isSyncing(self):
        task = self._sync_task
        return task is not None and not task.done()

    def isWorkingThroughUpload(self):
        return self.isSyncing() and self._model.isWorkingThroughUpload()

    async def waitForSyncToFinish(self):
        task = self._sync_task
        if task is not None:
            await task

    async def cancel(self):
        task = self._sync_task
        if task is not None and not task.done():
            task.cancel()
            await wait([task])

    def nextSyncAttempt(self):
        if self._global_info._last_error is not None:
            # we had an error last
            failure = self._global_info._last_failure_time
            if failure is None:
                return self._time.now() - timedelta(minutes=1)
            return failure + timedelta(seconds=self._backoff.peek())
        else:
            scheduled = self._global_info._last_success
            if scheduled is None:
                scheduled = self._time.now() - timedelta(minutes=1)
            else:
                scheduled += timedelta(seconds=self._config.get(
                    Setting.MAX_SYNC_INTERVAL_SECONDS))
            next_snapshot = self.nextSnapshotTime()
            if next_snapshot is None:
                return scheduled
            else:
                return min(self.nextSnapshotTime(), scheduled)

    def nextSnapshotTime(self):
        return self._buildModel().nextSnapshot(self._time.now())

    def buildSnapshotMetrics(self):
        info = {}
        for source in self._sources:
            source_class = self._sources[source]
            source_info = {
                'snapshots': 0,
                'retained': 0,
                'deletable': 0,
                'name': source,
                'title': source_class.title(),
                'latest': None,
                'max': source_class.maxCount(),
                'enabled': source_class.enabled(),
                'icon': source_class.icon(),
                'ignored': 0,
            }
            size = 0
            ignored_size = 0
            latest = None
            for snapshot in self.snapshots():
                data: AbstractSnapshot = snapshot.getSource(source)
                if data is None:
                    continue
                if data.ignore() and snapshot.ignore():
                    source_info['ignored'] += 1
                if snapshot.ignore():
                    ignored_size += snapshot.size()
                    continue
                source_info['snapshots'] += 1
                if data.retained():
                    source_info['retained'] += 1
                else:
                    source_info['deletable'] += 1
                if latest is None or data.date() > latest:
                    latest = data.date()
                size += int(data.sizeInt())
            if latest is not None:
                source_info['latest'] = self._time.asRfc3339String(latest)
            source_info['size'] = Estimator.asSizeString(size)
            source_info['ignored_size'] = Estimator.asSizeString(ignored_size)
            free_space = source_class.freeSpace()
            if free_space is not None:
                source_info['free_space'] = Estimator.asSizeString(free_space)
            info[source] = source_info
        return info

    async def _sync_wrapper(self):
        self._sync_task = create_task(
            self._sync(), name="Internal sync worker")
        await wait([self._sync_task])

    async def _sync(self):
        try:
            self._sync_start.set()
            await self._sync_wait.wait()
            logger.info("Syncing Snapshots")
            self._global_info.sync()
            self._estimator.refresh()
            await self._buildModel().sync(self._time.now())
            self._global_info.success()
            self._backoff.reset()
            self._global_info.setSkipSpaceCheckOnce(False)
        except BaseException as e:
            self.handleError(e)
        finally:
            self._updateFreshness()

    def handleError(self, e):
        if isinstance(e, CancelledError):
            e = UserCancelledError()
        if isinstance(e, KnownError):
            known: KnownError = e
            logger.error(known.message())
            if known.retrySoon():
                self._backoff.backoff(e)
            else:
                self._backoff.maxOut()
        else:
            logger.printException(e)
            self._backoff.backoff(e)
        self._global_info.failed(e)

        seconds = self._backoff.peek()
        if seconds < 1:
            text = "right now"
        elif seconds < 60:
            text = "in {0} seconds".format(seconds)
        elif seconds < 60 * 60:
            text = "in {0}(ish) minutes".format(int(seconds / 60))
        elif seconds == 60 * 60:
            text = "in an hour"
        else:
            text = "much later"

        logger.info("I'll try again {0}".format(text))

    def snapshots(self) -> List[Snapshot]:
        ret = list(self._model.snapshots.values())
        ret.sort(key=lambda s: s.date())
        return ret

    async def uploadSnapshot(self, slug):
        await self._withSoftLock(lambda: self._uploadSnapshot(slug))

    async def _uploadSnapshot(self, slug):
        snapshot = self._ensureSnapshot(self._model.dest.name(), slug)
        snapshot_dest = snapshot.getSource(self._model.dest.name())
        snapshot_source = snapshot.getSource(self._model.source.name())
        if snapshot_source:
            raise LogicError("This snapshot already exists in Home Assistant")
        if not snapshot_dest:
            # Unreachable?
            raise LogicError("This snapshot isn't in Google Drive")
        created = await self._model.source.save(snapshot, await self._model.dest.read(snapshot))
        snapshot.addSource(created)
        self._updateFreshness()

    async def startSnapshot(self, options: CreateOptions):
        return await self._withSoftLock(lambda: self._startSnapshot(options))

    async def _startSnapshot(self, options: CreateOptions):
        self._estimator.refresh()
        self._estimator.checkSpace(self.snapshots())
        created = await self._buildModel().source.create(options)
        snapshot = Snapshot(created)
        self._model.snapshots[snapshot.slug()] = snapshot
        self._updateFreshness()
        self._estimator.refresh()
        return snapshot

    def getSnapshot(self, slug):
        return self._ensureSnapshot(None, slug)

    async def download(self, slug):
        snapshot = self._ensureSnapshot(None, slug)
        for source in self._sources.values():
            if not source.enabled():
                continue
            if snapshot.getSource(source.name()):
                return await source.read(snapshot)
        raise NoSnapshot()

    async def retain(self, sources: Dict[str, bool], slug: str):
        for source in sources:
            snapshot = self._ensureSnapshot(source, slug)
            await self._ensureSource(source).retain(snapshot, sources[source])
        self._updateFreshness()

    async def delete(self, sources, slug):
        await self._withSoftLock(lambda: self._delete(sources, slug))

    async def ignore(self, slug: str, ignore: bool):
        await self._withSoftLock(lambda: self._ignore(slug, ignore))

    async def _delete(self, sources, slug):
        for source in sources:
            snapshot = self._ensureSnapshot(source, slug)
            await self._ensureSource(source).delete(snapshot)
            if snapshot.isDeleted():
                del self._model.snapshots[slug]
        self._updateFreshness()

    async def _ignore(self, slug: str, ignore: bool):
        snapshot = self._ensureSnapshot(SOURCE_HA, slug)
        await self._ensureSource(SOURCE_HA).ignore(snapshot, ignore)

    def _ensureSnapshot(self, source: str = None, slug=None) -> Snapshot:
        snapshot = self._buildModel().snapshots.get(slug)
        if not snapshot:
            raise NoSnapshot()
        if not source:
            return snapshot
        if not source:
            return snapshot
        if not snapshot.getSource(source):
            raise NoSnapshot()
        return snapshot

    def _ensureSource(self, source):
        ret = self._sources.get(source)
        if ret and ret.enabled():
            return ret
        raise LogicError()

    def _buildModel(self) -> Model:
        self._model.reinitialize()
        return self._model

    def _updateFreshness(self):
        purges = self._buildModel().getNextPurges()
        for snapshot in self._model.snapshots.values():
            for source in purges:
                if snapshot.getSource(source):
                    snapshot.updatePurge(source, snapshot == purges[source])

    async def _withSoftLock(self, callable):
        with self._lock:
            if self._busy:
                raise PleaseWait()
            self._busy = True
        try:
            return await callable()
        finally:
            with self._lock:
                self._busy = False
