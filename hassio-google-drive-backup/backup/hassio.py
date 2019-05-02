import requests
from requests import Response
from pprint import pformat
from datetime import datetime
from .snapshots import HASnapshot
from .snapshots import Snapshot
from .helpers import nowutc
from .helpers import formatException
from .knownerror import KnownError
from .config import Config
from .logbase import LogBase
from typing import Optional, Any, List, Dict
from threading import Lock, Thread

# Seconds to wait after starting a snapshot before we consider it successful.
SNAPSHOT_FASTFAIL_SECOND = 10
NOTIFICATION_ID = "backup_broken"


class SnapshotInProgress(KnownError):
    def __init__(self):
        super(SnapshotInProgress, self).__init__(
            "A snapshot is already in progress")


class Hassio(LogBase):
    """
    Stores logic for interacting with the Hass.io add-on API
    """

    def __init__(self, config: Config):
        self.config: Config = config
        self.snapshot_thread: Thread = Thread(target=self._getSnapshot)
        self.snapshot_thread.daemon = True
        self.pending_snapshot: Optional[Snapshot] = None
        self.pending_snapshot_error: Optional[Exception] = None
        self.self_info = None
        self.host_info = None
        self.ha_info = None
        self.lock: Lock = Lock()
        self.has_offline = False
        self._retain_drive = False
        self._retain_ha = False
        self._customName = self.config.snapshotName()

    def loadInfo(self) -> None:
        self.self_info = self.readAddonInfo()
        self.host_info = self.readHostInfo()
        self.ha_info = self.getHaInfo()
        self.config.setIngressInfo(self.host_info)

    def getIngressUrl(self):
        if self.config.useIngress():
            try:
                if self.ha_info['ssl']:
                    protocol = "https"
                else:
                    protocol = "http"
                return "{0}://{1}:{2}/hassio/ingress/{3}".format(protocol, self.host_info['hostname'], self.ha_info['port'], self.self_info['slug'])
            except KeyError:
                return "/"
        else:
            return "/"

    def _getSnapshot(self) -> None:
        try:
            self.pending_snapshot_error = None

            addon_info = self.readSupervisorInfo()['addons']
            addons: List[str] = []
            for addon in addon_info:
                addons.append(addon['slug'])

            # build the partial snapshot request.
            request_info = {
                'addons': [],
                'folders': []
            }
            isPartial = False
            folders = ["ssl", "share", "homeassistant", "addons/local"]
            for folder in folders:
                if folder not in self.config.excludeFolders():
                    request_info['folders'].append(folder)
                else:
                    isPartial = True

            for addon in addons:
                if addon not in self.config.excludeAddons():
                    request_info['addons'].append(addon)
                else:
                    isPartial = True
            if len(self.config.snapshotPassword()) > 0:
                request_info['password'] = self.config.snapshotPassword()

            if isPartial:
                snapshot_type = "Partial"
            else:
                del request_info['folders']
                del request_info['addons']
                snapshot_type = "Full"

            now_utc: datetime = nowutc()
            backup_name: str = self.getSnapshotName(snapshot_type, self._custom_name)

            request_info['name'] = backup_name

            try:
                self.lock.acquire()
                self.pending_snapshot = Snapshot(None)
                self.pending_snapshot.setPending(backup_name, now_utc, self._retain_drive, self._retain_ha)
            finally:
                self.lock.release()

            if isPartial:
                # partial snapshot
                url = "{0}snapshots/new/partial".format(
                    self.config.hassioBaseUrl())
                return_info = self._postHassioData(url, request_info)
            else:
                # full snapshot
                url = "{0}snapshots/new/full".format(
                    self.config.hassioBaseUrl())
                return_info = self._postHassioData(url, request_info)

            try:
                self.lock.acquire()
                if self.pending_snapshot:
                    self.pending_snapshot.endPending(return_info['slug'])
            finally:
                self.lock.release()
        except Exception as e:
            try:
                self.lock.acquire()
                if self.pending_snapshot:
                    self.pending_snapshot.pendingFailed()
                    self.pending_snapshot = None
                self.pending_snapshot_error = e
            finally:
                self.lock.release()

    def getSnapshotName(self, snapshot_type: str, template: str) -> str:
        now_local: datetime = datetime.now()
        template = template.replace("{type}", snapshot_type)
        template = template.replace("{year}", now_local.strftime("%Y"))
        template = template.replace("{year_short}", now_local.strftime("%y"))
        template = template.replace("{weekday}", now_local.strftime("%A"))
        template = template.replace("{weekday_short}", now_local.strftime("%a"))
        template = template.replace("{month}", now_local.strftime("%m"))
        template = template.replace("{month_long}", now_local.strftime("%B"))
        template = template.replace("{month_short}", now_local.strftime("%b"))
        template = template.replace("{ms}", now_local.strftime("%f"))
        template = template.replace("{day}", now_local.strftime("%d"))
        template = template.replace("{hr24}", now_local.strftime("%H"))
        template = template.replace("{hr12}", now_local.strftime("%I"))
        template = template.replace("{min}", now_local.strftime("%M"))
        template = template.replace("{sec}", now_local.strftime("%S"))
        template = template.replace("{ampm}", now_local.strftime("%p"))
        template = template.replace("{version_ha}", str(self.host_info.get('homeassistant', 'None')))
        template = template.replace("{version_hassos}", str(self.host_info.get('hassos', 'None')))
        template = template.replace("{version_super}", str(self.host_info.get('supervisor', 'None')))
        template = template.replace("{date}", now_local.strftime("%x"))
        template = template.replace("{time}", now_local.strftime("%X"))
        template = template.replace("{datetime}", now_local.strftime("%c"))
        template = template.replace("{isotime}", now_local.isoformat())
        return template

    def killPending(self) -> None:
        try:
            self.lock.acquire()
            self.pending_snapshot_error = None
            self.pending_snapshot = None
        finally:
            self.lock.release()

    def auth(self, user: str, password: str) -> None:
        self._postHassioData("{}auth".format(self.config.hassioBaseUrl()), {
                             "username": user, "password": password})

    def newSnapshot(self, retain_drive=False, retain_ha=False, custom_name=None) -> Snapshot:
        try:
            self.lock.acquire()
            if self.snapshot_thread is not None and self.snapshot_thread.is_alive():
                raise SnapshotInProgress()
            self._retain_drive = retain_drive
            self._retain_ha = retain_ha
            if custom_name and len(custom_name) > 0:
                self._custom_name = custom_name
            else:
                self._custom_name = self.config.snapshotName()
            self.snapshot_thread = Thread(target=self._getSnapshot)
            self.snapshot_thread.start()
        finally:
            self.lock.release()
        self.snapshot_thread.join(timeout=SNAPSHOT_FASTFAIL_SECOND)
        try:
            self.lock.acquire()
            if self.pending_snapshot_error is not None and isinstance(self.pending_snapshot_error, SnapshotInProgress) and not self.pending_snapshot:
                # A snapshot was started "outside" of the add-on, so create a stub that we'll later associate with the pending snapshot once it shows up
                self.pending_snapshot = Snapshot(None)
                self.pending_snapshot.setPending("Pending Snapshot", nowutc(), False, False)
                return self.pending_snapshot
            if self.pending_snapshot_error is not None:
                raise self.pending_snapshot_error  # pylint: disable-msg=E0702
            elif self.pending_snapshot is not None:
                return self.pending_snapshot
            else:
                raise KnownError(
                    "Unexpected circumstances, pending snapshot is null")
        finally:
            self.lock.release()

    def uploadSnapshot(self, file, name=""):
        url: str = "{0}snapshots/new/upload".format(
            self.config.hassioBaseUrl())
        return self._postHassioData(url, file=file, name=name)

    def deleteSnapshot(self, snapshot: Snapshot) -> None:
        delete_url: str = "{0}snapshots/{1}/remove".format(
            self.config.hassioBaseUrl(), snapshot.slug())
        self._postHassioData(delete_url, {})
        snapshot.ha = None

    def get(self, slug):
        return HASnapshot(self._getHassioData("{0}snapshots/{1}/info".format(self.config.hassioBaseUrl(), slug)), self.config.isRetained(slug))

    def readSnapshots(self) -> List[HASnapshot]:
        snapshots: List[HASnapshot] = []
        snapshot_list: Dict[str, List[Dict[str, Any]]] = self._getHassioData(
            self.config.hassioBaseUrl() + "snapshots")
        for snapshot in snapshot_list['snapshots']:
            snapshots.append(self.get(snapshot['slug']))

        snapshots.sort(key=lambda x: x.date())
        return snapshots

    def getHaInfo(self):
        url = "{0}homeassistant/info".format(self.config.hassioBaseUrl())
        return self._getHassioData(url)

    def readAddonInfo(self) -> Dict[str, Any]:
        return self._getHassioData(self.config.hassioBaseUrl() + "addons/self/info")

    def readHassosInfo(self) -> Dict[str, Any]:
        return self._getHassioData(self.config.hassioBaseUrl() + "hassos/info")

    def readHostInfo(self) -> Dict[str, Any]:
        return self._getHassioData(self.config.hassioBaseUrl() + "info")

    def hassioget(self, url):
        return self._getHassioData(self.config.hassioBaseUrl() + url)

    def hassiopost(self, url, data):
        return self._postHassioData(self.config.hassioBaseUrl() + url, data)

    def refreshSnapshots(self):
        url = "{0}snapshots/reload".format(self.config.hassioBaseUrl())
        return self._postHassioData(url)

    def readSupervisorInfo(self):
        url = "{0}supervisor/info".format(self.config.hassioBaseUrl())
        return self._getHassioData(url)

    def restoreSnapshot(self, slug: str, password: str = None, snapshot: Snapshot = None) -> None:
        snapshot.restoring = True
        try:
            url: str = "{0}snapshots/{1}/restore/full".format(
                self.config.hassioBaseUrl(), slug)
            if password:
                self._postHassioData(url, {'password': password})
            else:
                self._postHassioData(url, {})
            snapshot.restoring = False
        except Exception:
            snapshot.restoring = None

    def downloadUrl(self, snapshot: Snapshot) -> str:
        return "{0}snapshots/{1}/download".format(self.config.hassioBaseUrl(), snapshot.slug())

    def _validateHassioReply(self, resp: Response) -> Dict[str, Any]:
        if not resp.ok:
            if resp.status_code == 400 and "snapshots/new/full" in resp.url:
                # Hass.io seems to return http 400 when snapshot is already in progress, which is
                # great because there is no way to differentiate it from a malformed error.
                raise SnapshotInProgress()
            self.debug(
                "Hass.io responded with: {0} {1}".format(resp, resp.text))
            raise Exception(
                'Request to Hassio failed, HTTP error: {0} Message: {1}'.format(resp, resp.text))
        details: Dict[str, Any] = resp.json()
        self.debug("Hassio said: ")
        self.debug(pformat(details))
        if "result" not in details or details["result"] != "ok":
            if "result" in details:
                raise Exception("Hassio said: " + details["result"])
            else:
                raise Exception(
                    "Malformed response from Hassio: " + str(details))

        if "data" not in details:
            return None

        return details["data"]

    def _getHassioData(self, url: str) -> Dict[str, Any]:
        self.debug("Making Hassio request: " + url)
        return self._validateHassioReply(requests.get(url, headers=self.config.getHassioHeaders()))

    def _postHassioData(self, url: str, json_data: Dict[str, Any] = {}, file=None, name="file.tar") -> Dict[str, Any]:
        self.debug("Making Hassio request: " + url)
        if not file:
            return self._validateHassioReply(requests.post(url, headers=self.config.getHassioHeaders(), json=json_data))
        else:
            return self._validateHassioReply(requests.post(url, headers=self.config.getHassioHeaders(), json=json_data, files={name: file}))

    def _postHaData(self, path: str, data: Dict[str, Any]) -> None:
        try:
            requests.post(self.config.haBaseUrl() + path, headers=self.config.getHaHeaders(), json=data).raise_for_status()
            if self.has_offline:
                self.info("Home Assistant came back.")
                self.has_offline = False
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 502:
                if not self.has_offline:
                    self.error("Unable to reach Home Assistant.  Is it restarting?")
                    self.has_offline = True
            else:
                self.error(formatException(e))
        except Exception as e:
            self.error(formatException(e))

    def sendNotification(self, title: str, message: str) -> None:
        if not self.config.notifyForStaleSnapshots():
            return
        data: Dict[str, str] = {
            "title": title,
            "message": message,
            "notification_id": NOTIFICATION_ID
        }
        self._postHaData("services/persistent_notification/create", data)

    def dismissNotification(self) -> None:
        if not self.config.notifyForStaleSnapshots():
            return
        data: Dict[str, str] = {
            "notification_id": NOTIFICATION_ID
        }
        self._postHaData("services/persistent_notification/dismiss", data)

    def updateSnapshotStaleSensor(self, state: bool) -> None:
        if not self.config.enableSnapshotStaleSensor():
            return
        data: Dict[str, Any] = {
            "state": state,
            "attributes": {
                "friendly_name": "Snapshots Stale",
                "device_class": "problem"
            }
        }
        self._postHaData("states/binary_sensor.snapshots_stale", data)

    def updateConfig(self, config) -> None:
        return self._postHassioData("{0}addons/self/options".format(self.config.hassioBaseUrl()), {'options': config})

    def updateSnapshotsSensor(self, state: str, snapshots: List[Snapshot]) -> None:
        if not self.config.enableSnapshotStateSensor():
            return

        last = ""
        if len(snapshots) > 0:
            last = max(snapshots, key=lambda s: s.date()).date().isoformat()

        data: Dict[str, Any] = {
            "state": state,
            "attributes": {
                "friendly_name": "Snapshot State",
                "last_snapshot": last,  # type: ignore
                "snapshots_in_google_drive": len(list(filter(lambda s: s.isInDrive(), snapshots))),
                "snapshots_in_hassio": len(list(filter(lambda s: s.isInHA(), snapshots))),
                "snapshots": list(map(lambda s: {"name": s.name(), "date": str(s.date().isoformat()), "state": s.status()}, snapshots))
            }
        }
        self._postHaData("states/sensor.snapshot_backup", data)
