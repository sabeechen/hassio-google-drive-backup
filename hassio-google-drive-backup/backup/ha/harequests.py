import os
from typing import Any, Dict, List

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientResponseError, ClientConnectorError
from injector import inject
from asyncio.exceptions import TimeoutError

from ..util import AsyncHttpGetter
from ..config import Config, Setting, Version
from ..const import SOURCE_GOOGLE_DRIVE, SOURCE_HA
from ..exceptions import HomeAssistantDeleteError, SupervisorConnectionError, SupervisorPermissionError, SupervisorTimeoutError, SupervisorUnexpectedError
from ..model import HASnapshot, Snapshot
from ..logger import getLogger
from ..util import DataCache
from backup.time import Time
from yarl import URL

logger = getLogger(__name__)

NOTIFICATION_ID = "backup_broken"
EVENT_SNAPSHOT_START = "snapshot_started"
EVENT_SNAPSHOT_END = "snapshot_ended"

VERSION_BACKUP_PATH = Version.parse("2021.8")


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
    def __init__(self, config: Config, session: ClientSession, time: Time, data_cache: DataCache):
        self.config: Config = config
        self.cache = {}
        self.session = session
        self._time = time
        self._data_cache = data_cache

        # default the supervisor versio to using the "most featured" when it can't be parsed.
        # TODO: remove when we no longer support the "snapshot" query path
        self._super_version = VERSION_BACKUP_PATH

    def getSupervisorURL(self) -> URL:
        if len(self.config.get(Setting.SUPERVISOR_URL)) > 0:
            return URL(self.config.get(Setting.SUPERVISOR_URL))
        if 'SUPERVISOR_TOKEN' in os.environ:
            return URL("http://supervisor")
        else:
            # TODO: remove when we no longer support the "snapshot" query path
            return URL("http://hassio")

    def _getSnapshotPath(self):
        if not self._super_version or self._super_version >= VERSION_BACKUP_PATH:
            return "backups"
        # TODO: remove when we no longer support the "snapshot" query path
        return "snapshots"

    @supervisor_call
    async def createSnapshot(self, info):
        if 'folders' in info or 'addons' in info:
            url = self.getSupervisorURL().with_path("{0}/new/partial".format(self._getSnapshotPath()))
        else:
            url = self.getSupervisorURL().with_path("{0}/new/full".format(self._getSnapshotPath()))
        return await self._postHassioData(url, info, timeout=ClientTimeout(total=self.config.get(Setting.PENDING_SNAPSHOT_TIMEOUT_SECONDS)))

    @supervisor_call
    async def auth(self, user: str, password: str) -> None:
        await self._postHassioData(self.getSupervisorURL().with_path("auth"), {"username": user, "password": password})

    @supervisor_call
    async def upload(self, stream):
        url = self.getSupervisorURL().with_path("{0}/new/upload".format(self._getSnapshotPath()))
        return await self._postHassioData(url, data=stream)

    @supervisor_call
    async def delete(self, slug) -> None:
        delete_url = self.getSupervisorURL().with_path("{1}/{0}/remove".format(slug, self._getSnapshotPath()))
        if slug in self.cache:
            del self.cache[slug]
        try:
            await self._sendHassioData("delete", delete_url, {})
        except ClientResponseError as e:
            if e.status == 400:
                raise HomeAssistantDeleteError()
            raise e

    @supervisor_call
    async def startAddon(self, slug) -> None:
        url = self.getSupervisorURL().with_path("addons/{0}/start".format(slug))
        await self._postHassioData(url, {})

    @supervisor_call
    async def stopAddon(self, slug) -> None:
        url = self.getSupervisorURL().with_path("addons/{0}/stop".format(slug))
        await self._postHassioData(url, {})

    @supervisor_call
    async def snapshot(self, slug):
        if slug in self.cache:
            info = self.cache[slug]
        else:
            info = await self._getHassioData(self.getSupervisorURL().with_path("{1}/{0}/info".format(slug, self._getSnapshotPath())))
            self.cache[slug] = info
        return HASnapshot(info, self._data_cache, self.config, self.config.isRetained(slug))

    @supervisor_call
    async def snapshots(self):
        return await self._getHassioData(self.getSupervisorURL().with_path(self._getSnapshotPath()))

    @supervisor_call
    async def haInfo(self):
        return await self._getHassioData(self.getSupervisorURL().with_path("core/info"))

    @supervisor_call
    async def selfInfo(self) -> Dict[str, Any]:
        return await self.getAddonInfo("self")

    @supervisor_call
    async def getAddonInfo(self, addon_slug) -> Dict[str, Any]:
        return await self._getHassioData(self.getSupervisorURL().with_path("addons/{0}/info".format(addon_slug)))

    @supervisor_call
    async def hassosInfo(self) -> Dict[str, Any]:
        return await self._getHassioData(self.getSupervisorURL().with_path("hassos/info"))

    @supervisor_call
    async def info(self) -> Dict[str, Any]:
        return await self._getHassioData(self.getSupervisorURL().with_path("info"))

    @supervisor_call
    async def refreshSnapshots(self):
        url = self.getSupervisorURL().with_path("{0}/reload".format(self._getSnapshotPath()))
        return await self._postHassioData(url)

    @supervisor_call
    async def supervisorInfo(self):
        url = self.getSupervisorURL().with_path("supervisor/info")
        info = await self._getHassioData(url)

        # parse the supervisor version
        if 'version' in info:
            self._super_version = Version.parse(info['version'])
        return info

    @supervisor_call
    async def restore(self, slug: str, password: str = None) -> None:
        url = self.getSupervisorURL().with_path("{1}/{0}/restore/full".format(slug, self._getSnapshotPath()))
        if password:
            await self._postHassioData(url, {'password': password})
        else:
            await self._postHassioData(url, {})

    @supervisor_call
    async def download(self, slug) -> AsyncHttpGetter:
        url = self.getSupervisorURL().with_path("{1}/{0}/download".format(slug, self._getSnapshotPath()))
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
        url = self.getSupervisorURL().with_path("supervisor/logs")
        async with self.session.get(url, headers=self._getHassioHeaders()) as resp:
            resp.raise_for_status()
            return await resp.text()

    @supervisor_call
    async def getCoreLogs(self):
        url = self.getSupervisorURL().with_path("core/logs")
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
            logger.trace("Hassio replied: %s", details)
            return details["data"]

    async def getAddonLogo(self, slug: str):
        url = self.getSupervisorURL().with_path("addons/{0}/icon".format(slug))
        async with self.session.get(url, headers=self._getHassioHeaders()) as resp:
            resp.raise_for_status()
            return (resp.headers['Content-Type'], await resp.read())

    def _getToken(self):
        configured = self.config.get(Setting.SUPERVISOR_TOKEN)
        if configured and len(configured) > 0:
            return configured
        if "SUPERVISOR_TOKEN" in os.environ:
            return os.environ.get("SUPERVISOR_TOKEN")
        # Older versions of the supervisor use a different name for the token.
        return os.environ.get("HASSIO_TOKEN")

    def _getHassioHeaders(self):
        return self._getHaHeaders()

    def _getHaHeaders(self):
        return {
            'Authorization': 'Bearer ' + self._getToken()
        }

    @supervisor_call
    async def _getHassioData(self, url: URL) -> Dict[str, Any]:
        logger.debug("Making Hassio request: " + str(url))
        return await self._validateHassioReply(await self.session.get(url, headers=self._getHassioHeaders()))

    async def _postHassioData(self, url: URL, json=None, file=None, data=None, timeout=None) -> Dict[str, Any]:
        return await self._sendHassioData("post", url, json, file, data, timeout)

    @supervisor_call
    async def _sendHassioData(self, method: str, url: URL, json=None, file=None, data=None, timeout=None) -> Dict[str, Any]:
        logger.debug("Making Hassio request: " + str(url))
        return await self._validateHassioReply(await self.session.request(method, url, headers=self._getHassioHeaders(), json=json, data=data, timeout=timeout))

    async def _postHaData(self, path: str, data: Dict[str, Any]) -> None:
        url = self.getSupervisorURL().with_path("/core/api/" + path)
        async with self.session.post(url, headers=self._getHaHeaders(), json=data) as resp:
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
        return await self._postHassioData(self.getSupervisorURL().with_path("addons/self/options"), {'options': config})

    @supervisor_call
    async def updateAddonOptions(self, slug, options):
        return await self._postHassioData(self.getSupervisorURL().with_path("addons/{0}/options".format(slug)), options)

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
