import asyncio
from datetime import timedelta
from io import IOBase
from threading import Lock, Thread
from typing import Dict, List, Optional

from aiohttp.client_exceptions import ClientResponseError
from injector import inject, singleton

from ..util import AsyncHttpGetter, GlobalInfo
from ..config import Config, Setting, CreateOptions
from ..const import SOURCE_HA
from ..model import SnapshotSource, AbstractSnapshot, HASnapshot, Snapshot
from ..exceptions import (LogicError, SnapshotInProgress,
                          UploadFailed, ensureKey)
from .harequests import HaRequests
from .password import Password
from .snapshotname import SnapshotName
from ..time import Time
from ..logger import getLogger

logger = getLogger(__name__)


class PendingSnapshot(AbstractSnapshot):
    def __init__(self, snapshotType, protected, options: CreateOptions, request_info, config, time):
        super().__init__(
            name=request_info['name'],
            slug="pending",
            date=options.when,
            size="pending",
            source=SOURCE_HA,
            snapshotType=snapshotType,
            version="",
            protected=protected,
            retained=False,
            uploadable=False,
            details={})
        self._config = config
        self._failed = False
        self._complete = False
        self._exception = None
        self._failed_at = None
        self.setOptions(options)
        self._request_info = request_info
        self._completed_slug = None
        self._time = time
        self._pending_subverted = False
        self._start_time = time.now()

    def startTime(self):
        return self._start_time

    def failed(self, exception, time):
        self._failed = True
        self._exception = exception
        self._failed_at = time

    def getFailureTime(self):
        return self._failed_at

    def complete(self, slug):
        self._complete = True
        self._completed_slug = slug

    def setPendingUnknown(self):
        self._name = "Pending Snapshot"
        self._snapshotType = "unknown"
        self._protected = False
        self._pending_subverted = True

    def createdSlug(self):
        return self._completed_slug

    def isComplete(self):
        return self._complete

    def isFailed(self):
        return self._failed

    def status(self):
        if self._complete:
            return "Created"
        if self._failed:
            return "Failed!"
        return "Pending"

    def raiseIfNeeded(self):
        if self.isFailed():
            raise self._exception
        if self._pending_subverted:
            raise SnapshotInProgress()

    def isStale(self):
        if self._pending_subverted:
            delta = timedelta(seconds=self._config.get(
                Setting.SNAPSHOT_STALE_SECONDS))
            if self._time.now() > self.startTime() + delta:
                return True
        if not self.isFailed():
            return False
        delta = timedelta(seconds=self._config.get(
            Setting.FAILED_SNAPSHOT_TIMEOUT_SECONDS))
        staleTime = self.getFailureTime() + delta
        return self._time.now() >= staleTime


@singleton
class HaSource(SnapshotSource[HASnapshot]):
    """
    Stores logic for interacting with the supervisor add-on API
    """
    @inject
    def __init__(self, config: Config, time: Time, ha: HaRequests, info: GlobalInfo):
        super().__init__()
        self.config: Config = config
        self.snapshot_thread: Thread = None
        self.pending_snapshot_error: Optional[Exception] = None
        self.pending_snapshot_slug: Optional[str] = None
        self.self_info = None
        self.host_info = None
        self.ha_info = None
        self.super_info = None
        self.lock: Lock = Lock()
        self.time = time
        self.harequests = ha
        self.last_slugs = set()
        self.retained = []
        self.cached_retention = {}
        self._info = info
        self.pending_options = {}

        # This lock should be used for _ANYTHING_ that interacts with self._pending_snapshot
        self._pending_snapshot_lock = asyncio.Lock()
        self.pending_snapshot: Optional[PendingSnapshot] = None
        self._pending_snapshot_task = None
        self._initialized = False

    def isInitialized(self):
        return self._initialized

    def check(self) -> bool:
        pending = self.pending_snapshot
        if pending and pending.isStale():
            self.trigger()
        return super().check()

    def name(self) -> str:
        return SOURCE_HA

    def maxCount(self) -> None:
        return self.config.get(Setting.MAX_SNAPSHOTS_IN_HASSIO)

    def enabled(self) -> bool:
        return True

    async def create(self, options: CreateOptions) -> HASnapshot:
        # Make sure instance info is up-to-date, for the snapshot name
        await self._refreshInfo()

        # Set a default name if it was unspecified
        if options.name_template is None or len(options.name_template) == 0:
            options.name_template = self.config.get(Setting.SNAPSHOT_NAME)

        # Build the snapshot request json, get type, etc
        request, options, type_name, protected = self._buildSnapshotInfo(
            options)

        async with self._pending_snapshot_lock:
            # Check if a snapshot is already in progress
            if self.pending_snapshot:
                if not self.pending_snapshot.isFailed() and not self.pending_snapshot.isComplete():
                    logger.info("A snapshot was already in progress")
                    raise SnapshotInProgress()

            # Create the snapshot palceholder object
            self.pending_snapshot = PendingSnapshot(
                type_name, protected, options, request, self.config, self.time)
            logger.info("Requesting a new snapshot")
            self._pending_snapshot_task = asyncio.create_task(self._requestAsync(
                self.pending_snapshot), name="Pending Snapshot Requester")
            await asyncio.wait({self._pending_snapshot_task}, timeout=self.config.get(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS))
            self.pending_snapshot.raiseIfNeeded()
            if self.pending_snapshot.isComplete():
                # It completed while we waited, so just query the new snapshot
                return await self.harequests.snapshot(self.pending_snapshot.createdSlug())
            else:
                return self.pending_snapshot

    def _isHttp400(self, e):
        if isinstance(e, ClientResponseError):
            return e.status == 400
        return False

    async def start(self):
        try:
            await self.init()
        except Exception:
            pass

    async def get(self) -> Dict[str, HASnapshot]:
        if not self._initialized:
            await self.init()
        slugs = set()
        retained = []
        snapshots: Dict[str, HASnapshot] = {}
        query = await self.harequests.snapshots()
        for snapshot in query['snapshots']:
            slug = snapshot['slug']
            slugs.add(slug)
            item = await self.harequests.snapshot(slug)
            if slug in self.pending_options:
                item.setOptions(self.pending_options[slug])
            snapshots[slug] = item
            if item.retained():
                retained.append(item.slug())
        if self.pending_snapshot:
            async with self._pending_snapshot_lock:
                if self.pending_snapshot:
                    if self.pending_snapshot.isStale():
                        # The snapshot is stale, so just let it die.
                        self._killPending()
                    elif self.pending_snapshot.isComplete() and self.pending_snapshot.createdSlug() in snapshots:
                        # Copy over options if we got the requested snapshot.
                        snapshots[self.pending_snapshot.createdSlug()].setOptions(
                            self.pending_snapshot.getOptions())
                        self._killPending()
                    elif self.last_slugs.symmetric_difference(slugs).intersection(slugs):
                        # New snapshot added, ignore pending snapshot.
                        self._killPending()
            if self.pending_snapshot:
                snapshots[self.pending_snapshot.slug()] = self.pending_snapshot
        for slug in retained:
            if not self.config.isRetained(slug):
                self.config.setRetained(slug, False)
        self.last_slugs = slugs
        return snapshots

    async def delete(self, snapshot: Snapshot):
        slug = self._validateSnapshot(snapshot).slug()
        logger.info("Deleting '{0}' from Home Assistant".format(snapshot.name()))
        await self.harequests.delete(slug)
        snapshot.removeSource(self.name())

    async def save(self, snapshot: Snapshot, source: AsyncHttpGetter) -> HASnapshot:
        logger.info("Downloading '{0}'".format(snapshot.name()))
        self._info.upload(0)
        resp = None
        try:
            snapshot.overrideStatus("Downloading {0}%", source)
            resp = await self.harequests.upload(source)
            snapshot.clearStatus()
        except Exception as e:
            logger.printException(e)
            snapshot.overrideStatus("Failed!")
        if resp and 'slug' in resp and resp['slug'] == snapshot.slug():
            self.config.setRetained(snapshot.slug(), True)
            return await self.harequests.snapshot(snapshot.slug())
        else:
            raise UploadFailed()

    async def read(self, snapshot: Snapshot) -> IOBase:
        item = self._validateSnapshot(snapshot)
        return await self.harequests.download(item.slug())

    async def retain(self, snapshot: Snapshot, retain: bool) -> None:
        item: HASnapshot = self._validateSnapshot(snapshot)
        item._retained = retain
        self.config.setRetained(snapshot.slug(), retain)

    async def init(self):
        await self._refreshInfo()
        self._initialized = True

    async def refresh(self):
        await self._refreshInfo()

    async def _refreshInfo(self) -> None:
        try:
            self.self_info = await self.harequests.selfInfo()
            self.host_info = await self.harequests.info()
            self.ha_info = await self.harequests.haInfo()
            self.super_info = await self.harequests.supervisorInfo()
            self.config.update(
                ensureKey("options", self.self_info, "addon metdata"))

            self._info.ha_port = ensureKey(
                "port", self.ha_info, "Home Assistant metadata")
            self._info.ha_ssl = ensureKey(
                "ssl", self.ha_info, "Home Assistant metadata")
            self._info.addons = ensureKey(
                "addons", self.super_info, "Supervisor metadata")
            self._info.slug = ensureKey(
                "slug", self.self_info, "addon metdata")
            self._info.url = self.getAddonUrl()

            self._info.addDebugInfo("self_info", self.self_info)
            self._info.addDebugInfo("host_info", self.host_info)
            self._info.addDebugInfo("ha_info", self.ha_info)
            self._info.addDebugInfo("super_info", self.super_info)
        except Exception as e:
            logger.debug("Failed to connect to supervisor")
            logger.debug(logger.formatException(e))
            raise e

    def getAddonUrl(self):
        """
        Returns the relative path to the add-on, for the purpose of linking to the add-on page from within Home Assistant.
        """
        if self._info.slug is None:
            return ""
        return "/hassio/ingress/" + str(self._info.slug)

    def getHostInfo(self):
        if not self.isInitialized():
            return {}
        return self.host_info

    def getFullAddonUrl(self):
        if not self.isInitialized():
            return ""
        return self._haUrl() + "hassio/ingress/" + str(self._info.slug)

    def getFullRestoreLink(self):
        if not self.isInitialized():
            return ""
        return self._haUrl() + "hassio/snapshots"

    def _haUrl(self):
        if self._info.ha_ssl:
            protocol = "https://"
        else:
            protocol = "http://"
        return "".join([protocol, "{host}:", str(self._info.ha_port), "/"])

    def _validateSnapshot(self, snapshot) -> HASnapshot:
        item: HASnapshot = snapshot.getSource(self.name())
        if not item:
            raise LogicError(
                "Requested to do something with a snapshot from Home Assistant, but the snapshot has no Home Assistant source")
        return item

    def _killPending(self):
        self.pending_snapshot = None
        if self._pending_snapshot_task and not self._pending_snapshot_task.done():
            self._pending_snapshot_task.cancel()

    async def _requestAsync(self, pending: PendingSnapshot) -> None:
        try:
            result = await asyncio.wait_for(self.harequests.createSnapshot(pending._request_info), timeout=self.config.get(Setting.PENDING_SNAPSHOT_TIMEOUT_SECONDS))
            slug = ensureKey(
                "slug", result, "supervisor's create snapshot response")
            pending.complete(slug)
            self.config.setRetained(
                slug, pending.getOptions().retain_sources.get(self.name(), False))
            logger.info("Snapshot finished")
        except Exception as e:
            if self._isHttp400(e):
                logger.warning("A snapshot was already in progress")
                pending.setPendingUnknown()
            else:
                logger.error("Snapshot failed:")
                logger.printException(e)
                pending.failed(e, self.time.now())
        self.trigger()

    def _buildSnapshotInfo(self, options: CreateOptions):
        addons: List[str] = []
        for addon in self.super_info.get('addons', {}):
            addons.append(addon['slug'])
        request_info = {
            'addons': [],
            'folders': []
        }
        folders = ["ssl", "share", "homeassistant", "addons/local"]
        type_name = "Full"
        for folder in folders:
            if folder not in self.config.get(Setting.EXCLUDE_FOLDERS):
                request_info['folders'].append(folder)
            else:
                type_name = "Partial"
        for addon in addons:
            if addon not in self.config.get(Setting.EXCLUDE_ADDONS):
                request_info['addons'].append(addon)
            else:
                type_name = "Partial"
        if type_name == "Full":
            del request_info['addons']
            del request_info['folders']
        protected = False
        password = Password(self.config).resolve()
        if password:
            request_info['password'] = password
        name = SnapshotName().resolve(type_name, options.name_template,
                                      self.time.toLocal(options.when), self.host_info)
        request_info['name'] = name
        return request_info, options, type_name, protected
