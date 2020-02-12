import os
from typing import Any, Dict, List

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientResponseError
from injector import inject

from ..util import AsyncHttpGetter
from ..config import Config, Setting
from ..const import SOURCE_GOOGLE_DRIVE, SOURCE_HA
from ..exceptions import HomeAssistantDeleteError
from ..logbase import LogBase
from ..model import HASnapshot, Snapshot

NOTIFICATION_ID = "backup_broken"
EVENT_SNAPSHOT_START = "snapshot_started"
EVENT_SNAPSHOT_END = "snapshot_ended"


class HaRequests(LogBase):
    """
    Stores logic for interacting with the Hass.io add-on API
    """
    @inject
    def __init__(self, config: Config, session: ClientSession):
        self.config: Config = config
        self.cache = {}
        self.session = session

    async def createSnapshot(self, info):
        if 'folders' in info or 'addons' in info:
            url = "{0}snapshots/new/partial".format(
                self.config.get(Setting.HASSIO_URL))
        else:
            url = "{0}snapshots/new/full".format(
                self.config.get(Setting.HASSIO_URL))
        return await self._postHassioData(url, info)

    async def auth(self, user: str, password: str) -> None:
        await self._postHassioData("{}auth".format(self.config.get(Setting.HASSIO_URL)), {"username": user, "password": password})

    async def upload(self, stream):
        url: str = "{0}snapshots/new/upload".format(
            self.config.get(Setting.HASSIO_URL))
        async with stream:
            return await self._postHassioData(url, data=stream.generator(self.config.get(Setting.DEFAULT_CHUNK_SIZE)))

    async def delete(self, slug) -> None:
        delete_url: str = "{0}snapshots/{1}/remove".format(
            self.config.get(Setting.HASSIO_URL), slug)
        if slug in self.cache:
            del self.cache[slug]
        try:
            await self._postHassioData(delete_url, {})
        except ClientResponseError as e:
            if e.status == 400:
                raise HomeAssistantDeleteError()
            raise e

    async def snapshot(self, slug):
        if slug in self.cache:
            info = self.cache[slug]
        else:
            info = await self._getHassioData("{0}snapshots/{1}/info".format(self.config.get(Setting.HASSIO_URL), slug))
            self.cache[slug] = info
        return HASnapshot(info, self.config.isRetained(slug))

    async def snapshots(self):
        return await self._getHassioData(self.config.get(Setting.HASSIO_URL) + "snapshots")

    async def haInfo(self):
        url = "{0}homeassistant/info".format(
            self.config.get(Setting.HASSIO_URL))
        return await self._getHassioData(url)

    async def selfInfo(self) -> Dict[str, Any]:
        return await self._getHassioData(self.config.get(Setting.HASSIO_URL) + "addons/self/info")

    async def hassosInfo(self) -> Dict[str, Any]:
        return await self._getHassioData(self.config.get(Setting.HASSIO_URL) + "hassos/info")

    async def info(self) -> Dict[str, Any]:
        return await self._getHassioData(self.config.get(Setting.HASSIO_URL) + "info")

    async def refreshSnapshots(self):
        url = "{0}snapshots/reload".format(self.config.get(Setting.HASSIO_URL))
        return await self._postHassioData(url)

    async def supervisorInfo(self):
        url = "{0}supervisor/info".format(self.config.get(Setting.HASSIO_URL))
        return await self._getHassioData(url)

    async def restore(self, slug: str, password: str = None) -> None:
        url: str = "{0}snapshots/{1}/restore/full".format(
            self.config.get(Setting.HASSIO_URL), slug)
        if password:
            await self._postHassioData(url, {'password': password})
        else:
            await self._postHassioData(url, {})

    async def download(self, slug) -> AsyncHttpGetter:
        url = "{0}snapshots/{1}/download".format(
            self.config.get(Setting.HASSIO_URL), slug)
        ret = AsyncHttpGetter(url, self._getHassioHeaders(), self.session)
        return ret

    async def _validateHassioReply(self, resp) -> Dict[str, Any]:
        async with resp:
            resp.raise_for_status()
            details: Dict[str, Any] = await resp.json()
            if "result" not in details or details["result"] != "ok":
                if "result" in details:
                    raise Exception("Hassio said: " + details["result"])
                else:
                    raise Exception(
                        "Malformed response from Hassio: " + str(details))

            if "data" not in details:
                return {}

            return details["data"]

    def _getToken(self):
        configured = self.config.get(Setting.HASSIO_TOKEN)
        if configured and len(configured) > 0:
            return configured
        return os.environ.get("HASSIO_TOKEN")

    def _getHassioHeaders(self):
        return {
            "X-HASSIO-KEY": self._getToken(),
            'Client-Identifier': self.config.clientIdentifier()
        }

    def _getHaHeaders(self):
        return {
            'Authorization': 'Bearer ' + self._getToken(),
            'Client-Identifier': self.config.clientIdentifier()
        }

    async def _getHassioData(self, url: str) -> Dict[str, Any]:
        self.debug("Making Hassio request: " + url)
        return await self._validateHassioReply(await self.session.get(url, headers=self._getHassioHeaders()))

    async def _postHassioData(self, url: str, json=None, file=None, data=None) -> Dict[str, Any]:
        self.debug("Making Hassio request: " + url)
        return await self._validateHassioReply(await self.session.post(url, headers=self._getHassioHeaders(), json=json, data=data))

    async def _postHaData(self, path: str, data: Dict[str, Any]) -> None:
        async with self.session.post(self.config.get(Setting.HOME_ASSISTANT_URL) + path, headers=self._getHaHeaders(), json=data) as resp:
            resp.raise_for_status()

    async def sendNotification(self, title: str, message: str) -> None:
        data: Dict[str, str] = {
            "title": title,
            "message": message,
            "notification_id": NOTIFICATION_ID
        }
        await self._postHaData("services/persistent_notification/create", data)

    async def eventSnapshotStart(self, name, time):
        await self._sendEvent(EVENT_SNAPSHOT_START, {
            'snapshot_name': name,
            'snapshot_time': str(time)
        })

    async def eventSnapshotEnd(self, name, time, completed):
        await self._sendEvent(EVENT_SNAPSHOT_END, {
            'completed': completed,
            'snapshot_name': name,
            'snapshot_time': str(time)
        })

    async def _sendEvent(self, event_name: str, data: Dict[str, str]) -> None:
        await self._postHaData("events/" + event_name, data)

    async def dismissNotification(self) -> None:
        data: Dict[str, str] = {
            "notification_id": NOTIFICATION_ID
        }
        await self._postHaData("services/persistent_notification/dismiss", data)

    async def updateSnapshotStaleSensor(self, state: bool) -> None:
        data: Dict[str, Any] = {
            "state": state,
            "attributes": {
                "friendly_name": "Snapshots Stale"
            }
        }
        await self._postHaData("states/binary_sensor.snapshots_stale", data)

    async def updateConfig(self, config) -> None:
        return await self._postHassioData("{0}addons/self/options".format(self.config.get(Setting.HASSIO_URL)), {'options': config})

    async def updateEntity(self, entity, data):
        await self._postHaData("states/" + entity, data)

    async def updateSnapshotsSensor(self, state: str, snapshots: List[Snapshot]) -> None:
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

        await self._postHaData("states/sensor.snapshot_backup", data)
