import os.path
import os
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

# Secodns to wait after starting a snapshot before we consider it successful.
SNAPSHOT_FASTFAIL_SECOND = 10

HEADERS = {"X-HASSIO-KEY": os.environ.get("HASSIO_TOKEN")}

HEADERS_HA = {'Authorization': 'Bearer ' + str(os.environ.get("HASSIO_TOKEN"))}

NOTIFICATION_ID = "backup_broken"


class SnapshotInProgress(KnownError):
    def __init__(self):
        super(SnapshotInProgress, self).__init__("A snapshot is already in progress")


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
        self.lock: Lock = Lock()

    def _getSnapshot(self) -> None:
        try:
            self.pending_snapshot_error = None
            now_local: datetime = datetime.now()
            now_utc: datetime = nowutc()
            backup_name: str = "Full Snapshot {0}-{1:02d}-{2:02d} {3:02d}:{4:02d}:{5:02d}".format(
                now_local.year,
                now_local.month,
                now_local.day,
                now_local.hour,
                now_local.minute,
                now_local.second)
            snapshot_url = "{0}snapshots/new/full".format(self.config.hassioBaseUrl())
            try:
                self.lock.acquire()
                self.pending_snapshot = Snapshot(None)
                self.pending_snapshot.setPending(backup_name, now_utc)
            finally:
                self.lock.release()
            return_info = self._postHassioData(snapshot_url, {'name': backup_name})
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
                    self.pending_snapshot_error = e
                    self.pending_snapshot = None
            finally:
                self.lock.release()

    def killPending(self) -> None:
        try:
            self.lock.acquire()
            self.pending_snapshot_error = None
            self.pending_snapshot = None
        finally:
            self.lock.release()

    def auth(self, user: str, password: str) -> None:
        self._postHassioData("{}auth".format(self.config.hassioBaseUrl()), {"username": user, "password": password})

    def newSnapshot(self) -> Snapshot:
        try:
            self.lock.acquire()
            if self.snapshot_thread is not None and self.snapshot_thread.is_alive():
                raise SnapshotInProgress()
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
                self.pending_snapshot.setPending("Pending Snapshot", nowutc())
                return self.pending_snapshot
            if self.pending_snapshot_error is not None:
                raise self.pending_snapshot_error  # pylint: disable-msg=E0702
            elif self.pending_snapshot is not None:
                return self.pending_snapshot
            else:
                raise KnownError("Unexpected circumstances, pending snapshot is null")
        finally:
            self.lock.release()

    def deleteSnapshot(self, snapshot: Snapshot) -> None:
        delete_url: str = "{0}snapshots/{1}/remove".format(self.config.hassioBaseUrl(), snapshot.slug())
        self._postHassioData(delete_url, {})
        snapshot.ha = None

    def readSnapshots(self) -> List[HASnapshot]:
        snapshots: List[HASnapshot] = []
        snapshot_list: Dict[str, List[Dict[str, Any]]] = self._getHassioData(self.config.hassioBaseUrl() + "snapshots")
        for snapshot in snapshot_list['snapshots']:
            snapshot_details: Dict[Any, Any] = self._getHassioData("{0}snapshots/{1}/info".format(self.config.hassioBaseUrl(), snapshot['slug']))
            snapshots.append(HASnapshot(snapshot_details))

        snapshots.sort(key=lambda x: x.date())
        return snapshots

    def readAddonInfo(self) -> Dict[str, Any]:
        return self._getHassioData(self.config.hassioBaseUrl() + "addons/self/info")

    def readHostInfo(self) -> Dict[str, Any]:
        return self._getHassioData(self.config.hassioBaseUrl() + "info")

    def downloadUrl(self, snapshot: Snapshot) -> str:
        return "{0}snapshots/{1}/download".format(self.config.hassioBaseUrl(), snapshot.slug())

    def _validateHassioReply(self, resp: Response) -> Dict[str, Any]:
        if not resp.ok:
            if resp.status_code == 400 and "snapshots/new/full" in resp.url:
                # Hass.io seems to return http 400 when snapshot is already in progress, which is
                # great because there is no way to differentiate it from a malformed error.
                raise SnapshotInProgress()
            self.debug("Hass.io responded with: {0} {1}".format(resp, resp.text))
            raise Exception('Request to Hassio failed, HTTP error: {0} Message: {1}'.format(resp, resp.text))
        details: Dict[str, Any] = resp.json()
        self.debug("Hassio said: ")
        self.debug(pformat(details))
        if "result" not in details or "data" not in details or details["result"] != "ok":
            if "result" in details:
                raise Exception("Hassio said: " + details["result"])
            else:
                raise Exception("Malformed response from Hassio: " + str(details))
        return details["data"]  # type: ignore

    def _getHassioData(self, url: str) -> Dict[str, Any]:
        self.debug("Making Hassio request: " + url)
        return self._validateHassioReply(requests.get(url, headers=HEADERS))

    def _postHassioData(self, url: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        self.debug("Making Hassio request: " + url)
        return self._validateHassioReply(requests.post(url, headers=HEADERS, json=json_data))

    def _postHaData(self, path: str, data: Dict[str, Any]) -> None:
        headers: Dict[str, str] = {}
        if len(self.config.haBearer()) > 0:
            headers = {'Authorization': 'Bearer ' + self.config.haBearer()}
        else:
            headers = HEADERS_HA
        try:
            self.debug("Making Ha request: " + self.config.haBaseUrl() + path)
            self.debug("With Data: {0}".format(data))
            requests.post(self.config.haBaseUrl() + path, headers=headers, json=data).raise_for_status()
        except Exception as e:
            self.error(formatException(e))

    def sendNotification(self, title: str, message: str) -> None:
        if not self.sendNotification():
            return
        data: Dict[str, str] = {
            "title": title,
            "message": message,
            "notification_id": NOTIFICATION_ID
        }
        self._postHaData("services/persistent_notification/create", data)

    def dismissNotification(self) -> None:
        if not self.sendNotification():
            return
        data: Dict[str, str] = {
            "notification_id": NOTIFICATION_ID
        }
        self._postHaData("services/persistent_notification/dismiss", data)

    def updateSnapshotStaleSensor(self, state: bool) -> None:
        if not self.updateSnapshotStaleSensor():
            return
        data: Dict[str, Any] = {
            "state": state,
            "attributes": {
                "friendly_name": "Snapshots Stale",
                "device_class": "problem"
            }
        }
        self._postHaData("states/binary_sensor.snapshots_stale", data)

    def updateSnapshotsSensor(self, state: str, snapshots: List[Snapshot]) -> None:
        if not self.config.enableSnapshotStateSensor():
            return
        data: Dict[str, Any] = {
            "state": state,
            "attributes": {
                "friendly_name": "Snapshot State",
                "last_snapshot": str(max(snapshots, key=lambda s: s.date(), default="")),  # type: ignore
                "spanshots_in_google_drive": len(list(filter(lambda s: s.isInDrive(), snapshots))),
                "spanshots_in_hassio": len(list(filter(lambda s: s.isInHA(), snapshots))),
                "snapshots": list(map(lambda s: {"name": s.name(), "date": str(s.date()), "state": s.status()}, snapshots))
            }
        }
        self._postHaData("states/sensor.snapshot_backup", data)
