import asyncio
import aiohttp
from datetime import timedelta
from io import IOBase
from threading import Lock, Thread
from typing import Dict, List, Optional

from aiohttp.client_exceptions import ClientResponseError
from injector import inject, singleton

from backup.util import AsyncHttpGetter, GlobalInfo, Estimator, DataCache, KEY_LAST_SEEN, KEY_PENDING, KEY_NAME, KEY_CREATED, KEY_I_MADE_THIS, KEY_IGNORE
from ..config import Config, Setting, CreateOptions, Startable
from ..const import SOURCE_HA
from ..model import SnapshotSource, AbstractSnapshot, HASnapshot, Snapshot
from ..exceptions import (LogicError, SnapshotInProgress,
                          UploadFailed, ensureKey)
from .harequests import HaRequests
from .password import Password
from .snapshotname import SnapshotName
from ..time import Time
from ..logger import getLogger, StandardLogger
from backup.const import FOLDERS
from .addon_stopper import AddonStopper

logger: StandardLogger = getLogger(__name__)


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
            details=None)
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

    def considerForPurge(self) -> bool:
        return False

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

    def madeByTheAddon(self):
        return True


@singleton
class HaSource(SnapshotSource[HASnapshot], Startable):
    """
    Stores logic for interacting with the supervisor add-on API
    """
    @inject
    def __init__(self, config: Config, time: Time, ha: HaRequests, info: GlobalInfo, stopper: AddonStopper, estimator: Estimator, data_cache: DataCache):
        super().__init__()
        self.config: Config = config
        self._data_cache = data_cache
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
        self.stopper = stopper
        self.estimator = estimator
        self._addons = {}

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

    def icon(self) -> str:
        return "home-assistant"

    def name(self) -> str:
        return SOURCE_HA

    def title(self) -> str:
        return "Home Assistant"

    def maxCount(self) -> None:
        return self.config.get(Setting.MAX_SNAPSHOTS_IN_HASSIO)

    def enabled(self) -> bool:
        return True

    def freeSpace(self):
        return self.estimator.getBytesFree()

    async def create(self, options: CreateOptions) -> HASnapshot:
        # Make sure instance info is up-to-date, for the snapshot name
        await self._refreshInfo()

        # Set a default name if it was unspecified
        if options.name_template is None or len(options.name_template) == 0:
            options.name_template = self.config.get(Setting.SNAPSHOT_NAME)

        # Build the snapshot request json, get type, etc
        request, type_name, protected = self._buildSnapshotInfo(
            options)

        async with self._pending_snapshot_lock:
            # Check if a snapshot is already in progress
            if self.pending_snapshot:
                if not self.pending_snapshot.isFailed() and not self.pending_snapshot.isComplete():
                    logger.info("A snapshot was already in progress")
                    raise SnapshotInProgress()

            # try to stop addons
            await self.stopper.stopAddons(self.self_info['slug'])

            # Create the snapshot palceholder object
            self.pending_snapshot = PendingSnapshot(
                type_name, protected, options, request, self.config, self.time)
            logger.info("Requesting a new snapshot")
            self._pending_snapshot_task = asyncio.create_task(self._requestAsync(
                self.pending_snapshot), name="Pending Snapshot Requester")
            await asyncio.wait({self._pending_snapshot_task}, timeout=self.config.get(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS))
            # set up the pending snapshot info
            pending = self._data_cache.snapshot(KEY_PENDING)
            pending[KEY_NAME] = request['name']
            pending[KEY_CREATED] = options.when.isoformat()
            pending[KEY_LAST_SEEN] = self.time.now().isoformat()
            self._data_cache.makeDirty()
            self.pending_snapshot.raiseIfNeeded()
            if self.pending_snapshot.isComplete():
                # It completed while we waited, so just query the new snapshot
                ret = await self.harequests.snapshot(self.pending_snapshot.createdSlug())
                self.setDataCacheInfo(ret)
                self._data_cache.snapshot(ret.slug())[KEY_I_MADE_THIS] = True
                return ret
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

    async def stop(self):
        if self._pending_snapshot_task:
            self._pending_snapshot_task.cancel()
            await asyncio.wait([self._pending_snapshot_task])

    async def get(self) -> Dict[str, HASnapshot]:
        if not self._initialized:
            await self.init()
        else:
            # Always ensure the supervisor version is fresh
            # TODO: remove when we no longer support the "snapshot" query path
            self.super_info = await self.harequests.supervisorInfo()
        slugs = set()
        retained = []
        snapshots: Dict[str, HASnapshot] = {}
        query = await self.harequests.snapshots()

        # Different supervisor version use different names for the list of backups
        backup_list = []
        if 'snapshots' in query:
            backup_list = query['snapshots']
        if 'backups' in query:
            backup_list = query['backups']

        for snapshot in backup_list:
            slug = snapshot['slug']
            slugs.add(slug)
            item = await self.harequests.snapshot(slug)
            if slug in self.pending_options:
                item.setOptions(self.pending_options[slug])
            snapshots[slug] = item
            if item.retained():
                retained.append(item.slug())
            self.setDataCacheInfo(item)
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

    def setDataCacheInfo(self, snapshot: HASnapshot):
        if snapshot.slug() not in self._data_cache.snapshots:
            # its a new snapshot, so we need to create a record for it
            pending = self._data_cache.snapshots.get(KEY_PENDING, {})
            pending_created = self.time.parse(pending.get(KEY_CREATED, self.time.now().isoformat()))

            # If the snapshot has the same name as the one we created and it was created within a day
            # of the requested time, then assume the addon created it.
            self_created = snapshot.name() == pending.get(KEY_NAME, None) and abs((pending_created - snapshot.date()).total_seconds()) < timedelta(days=1).total_seconds()

            stored_snapshot = self._data_cache.snapshot(snapshot.slug())
            stored_snapshot[KEY_I_MADE_THIS] = self_created
            stored_snapshot[KEY_CREATED] = snapshot.date().isoformat()
            stored_snapshot[KEY_NAME] = snapshot.name()
            if self_created:
                # Remove the pending snapshot info from the cache so it doesn't get reused.
                del self._data_cache.snapshots[KEY_PENDING]
        # bump the last seen time
        self._data_cache.snapshot(snapshot.slug())[KEY_LAST_SEEN] = self.time.now().isoformat()
        self._data_cache.makeDirty()

    async def delete(self, snapshot: Snapshot):
        slug = self._validateSnapshot(snapshot).slug()
        logger.info("Deleting '{0}' from Home Assistant".format(snapshot.name()))
        await self.harequests.delete(slug)
        snapshot.removeSource(self.name())

    async def ignore(self, snapshot: Snapshot, ignore: bool):
        slug = self._validateSnapshot(snapshot).slug()
        logger.info("Updating ignore settings for '{0}'".format(snapshot.name()))
        self._data_cache.snapshot(slug)[KEY_IGNORE] = ignore
        self._data_cache.makeDirty()

    async def save(self, snapshot: Snapshot, source: AsyncHttpGetter) -> HASnapshot:
        logger.info("Downloading '{0}'".format(snapshot.name()))
        self._info.upload(0)
        resp = None
        try:
            snapshot.overrideStatus("Loading {0}%", source)
            snapshot.setUploadSource(self.title(), source)
            async with source:
                with aiohttp.MultipartWriter('mixed') as mpwriter:
                    mpwriter.append(source, {'CONTENT-TYPE': 'application/tar'})
                    resp = await self.harequests.upload(mpwriter)
            snapshot.clearStatus()
            snapshot.clearUploadSource()
        except Exception as e:
            logger.printException(e)
            snapshot.overrideStatus("Failed!")
            snapshot.uploadFailure(logger.formatException(e))
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

            self._addons = {}
            for addon in self.super_info['addons']:
                self._addons[addon.get('slug', "default")] = addon

            self._info.addDebugInfo("self_info", self.self_info)
            self._info.addDebugInfo("host_info", self.host_info)
            self._info.addDebugInfo("ha_info", self.ha_info)
            self._info.addDebugInfo("super_info", self.super_info)
        except Exception as e:
            logger.debug("Failed to connect to supervisor")
            logger.debug(logger.formatException(e))
            raise e

    def addonHasLogo(self, slug):
        return self._addons.get(slug, {}).get('logo', False)

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

    def getHomeAssistantUrl(self):
        if not self.isInitialized():
            return ""
        return self._haUrl()

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

    def postSync(self):
        self.stopper.allowRun()
        self.stopper.isSnapshotting(self.pending_snapshot is not None)

    async def _requestAsync(self, pending: PendingSnapshot, start=[]) -> None:
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
        finally:
            await self.stopper.startAddons()
            self.trigger()

    def _buildSnapshotInfo(self, options: CreateOptions):
        addons: List[str] = []
        for addon in self.super_info.get('addons', {}):
            addons.append(addon['slug'])
        request_info = {
            'addons': [],
            'folders': []
        }
        folders = list(map(lambda f: f['slug'], FOLDERS))
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
        return request_info, type_name, protected
