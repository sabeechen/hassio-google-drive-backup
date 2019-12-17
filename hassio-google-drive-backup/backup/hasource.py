import os.path
from .snapshots import HASnapshot, Snapshot, AbstractSnapshot
from .config import Config
from .time import Time
from .model import SnapshotSource, CreateOptions
from typing import Optional, List, Dict
from threading import Lock, Thread
from .harequests import HaRequests
from .exceptions import LogicError
from .helpers import formatException, touch
from .exceptions import SnapshotInProgress, UploadFailed, ensureKey
from .globalinfo import GlobalInfo
from .const import SOURCE_HA
from datetime import timedelta
from io import IOBase
from requests import HTTPError
from .settings import Setting
from .password import Password
from .snapshotname import SnapshotName


class PendingSnapshot(AbstractSnapshot):
    def __init__(self, name, date, snapshotType, protected, start_time):
        super().__init__(
            name=name,
            slug="pending",
            date=date,
            size="pending",
            source=SOURCE_HA,
            snapshotType=snapshotType,
            version="",
            protected=protected,
            retained=False,
            uploadable=False,
            details={})
        self._failed = False
        self._complete = False
        self._exception = None
        self._start_time = start_time
        self._failed_at = None

    def startTime(self):
        return self._start_time

    def failed(self, exception, time):
        self._failed = True
        self._exception = exception
        self._failed_at = time

    def getFailureTime(self):
        return self._failed_at

    def complete(self):
        self._complete = True

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


class HaSource(SnapshotSource[HASnapshot]):
    """
    Stores logic for interacting with the Hass.io add-on API
    """
    def __init__(self, config: Config, time: Time, ha: HaRequests, info: GlobalInfo):
        super().__init__()
        self.config: Config = config
        self.snapshot_thread: Thread = None
        self.pending_snapshot: Optional[PendingSnapshot] = None
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
        self._temporary_extra_server = False

    def runTemporaryServer(self):
        return self._temporary_extra_server

    def check(self) -> bool:
        # determine if the pending snapshot has timed out, but not if we're still waiting for the request
        pending = self.pending_snapshot
        if pending is not None:
            if self.snapshot_thread is None or not self.snapshot_thread.is_alive():
                if self.time.now() > pending.startTime() + timedelta(seconds=self.config.get(Setting.PENDING_SNAPSHOT_TIMEOUT_SECONDS)):
                    self._killPending()
                    self.trigger()
            if pending.isFailed() and self.time.now() >= pending.getFailureTime() + timedelta(seconds=self.config.get(Setting.FAILED_SNAPSHOT_TIMEOUT_SECONDS)):
                self._killPending()
                self.trigger()
            if pending.isComplete():
                self._killPending()
                self.trigger()
        return super().check()

    def name(self) -> str:
        return SOURCE_HA

    def maxCount(self) -> None:
        return self.config.get(Setting.MAX_SNAPSHOTS_IN_HASSIO)

    def enabled(self) -> bool:
        return True

    def create(self, options: CreateOptions) -> HASnapshot:
        self._refreshInfo()
        if options.name_template is None or len(options.name_template) == 0:
            options.name_template = self.config.get(Setting.SNAPSHOT_NAME)
        self.info("Requesting a new snapshot")
        data = self._buildSnapshotInfo(options)
        with self.lock:
            if self.snapshot_thread is not None and self.snapshot_thread.is_alive():
                self.info("A snapshot was already in progress")
                raise SnapshotInProgress()
            if self.pending_snapshot is not None:
                if not self.pending_snapshot.isFailed() and not self.pending_snapshot.isComplete():
                    raise SnapshotInProgress()
            self.pending_snapshot_error = None
            self.pending_snapshot_slug = None
            self.pending_snapshot = None
            self.snapshot_thread = Thread(target=self._requestSnapshot, args=(data), name="Snapshot Request Thread")
            self.snapshot_thread.setDaemon(True)
            self.snapshot_thread.start()

        self.snapshot_thread.join(timeout=self.config.get(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS))

        with self.lock:
            if self.pending_snapshot_error is not None:
                if self._isHttp400(self.pending_snapshot_error):
                    self.info("A snapshot was already in progress (created outside this addon)")
                    # A snapshot was started "outside" of the add-on, so create a stub that we'll later associate with the pending snapshot once it shows up
                    self.pending_snapshot = PendingSnapshot("Pending Snapshot", options.when, "Unknown", False, self.time.now())
                    raise SnapshotInProgress()
                else:
                    raise self.pending_snapshot_error
            elif self.pending_snapshot_slug:
                # The snapshot completed while we waited, so now we should be able to just read it.
                snapshot = self.harequests.snapshot(self.pending_snapshot_slug)
                snapshot.setOptions(options)
                return snapshot
            else:
                self.pending_snapshot = PendingSnapshot(data[0]['name'], options.when, data[2], data[3], self.time.now())
                self.pending_snapshot.setOptions(options)
            return self.pending_snapshot

    def _isHttp400(self, e):
        if not isinstance(e, HTTPError):
            return False
        return e.response.status_code == 400

    def get(self) -> Dict[str, HASnapshot]:
        # TODO: refresh settings here instead of during snapshot creation.  maybe cache it with a timeout
        slugs = set()
        retained = []
        snapshots: Dict[str, HASnapshot] = {}
        for snapshot in self.harequests.snapshots()['snapshots']:
            slug = snapshot['slug']
            slugs.add(slug)
            item = self.harequests.snapshot(slug)
            if slug in self.pending_options:
                item.setOptions(self.pending_options[slug])
            snapshots[slug] = item
            if item.retained():
                retained.append(item.slug())
        if len(slugs - self.last_slugs) > 0:
            # At least one item was added since the last query
            self.last_slugs = slugs
            if self.pending_snapshot is not None:
                self._killPending()
        if self.pending_snapshot:
            snapshots[self.pending_snapshot.slug()] = self.pending_snapshot
        for slug in retained:
            if not self.config.isRetained(slug):
                self.config.setRetained(slug, False)
        return snapshots

    def delete(self, snapshot: Snapshot):
        slug = self._validateSnapshot(snapshot).slug()
        self.info("Deleting '{0}' from Home Assistant".format(snapshot.name()))
        self.harequests.delete(slug)
        snapshot.removeSource(self.name())

    def save(self, snapshot: Snapshot, stream: IOBase) -> HASnapshot:
        self.info("Downloading '{0}'".format(snapshot.name()))
        self._info.upload(0)
        resp = None
        try:
            snapshot.overrideStatus("Downloading {0}%", stream)
            resp = self.harequests.upload(stream)
        except Exception as e:
            self.error(formatException(e))
        snapshot.clearStatus()
        if resp and 'slug' in resp and resp['slug'] == snapshot.slug():
            self.config.setRetained(snapshot.slug(), True)
            return self.harequests.snapshot(snapshot.slug())
        else:
            raise UploadFailed()

    def read(self, snapshot: Snapshot) -> IOBase:
        item = self._validateSnapshot(snapshot)
        return self.harequests.download(item.slug())

    def retain(self, snapshot: Snapshot, retain: bool) -> None:
        item: HASnapshot = self._validateSnapshot(snapshot)
        item._retained = retain
        self.config.setRetained(snapshot.slug(), retain)

    def init(self):
        self._refreshInfo()

        # check if the upgrade file is present.
        self._temporary_extra_server = False
        if not os.path.exists(self.config.get(Setting.INGRESS_TOKEN_FILE_PATH)):
            # No upgrade file, so check if drive creds are saved.
            if os.path.exists(self.config.get(Setting.CREDENTIALS_FILE_PATH)):
                # its an upgrade, so add the extra server option.
                self._temporary_extra_server = True
            else:
                # Its a new install, write the upgrde file so we never check again.
                touch(self.config.get(Setting.INGRESS_TOKEN_FILE_PATH))

    def refresh(self):
        self._refreshInfo()

    def _refreshInfo(self) -> None:
        self.self_info = self.harequests.selfInfo()
        self.host_info = self.harequests.info()
        self.ha_info = self.harequests.haInfo()
        self.super_info = self.harequests.supervisorInfo()
        self.config.update(ensureKey("options", self.self_info, "addon metdata"))

        self._info.ha_port = ensureKey("port", self.ha_info, "Home Assistant metadata")
        self._info.ha_ssl = ensureKey("ssl", self.ha_info, "Home Assistant metadata")
        self._info.addons = ensureKey("addons", self.super_info, "Supervisor metadata")
        self._info.slug = ensureKey("slug", self.self_info, "addon metdata")
        self._info.url = self.getAddonUrl()

        self._info.addDebugInfo("self_info", self.self_info)
        self._info.addDebugInfo("host_info", self.host_info)
        self._info.addDebugInfo("ha_info", self.ha_info)
        self._info.addDebugInfo("super_info", self.super_info)

    def getAddonUrl(self):
        """
        Returns the relative path to the add-on, for the purpose of linking to the add-on page from within Home Assistant.
        """
        return "/hassio/ingress/" + str(self._info.slug)

    def getFullAddonUrl(self):
        return self._haUrl() + "hassio/ingress/" + str(self._info.slug)

    def getFullRestoreLink(self):
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
            raise LogicError("Requested to do something with a snapshot from Home Assistant, but the snapshot has no Home Assistant source")
        return item

    def _requestSnapshot(self, *args) -> None:
        data = args
        options: CreateOptions = data[1]
        try:
            self.harequests.eventSnapshotStart(data[0]['name'], options.when)
            slug = ensureKey("slug", self.harequests.createSnapshot(data[0]), "Hass.io's create snapshot response")
            with self.lock:
                self.pending_snapshot_slug = slug
                self.config.setRetained(slug, options.retain_sources.get(self.name(), False))
                self.pending_options[slug] = options
                if self.pending_snapshot:
                    self.pending_snapshot.complete()
                self.info("Snapshot finished")
            self.trigger()
            self.harequests.eventSnapshotEnd(data[0]['name'], options.when, True)
        except Exception as e:
            self.harequests.eventSnapshotEnd(data[0]['name'], options.when, False)
            with self.lock:
                if self.pending_snapshot:
                    self.pending_snapshot.failed(e, self.time.now())
                    if self._isHttp400(e):
                        self.warn("A snapshot was already in progress")
                    else:
                        self.error("Snapshot failed:")
                        self.error(formatException(e))
                self.pending_snapshot_error = e

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
        name = SnapshotName().resolve(type_name, options.name_template, self.time.toLocal(options.when), self.host_info)
        request_info['name'] = name
        return (request_info, options, type_name, protected)

    def _killPending(self) -> None:
        with self.lock:
            self.pending_snapshot_error = None
            self.pending_snapshot_slug = None
            self.pending_snapshot = None
