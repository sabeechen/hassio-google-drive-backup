from .logbase import LogBase
from .trigger import Trigger
from .model import Model, CreateOptions
from .time import Time
from .config import Config
from .snapshots import Snapshot, AbstractSnapshot
from .exceptions import NoSnapshot, PleaseWait, LogicError, KnownError
from oauth2client.client import Credentials
from typing import List, Dict
from .globalinfo import GlobalInfo
from threading import Lock
from .helpers import formatException
from .haupdater import HaUpdater
from .backoff import Backoff
from datetime import timedelta
from .settings import Setting


class Coordinator(Trigger, LogBase):
    # SOMEDAY: would be nice to have a way to "cancel" sync at certain intervals.
    def __init__(self, model: Model, time: Time, config: Config, global_info: GlobalInfo, updater: HaUpdater = None):
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
        self._updater = updater
        self._backoff = Backoff(initial=0, base=10, max=60 * 60)
        self.trigger()

    def saveCreds(self, creds: Credentials):
        self._model.dest.saveCreds(creds)
        self._global_info.credsSaved()

    def name(self):
        return "Coordinator"

    def enabled(self) -> bool:
        return self._model.dest.enabled()

    def check(self) -> bool:
        if self._time.now() >= self.nextSyncAttempt():
            return True
        else:
            return super().check()

    def sync(self):
        self._withSoftLock(lambda: self._sync())

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
                scheduled += timedelta(seconds=self._config.get(Setting.MAX_SYNC_INTERVAL_SECONDS))
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
            source_info = {
                'snapshots': 0,
                'retained': 0,
                'deletable': 0,
                'name': source
            }
            for snapshot in self.snapshots():
                data: AbstractSnapshot = snapshot.getSource(source)
                if data is None:
                    continue
                source_info['snapshots'] += 1
                if data.retained():
                    source_info['retained'] += 1
                else:
                    source_info['deletable'] += 1
            info[source] = source_info
        return info

    def _sync(self):
        try:
            self.info("Syncing Snapshots")
            self._global_info.sync()
            self._buildModel().sync(self._time.now())
            self._updateFreshness()
            self._global_info.success()
            self._backoff.reset()
        except Exception as e:
            if isinstance(e, KnownError):
                self.error(e.message())
            else:
                self.error(formatException(e))
            self._global_info.failed(e)
            self._backoff.backoff(e)
            self.info("Another attempt to sync will be made in {0} seconds".format(self._backoff.peek()))
        self._updater.updateSnapshots(self.snapshots())

    def snapshots(self) -> List[Snapshot]:
        ret = list(self._model.snapshots.values())
        ret.sort(key=lambda s: s.date())
        return ret

    def uploadSnapshot(self, slug):
        self._withSoftLock(lambda: self._uploadSnapshot(slug))

    def _uploadSnapshot(self, slug):
        # TODO: prevent double snapshot upload with its own exception
        snapshot = self._ensureSnapshot(self._model.dest.name(), slug)
        snapshot_dest = snapshot.getSource(self._model.dest.name())
        snapshot_source = snapshot.getSource(self._model.source.name())
        if snapshot_source:
            raise LogicError("This snapshot already exists in Home Assistant")
        if not snapshot_dest:
            # Unreachable?
            raise LogicError("This snapshot isn't in Google Drive")
        created = self._model.source.save(snapshot, self._model.dest.read(snapshot))
        snapshot.addSource(created)
        self._updateFreshness()

    def startSnapshot(self, options: CreateOptions):
        return self._withSoftLock(lambda: self._startSnapshot(options))

    def _startSnapshot(self, options: CreateOptions):
        created = self._buildModel().source.create(options)
        snapshot = Snapshot(created)
        self._model.snapshots[snapshot.slug()] = snapshot
        self._updateFreshness()
        return snapshot

    def getSnapshot(self, slug):
        return self._ensureSnapshot(None, slug)

    def download(self, slug):
        snapshot = self._ensureSnapshot(None, slug)
        for source in self._sources.values():
            if not source.enabled():
                continue
            if snapshot.getSource(source.name()):
                return source.read(snapshot)
        raise NoSnapshot()

    def retain(self, sources: Dict[str, bool], slug: str):
        for source in sources:
            snapshot = self._ensureSnapshot(source, slug)
            self._ensureSource(source).retain(snapshot, sources[source])
        self._updateFreshness()

    def delete(self, sources, slug):
        self._withSoftLock(lambda: self._delete(sources, slug))

    def _delete(self, sources, slug):
        for source in sources:
            snapshot = self._ensureSnapshot(source, slug)
            self._ensureSource(source).delete(snapshot)
            if snapshot.isDeleted():
                del self._model.snapshots[slug]
        self._updateFreshness()

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

    def _withSoftLock(self, callable):
        if not self._lock.acquire(blocking=False):
            raise PleaseWait()
        try:
            return callable()
        finally:
            self._lock.release()
