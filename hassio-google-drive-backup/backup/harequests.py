from requests import Response
from requests.exceptions import HTTPError
from .exceptions import HomeAssistantDeleteError
from .snapshots import HASnapshot
from .snapshots import Snapshot
from .config import Config
from .const import SOURCE_GOOGLE_DRIVE, SOURCE_HA
from .logbase import LogBase
from .seekablerequest import SeekableRequest
from typing import Any, List, Dict

NOTIFICATION_ID = "backup_broken"


class HaRequests(LogBase):
    """
    Stores logic for interacting with the Hass.io add-on API
    """
    def __init__(self, config: Config, client):
        self.config: Config = config
        self.cache = {}
        self._client = client

    def createSnapshot(self, info):
        if 'folders' in info or 'addons' in info:
            url = "{0}snapshots/new/partial".format(self.config.hassioBaseUrl())
        else:
            url = "{0}snapshots/new/full".format(self.config.hassioBaseUrl())
        return self._postHassioData(url, info)

    def auth(self, user: str, password: str) -> None:
        self._postHassioData("{}auth".format(self.config.hassioBaseUrl()), {"username": user, "password": password})

    def upload(self, stream):
        url: str = "{0}snapshots/new/upload".format(
            self.config.hassioBaseUrl())
        return self._postHassioData(url, data=stream)

    def delete(self, slug) -> None:
        delete_url: str = "{0}snapshots/{1}/remove".format(self.config.hassioBaseUrl(), slug)
        if slug in self.cache:
            del self.cache[slug]
        try:
            self._postHassioData(delete_url, {})
        except HTTPError as e:
            if e.response.status_code == 400:
                raise HomeAssistantDeleteError()
            raise e

    def snapshot(self, slug):
        if slug in self.cache:
            info = self.cache[slug]
        else:
            info = self._getHassioData("{0}snapshots/{1}/info".format(self.config.hassioBaseUrl(), slug))
            self.cache[slug] = info
        return HASnapshot(info, self.config.isRetained(slug))

    def snapshots(self):
        return self._getHassioData(self.config.hassioBaseUrl() + "snapshots")

    def haInfo(self):
        url = "{0}homeassistant/info".format(self.config.hassioBaseUrl())
        return self._getHassioData(url)

    def selfInfo(self) -> Dict[str, Any]:
        return self._getHassioData(self.config.hassioBaseUrl() + "addons/self/info")

    def hassosInfo(self) -> Dict[str, Any]:
        return self._getHassioData(self.config.hassioBaseUrl() + "hassos/info")

    def info(self) -> Dict[str, Any]:
        return self._getHassioData(self.config.hassioBaseUrl() + "info")

    def refreshSnapshots(self):
        url = "{0}snapshots/reload".format(self.config.hassioBaseUrl())
        return self._postHassioData(url)

    def supervisorInfo(self):
        url = "{0}supervisor/info".format(self.config.hassioBaseUrl())
        return self._getHassioData(url)

    def restore(self, slug: str, password: str = None) -> None:
        url: str = "{0}snapshots/{1}/restore/full".format(self.config.hassioBaseUrl(), slug)
        if password:
            self._postHassioData(url, {'password': password})
        else:
            self._postHassioData(url, {})

    def download(self, slug) -> SeekableRequest:
        url = "{0}snapshots/{1}/download".format(self.config.hassioBaseUrl(), slug)
        return SeekableRequest(url, self.config.getHassioHeaders()).prepare()

    def _validateHassioReply(self, resp: Response) -> Dict[str, Any]:
        resp.raise_for_status()
        details: Dict[str, Any] = resp.json()
        if "result" not in details or details["result"] != "ok":
            if "result" in details:
                raise Exception("Hassio said: " + details["result"])
            else:
                raise Exception(
                    "Malformed response from Hassio: " + str(details))

        if "data" not in details:
            return {}

        return details["data"]

    def _getHassioData(self, url: str) -> Dict[str, Any]:
        self.debug("Making Hassio request: " + url)
        return self._validateHassioReply(self._client.get(url, headers=self.config.getHassioHeaders()))

    def _postHassioData(self, url: str, json=None, file=None, data=None) -> Dict[str, Any]:
        self.debug("Making Hassio request: " + url)
        return self._validateHassioReply(self._client.post(url, headers=self.config.getHassioHeaders(), json=json, data=data))

    def _postHaData(self, path: str, data: Dict[str, Any]) -> None:
        self._client.post(self.config.haBaseUrl() + path, headers=self.config.getHaHeaders(), json=data).raise_for_status()

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
        last = "Never"
        if len(snapshots) > 0:
            last = max(snapshots, key=lambda s: s.date()).date().isoformat()

        data: Dict[str, Any] = {
            "state": state,
            "attributes": {
                "friendly_name": "Snapshot State",
                "last_snapshot": last,  # type: ignore
                "snapshots_in_google_drive": len(list(filter(lambda s: s.getSource(SOURCE_GOOGLE_DRIVE) is not None, snapshots))),
                "snapshots_in_hassio": len(list(filter(lambda s: s.getSource(SOURCE_HA), snapshots))),
                "snapshots": list(map(lambda s: {"name": s.name(), "date": str(s.date().isoformat()), "state": s.status()}, snapshots))
            }
        }
        self._postHaData("states/sensor.snapshot_backup", data)
