import os
from typing import Any, Dict, List

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientResponseError, ClientConnectorError
from injector import inject
from asyncio.exceptions import TimeoutError

from ..util import AsyncHttpGetter
from ..config import Config, Setting
from ..const import SOURCE_GOOGLE_DRIVE, SOURCE_HA
from ..exceptions import HomeAssistantDeleteError, SupervisorConnectionError, SupervisorPermissionError, SupervisorTimeoutError, SupervisorUnexpectedError
from ..model import HASnapshot, Snapshot
from ..logger import getLogger
from backup.time import Time

logger = getLogger(__name__)

NOTIFICATION_ID = "backup_broken"
EVENT_SNAPSHOT_START = "snapshot_started"
EVENT_SNAPSHOT_END = "snapshot_ended"


def supervisor_call(func):
    async def wrap_and_call(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ClientConnectorError:
            raise SupervisorConnectionError()
        except TimeoutError:
            raise SupervisorConnectionError()
        except ClientResponseError as e:
            if e.status == 403:
                raise SupervisorPermissionError()
            raise
    return wrap_and_call


class HaRequests():
    """
    Stores logic for interacting with the supervisor add-on API
    """
    @inject
    def __init__(self, config: Config, session: ClientSession, time: Time):
        self.config: Config = config
        self.cache = {}
        self.session = session
        self._time = time

    @supervisor_call
    async def createSnapshot(self, info):
        if 'folders' in info or 'addons' in info:
            url = "{0}snapshots/new/partial".format(
                self.config.get(Setting.HASSIO_URL))
        else:
            url = "{0}snapshots/new/full".format(
                self.config.get(Setting.HASSIO_URL))
        return await self._postHassioData(url, info, timeout=ClientTimeout(total=self.config.get(Setting.PENDING_SNAPSHOT_TIMEOUT_SECONDS)))

    @supervisor_call
    async def auth(self, user: str, password: str) -> None:
        await self._postHassioData("{}auth".format(self.config.get(Setting.HASSIO_URL)), {"username": user, "password": password})

    @supervisor_call
    async def upload(self, stream):
        url: str = "{0}snapshots/new/upload".format(
            self.config.get(Setting.HASSIO_URL))
        return await self._postHassioData(url, data=stream)

    @supervisor_call
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

    @supervisor_call
    async def startAddon(self, slug) -> None:
        url: str = "{0}addons/{1}/start".format(self.config.get(Setting.HASSIO_URL), slug)
        await self._postHassioData(url, {})

    @supervisor_call
    async def stopAddon(self, slug) -> None:
        url: str = "{0}addons/{1}/stop".format(self.config.get(Setting.HASSIO_URL), slug)
        await self._postHassioData(url, {})

    @supervisor_call
    async def snapshot(self, slug):
        if slug in self.cache:
            info = self.cache[slug]
        else:
            info = await self._getHassioData("{0}snapshots/{1}/info".format(self.config.get(Setting.HASSIO_URL), slug))
            self.cache[slug] = info
        return HASnapshot(info, self.config.isRetained(slug))

    @supervisor_call
    async def snapshots(self):
        return await self._getHassioData(self.config.get(Setting.HASSIO_URL) + "snapshots")

    @supervisor_call
    async def haInfo(self):
        url = "{0}core/info".format(
            self.config.get(Setting.HASSIO_URL))
        return await self._getHassioData(url)

    @supervisor_call
    async def selfInfo(self) -> Dict[str, Any]:
        return await self.getAddonInfo("self")

    @supervisor_call
    async def getAddonInfo(self, addon_slug) -> Dict[str, Any]:
        return await self._getHassioData(self.config.get(Setting.HASSIO_URL) + "addons/{0}/info".format(addon_slug))

    @supervisor_call
    async def hassosInfo(self) -> Dict[str, Any]:
        return await self._getHassioData(self.config.get(Setting.HASSIO_URL) + "hassos/info")

    @supervisor_call
    async def info(self) -> Dict[str, Any]:
        return await self._getHassioData(self.config.get(Setting.HASSIO_URL) + "info")

    @supervisor_call
    async def refreshSnapshots(self):
        url = "{0}snapshots/reload".format(self.config.get(Setting.HASSIO_URL))
        return await self._postHassioData(url)

    @supervisor_call
    async def supervisorInfo(self):
        url = "{0}supervisor/info".format(self.config.get(Setting.HASSIO_URL))
        return await self._getHassioData(url)

    @supervisor_call
    async def restore(self, slug: str, password: str = None) -> None:
        url: str = "{0}snapshots/{1}/restore/full".format(
            self.config.get(Setting.HASSIO_URL), slug)
        if password:
            await self._postHassioData(url, {'password': password})
        else:
            await self._postHassioData(url, {})

    @supervisor_call
    async def download(self, slug) -> AsyncHttpGetter:
        url = "{0}snapshots/{1}/download".format(
            self.config.get(Setting.HASSIO_URL), slug)
        ret = AsyncHttpGetter(url,
                              self._getHassioHeaders(),
                              self.session,
                              timeoutFactory=SupervisorTimeoutError.factory,
                              otherErrorFactory=SupervisorUnexpectedError.factory,
                              timeout=ClientTimeout(sock_connect=self.config.get(Setting.DOWNLOAD_TIMEOUT_SECONDS),
                                                    sock_read=self.config.get(Setting.DOWNLOAD_TIMEOUT_SECONDS)),
                              time=self._time)
        return ret

    @supervisor_call
    async def getSuperLogs(self):
        url = "{0}supervisor/logs".format(self.config.get(Setting.HASSIO_URL))
        async with self.session.get(url, headers=self._getHassioHeaders()) as resp:
            resp.raise_for_status()
            return await resp.text()

    @supervisor_call
    async def getCoreLogs(self):
        url = "{0}core/logs".format(self.config.get(Setting.HASSIO_URL))
        async with self.session.get(url, headers=self._getHassioHeaders()) as resp:
            resp.raise_for_status()
            return await resp.text()

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

    async def getAddonLogo(self, slug: str):
        url = "{0}addons/{1}/logo".format(self.config.get(Setting.HASSIO_URL), slug)
        async with self.session.get(url, headers=self._getHassioHeaders()) as resp:
            resp.raise_for_status()
            return (resp.headers['Content-Type'], await resp.read())

    def _getToken(self):
        configured = self.config.get(Setting.HASSIO_TOKEN)
        if configured and len(configured) > 0:
            return configured
        return os.environ.get("HASSIO_TOKEN")

    def _getHassioHeaders(self):
        return {
            'X-Supervisor-Token': self._getToken()
        }

    def _getHaHeaders(self):
        return {
            'Authorization': 'Bearer ' + self._getToken()
        }

    @supervisor_call
    async def _getHassioData(self, url: str) -> Dict[str, Any]:
        logger.debug("Making Hassio request: " + url)
        return await self._validateHassioReply(await self.session.get(url, headers=self._getHassioHeaders()))

    @supervisor_call
    async def _postHassioData(self, url: str, json=None, file=None, data=None, timeout=None) -> Dict[str, Any]:
        logger.debug("Making Hassio request: " + url)
        return await self._validateHassioReply(await self.session.post(url, headers=self._getHassioHeaders(), json=json, data=data, timeout=timeout))

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
                "friendly_name": "Snapshots Stale",
                "device_class": "problem"
            }
        }
        await self._postHaData("states/binary_sensor.snapshots_stale", data)

    @supervisor_call
    async def updateConfig(self, config) -> None:
        return await self._postHassioData("{0}addons/self/options".format(self.config.get(Setting.HASSIO_URL)), {'options': config})

    @supervisor_call
    async def updateAddonOptions(self, slug, options):
        return await self._postHassioData("{0}addons/{1}/options".format(self.config.get(Setting.HASSIO_URL), slug), options)

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
