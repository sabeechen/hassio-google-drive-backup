import os.path
import sys
import os
import json
import requests
import threading

from requests import Response
from pprint import pprint
from datetime import datetime
from time import sleep
from oauth2client.client import HttpAccessTokenRefreshError # type: ignore
from .snapshots import HASnapshot
from .snapshots import Snapshot
from .helpers import nowutc
from .helpers import formatException
from .knownerror import KnownError
from .config import Config
from typing import Optional, Any, List, Dict

# Secodns to wait after starting a snapshot before we consider it successful.
SNAPSHOT_FASTFAIL_SECOND = 10

HEADERS = {"X-HASSIO-KEY": os.environ.get("HASSIO_TOKEN")}

HEADERS_HA = {'Authorization': 'Bearer ' + str(os.environ.get("HASSIO_TOKEN"))}

NOTIFICATION_ID = "backup_broken"

class Hassio(object):
    """
    Stores logic for interacting with the Hass.io add-on API
    """
    def __init__(self, config: Config):
        self.config: Config = config
        self.snapshot_thread: threading.Thread = threading.Thread(target = self._getSnapshot)
        self.snapshot_thread.daemon = True
        self.pending_snapshot: Optional[Snapshot] = None
        self.pending_snapshot_error: Optional[Exception] = None
        self.lock: threading.Lock = threading.Lock()

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
            self.pending_snapshot = Snapshot(None)
            self.pending_snapshot.setPending(backup_name, now_utc)
            return_info = self._postHassioData(snapshot_url, {'name': backup_name})
            self.pending_snapshot.endPending(return_info['slug'])
        except Exception as e:
            try:
                self.lock.acquire()
                if self.pending_snapshot:
                    self.pending_snapshot.pendingFailed()
                    self.pending_snapshot_error = e
                    self.pending_snapshot = None
            finally:
                self.lock.release()

    def auth(self, user: str, password: str) -> None:
         self._postHassioData("{}auth".format(self.config.hassioBaseUrl()), {"username": user, "password": password})

    
    def newSnapshot(self) -> Snapshot:
        try:
            self.lock.acquire()
            if not self.snapshot_thread is None and self.snapshot_thread.is_alive():
                raise Exception("A snapshot is already in progress")
            self.snapshot_thread = threading.Thread(target = self._getSnapshot)
            self.snapshot_thread.start()
        finally:
            self.lock.release()
        self.snapshot_thread.join(timeout = SNAPSHOT_FASTFAIL_SECOND)
        try:
            self.lock.acquire()
            if not self.pending_snapshot_error is None:
                raise self.pending_snapshot_error # pylint: disable-msg=E0702
            elif not self.pending_snapshot is None:
                return self.pending_snapshot
            else:
                raise Exception("Unexpected circumstances, everything is null")
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

        snapshots.sort(key = lambda x : x.date())
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
                raise KnownError("A snapshot is already in progress")
            print("Hass.io responded with: {0} {1}".format(resp, resp.text))
            raise Exception('Request to Hassio failed, HTTP error: {0} Message: {1}'.format(resp, resp.text))
        details: Dict[str, Any] = resp.json()
        if self.config.verbose():
            print("Hassio said: " + str(details))
        if not "result" in details or not "data" in details or details["result"] != "ok":
            if "result" in details:
                raise Exception("Hassio said: " + details["result"])
            else:
                raise Exception("Malformed response from Hassio: " + str(details))
        return details["data"]  # type: ignore

    def _getHassioData(self, url: str) -> Dict[str, Any]:
        if self.config.verbose():
            print("Making Hassio request: " + url)
        return self._validateHassioReply(requests.get(url, headers=HEADERS))

    def _postHassioData(self, url: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        if self.config.verbose():
            print("Making Hassio request: " + url)
        return self._validateHassioReply(requests.post(url, headers=HEADERS, json = json_data))

    def _postHaData(self, path: str, data: Dict[str, Any]) -> None:
        headers: Dict[str, str] = {}
        if len(self.config.haBearer()) > 0:
            headers = {'Authorization': 'Bearer ' + self.config.haBearer()}
        else:
            headers = HEADERS_HA
        try:
            if self.config.verbose():
                print("Making Ha request: " + self.config.haBaseUrl() + path)
                print("With Data: {0}".format(data))
            requests.post(self.config.haBaseUrl() + path, headers=headers, json = data).raise_for_status()
        except Exception as e:
            print(formatException(e))


    def sendNotification(self, title: str, message: str) -> None:
        data: Dict[str, str] = {
            "title" : title,
            "message" : message,
            "notification_id" : NOTIFICATION_ID
        }
        self._postHaData("services/persistent_notification/create", data)

    def dismissNotification(self) -> None:
        data: Dict[str, str] = {
            "notification_id" : NOTIFICATION_ID
        }
        self._postHaData("services/persistent_notification/dismiss", data)

    def updateSnapshotStaleSensor(self, state: bool) -> None:
        data: Dict[str, Any] = {
            "state": state,
            "attributes":{
                "friendly_name":"Snapshots Stale",
                "device_class": "problem"
                }
        } 
        self._postHaData("states/binary_sensor.snapshots_stale", data)

    def updateSnapshotsSensor(self, state: str, snapshots : List[Snapshot]) -> None:
        data: Dict[str, Any] = {
            "state": state,
            "attributes": {
                "friendly_name":"Snapshot State",
                "last_snapshot": str(max(snapshots, key=lambda s:s.date(), default="")),  # type: ignore
                "spanshots_in_google_drive": len(list(filter(lambda s:s.isInDrive(), snapshots))),
                "spanshots_in_hassio": len(list(filter(lambda s:s.isInHA(), snapshots))),
                "snapshots": list(map(lambda s: {"name":s.name(), "date":str(s.date()), "state":s.status()}, snapshots))
            }
        }
        self._postHaData("states/sensor.snapshot_backup", data)


