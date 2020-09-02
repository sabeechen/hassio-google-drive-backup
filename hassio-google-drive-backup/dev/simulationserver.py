import asyncio
import random
import re
from io import BytesIO
from threading import Lock
from typing import Any, Dict
from yarl import URL

import aiohttp
from aiohttp.web import (Application, HTTPBadRequest,
                         HTTPException, HTTPNotFound,
                         HTTPUnauthorized, Request, Response, get,
                         json_response, middleware, post, HTTPSeeOther)
from aiohttp.client import ClientSession
from injector import inject, singleton, Injector, provider, Module

from backup.time import Time
from tests.helpers import all_addons, createSnapshotTar, parseSnapshotInfo
from backup.logger import getLogger
from backup.creds import Creds
from backup.server import Server
from tests.faketime import FakeTime
from datetime import timedelta
from backup.module import BaseModule
from backup.config import Config, Setting
from .http_exception import HttpMultiException
from .simulated_google import SimulatedGoogle
from .base_server import BaseServer
from .ports import Ports
from .request_interceptor import RequestInterceptor
import aiorun

logger = getLogger(__name__)

mimeTypeQueryPattern = re.compile("^mimeType='.*'$")
parentsQueryPattern = re.compile("^'.*' in parents$")
bytesPattern = re.compile("^bytes \\d+-\\d+/\\d+$")
resumeBytesPattern = re.compile("^bytes \\*/\\d+$")
intPattern = re.compile("\\d+")
rangePattern = re.compile("bytes=\\d+-\\d+")


@singleton
class SimulationServer(BaseServer):
    @inject
    def __init__(self, ports: Ports, time: Time, session: ClientSession, authserver: Server, config: Config, google: SimulatedGoogle, interceptor: RequestInterceptor):
        self.interceptor = interceptor
        self.google = google
        self.config = config
        self.id_counter = 0
        self.upload_info: Dict[str, Any] = {}
        self.error_code = 500
        self.match_errors = []
        self.snapshots: Dict[str, Any] = {}
        self.snapshot_data: Dict[str, bytearray] = {}
        self.files: Dict[str, bytearray] = {}
        self.settings: Dict[str, Any] = self.defaultSettings()
        self._snapshot_lock = asyncio.Lock()
        self._settings_lock = Lock()
        self._port = ports.server
        self._ha_error = None
        self._entities = {}
        self._events = []
        self._attributes = {}
        self._notification = None
        self._time: FakeTime = time
        self._options = self.defaultOptions()
        self._username = "user"
        self._password = "pass"
        self.urls = []
        self.relative = True
        self.block_snapshots = False
        self.snapshot_in_progress = False
        self._authserver = authserver
        self.supervisor_error = None
        self.supervisor_sleep = 0

    def wasUrlRequested(self, pattern):
        for url in self.urls:
            if pattern in url:
                return True
        return False

    def blockSnapshots(self):
        self.block_snapshots = True

    def unBlockSnapshots(self):
        self.block_snapshots = False

    def setError(self, url_regx, attempts=0, status=500):
        self.match_errors.append({
            'url': url_regx,
            'attempts': attempts,
            'status': status
        })

    def clearErrors(self):
        self.match_errors.clear()

    def defaultOptions(self):
        return {
            "max_snapshots_in_hassio": 4,
            "max_snapshots_in_google_drive": 4,
            "days_between_snapshots": 3,
            "use_ssl": False
        }

    def getEvents(self):
        return self._events.copy()

    def setHomeAssistantError(self, status_code):
        self._ha_error = status_code

    def getEntity(self, entity):
        return self._entities.get(entity)

    def clearEntities(self):
        self._entities = {}

    def getAttributes(self, attribute):
        return self._attributes.get(attribute)

    def getNotification(self):
        return self._notification

    def _reset(self) -> None:
        with self._settings_lock:
            self._ha_error = None
            self.items = {}
            self.upload_info = {}
            self.snapshots = {}
            self.snapshot_data = {}
            self.files = {}
            self._entities = {}
            self._attributes = {}
            self._notification = None
            self.settings = self.defaultSettings()
            self._options = self.defaultOptions()

    def getSetting(self, key):
        with self._settings_lock:
            return self.settings[key]

    def update(self, config):
        with self._settings_lock:
            self.settings.update(config)

    def defaultSettings(self):
        return {
            'snapshot_wait_time': 0,
            'snapshot_min_size': 1024 * 256 * 1,
            'snapshot_max_size': 1024 * 256 * 2,
            'ha_header': "test_header",
            "ha_version": "0.91.3",
            "ha_last_version": "0.91.2",
            "machine": "raspberrypi3",
            "ip_address": "172.30.32.1",
            "arch": "armv7",
            "image": "homeassistant/raspberrypi3-homeassistant",
            "custom": True,
            "boot": True,
            "port": 8099,
            "ha_port": 1337,
            "ssl": False,
            "watchdog": True,
            "wait_boot": 600,
            "web_ui": "http://[HOST]:8099/",
            "ingress_url": "/index",
            "supervisor": "2.2.2",
            "homeassistant": "0.93.1",
            "hassos": "0.69.69",
            "hassio_error": None,
            "hassio_snapshot_error": None,
            "hostname": "localhost",
            "always_hard_lock": False,
            "supported_arch": [],
            "channel": "dev",
            "addon_slug": "self_slug",
        }

    async def reset(self, request: Request):
        self._reset()
        if isinstance(request, Request):
            self.update(request.query)
        if isinstance(request, Dict):
            self.update(request)

    async def uploadfile(self, request: Request):
        name: str = str(request.query.get("name", "test"))
        self.files[name] = await self.readAll(request)
        return Response(text="")

    async def readFile(self, request: Request):
        return self.serve_bytes(request, self.files[request.query.get("name", "test")])

    async def updateSettings(self, request: Request):
        data = await request.json()
        with self._settings_lock:
            for key in data:
                self.settings[key] = data[key]
            for key in request.query:
                self.settings[key] = request.query[key]
        return Response(text="updated")

    # HASSIO METHODS BELOW
    async def _verifyHassioHeader(self, request) -> bool:
        if self.supervisor_sleep > 0:
            await asyncio.sleep(self.supervisor_sleep)
        if self.getSetting("hassio_error") is not None:
            raise HttpMultiException(self.getSetting("hassio_error"))
        self._verifyHeader(request, "Authorization", "Bearer " + self.getSetting('ha_header'))

    def _verifyHaHeader(self, request) -> bool:
        if self._ha_error is not None:
            raise HttpMultiException(self._ha_error)
        self._verifyHeader(request, "Authorization", "Bearer " + self.getSetting('ha_header'))

    def _verifyHeader(self, request, key: str, value: str) -> bool:
        if request.headers.get(key, None) != value:
            raise HTTPUnauthorized()

    def formatDataResponse(self, data: Any) -> str:
        return json_response({'result': 'ok', 'data': data})

    def checkForSupervisorError(self):
        if self.supervisor_error is not None:
            return Response(status=self.supervisor_error)
        return None

    def formatErrorResponse(self, error: str) -> str:
        return json_response({'result': error})

    async def hassioSnapshots(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        await self._verifyHassioHeader(request)
        return self.formatDataResponse({'snapshots': list(self.snapshots.values())})

    async def hassioSupervisorInfo(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        await self._verifyHassioHeader(request)
        return self.formatDataResponse(
            {
                "addons": list(all_addons).copy()
            }
        )

    async def supervisorLogs(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        await self._verifyHassioHeader(request)
        return Response(body="Supervisor Log line 1\nSupervisor Log Line 2")

    async def coreLogs(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        await self._verifyHassioHeader(request)
        return Response(body="Core Log line 1\nCore Log Line 2")

    async def haInfo(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        await self._verifyHassioHeader(request)
        return self.formatDataResponse(
            {
                "version": self.getSetting('ha_version'),
                "last_version": self.getSetting('ha_last_version'),
                "machine": self.getSetting('machine'),
                "ip_address": self.getSetting('ip_address'),
                "arch": self.getSetting('arch'),
                "image": self.getSetting('image'),
                "custom": self.getSetting('custom'),
                "boot": self.getSetting('boot'),
                "port": self.getSetting('ha_port'),
                "ssl": self.getSetting('ssl'),
                "watchdog": self.getSetting('watchdog'),
                "wait_boot": self.getSetting('wait_boot')
            }
        )

    async def hassioNewFullSnapshot(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        if (self.block_snapshots or self.snapshot_in_progress) and not self.getSetting('always_hard_lock'):
            raise HTTPBadRequest()
        input_json = {}
        try:
            input_json = await request.json()
        except:  # noqa: E722
            pass
        try:
            await self._snapshot_lock.acquire()
            self.snapshot_in_progress = True
            await self._verifyHassioHeader(request)
            error = self.getSetting("hassio_snapshot_error")
            if error is not None:
                raise HttpMultiException(error)

            seconds = int(request.query.get(
                'seconds', self.getSetting('snapshot_wait_time')))
            date = self._time.now()
            size = int(random.uniform(float(self.getSetting('snapshot_min_size')), float(
                self.getSetting('snapshot_max_size'))))
            slug = self.generateId(8)
            name = input_json.get('name', "Default name")
            password = input_json.get('password', None)
            if seconds > 0:
                await asyncio.sleep(seconds)

            data = createSnapshotTar(slug, name, date, size, password=password)
            snapshot_info = parseSnapshotInfo(data)
            self.snapshots[slug] = snapshot_info
            self.snapshot_data[slug] = bytearray(data.getbuffer())
            return self.formatDataResponse({"slug": slug})
        finally:
            self.snapshot_in_progress = False
            self._snapshot_lock.release()

    async def hassioNewPartialSnapshot(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        if (self.block_snapshots or self.snapshot_in_progress) and not self.getSetting('always_hard_lock'):
            raise HTTPBadRequest()
        input_json = await request.json()
        try:
            await self._snapshot_lock.acquire()
            self.snapshot_in_progress = True
            await self._verifyHassioHeader(request)
            seconds = int(request.query.get(
                'seconds', self.getSetting('snapshot_wait_time')))
            date = self._time.now()
            size = int(random.uniform(float(self.getSetting('snapshot_min_size')), float(
                self.getSetting('snapshot_max_size'))))
            slug = self.generateId(8)
            name = input_json['name']
            password = input_json.get('password', None)
            if seconds > 0:
                await asyncio.sleep(seconds)

            data = createSnapshotTar(
                slug,
                name,
                date,
                size,
                included_folders=input_json['folders'],
                included_addons=input_json['addons'],
                password=password)
            snapshot_info = parseSnapshotInfo(data)
            self.snapshots[slug] = snapshot_info
            self.snapshot_data[slug] = bytearray(data.getbuffer())
            return self.formatDataResponse({"slug": slug})
        finally:
            self.snapshot_in_progress = False
            self._snapshot_lock.release()

    async def uploadNewSnapshot(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        await self._verifyHassioHeader(request)
        try:
            received_bytes = await self.readAll(request)
            info = parseSnapshotInfo(BytesIO(received_bytes))
            self.snapshots[info['slug']] = info
            self.snapshot_data[info['slug']] = received_bytes
            return self.formatDataResponse({"slug": info['slug']})
        except Exception as e:
            print(str(e))
            return self.formatErrorResponse("Bad snapshot")

    async def hassioDelete(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        slug = request.match_info.get('slug')
        await self._verifyHassioHeader(request)
        if slug not in self.snapshots:
            raise HTTPNotFound()
        del self.snapshots[slug]
        del self.snapshot_data[slug]
        return self.formatDataResponse("deleted")

    async def hassioSnapshotInfo(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        slug = request.match_info.get('slug')
        await self._verifyHassioHeader(request)
        if slug not in self.snapshots:
            raise HTTPNotFound()
        return self.formatDataResponse(self.snapshots[slug])

    async def hassioSnapshotDownload(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        slug = request.match_info.get('slug')
        await self._verifyHassioHeader(request)
        if slug not in self.snapshot_data:
            raise HTTPNotFound()
        return self.serve_bytes(request, self.snapshot_data[slug])

    async def hassioSelfInfo(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        await self._verifyHassioHeader(request)
        return self.formatDataResponse({
            "webui": self.getSetting('web_ui'),
            'ingress_url': self.getSetting('ingress_url'),
            "slug": self.getSetting('addon_slug'),
            "options": self._options
        })

    async def hassioInfo(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        await self._verifyHassioHeader(request)
        return self.formatDataResponse({
            "supervisor": self.getSetting('supervisor'),
            "homeassistant": self.getSetting('homeassistant'),
            "hassos": self.getSetting('hassos'),
            "hostname": self.getSetting('hostname'),
            "machine": self.getSetting('machine'),
            "arch": self.getSetting('arch'),
            "supported_arch": self.getSetting('supported_arch'),
            "channel": self.getSetting('channel')
        })

    async def hassioAuthenticate(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        await self._verifyHassioHeader(request)
        input_json = await request.json()
        if input_json.get("username") != self._username or input_json.get("password") != self._password:
            raise HTTPBadRequest()
        return self.formatDataResponse({})

    async def haStateUpdate(self, request: Request):
        entity = request.match_info.get('entity')
        self._verifyHaHeader(request)
        json = await request.json()
        self._entities[entity] = json['state']
        self._attributes[entity] = json['attributes']
        return Response()

    async def haEventUpdate(self, request: Request):
        name = request.match_info.get('name')
        self._verifyHaHeader(request)
        self._events.append((name, await request.json()))
        return Response()

    async def createNotification(self, request: Request):
        self._verifyHaHeader(request)
        notification = await request.json()
        print("Created notification with: {}".format(notification))
        self._notification = notification.copy()
        return Response()

    async def dismissNotification(self, request: Request):
        self._verifyHaHeader(request)
        print("Dismissed notification with: {}".format(await request.json()))
        self._notification = None
        return Response()

    async def hassioUpdateOptions(self, request: Request):
        if self.checkForSupervisorError() is not None:
            return self.checkForSupervisorError()
        await self._verifyHassioHeader(request)
        self._options = (await request.json())['options'].copy()
        return self.formatDataResponse({})

    async def slugRedirect(self, request: Request):
        raise HTTPSeeOther("https://localhost:" + str(self.config.get(Setting.INGRESS_PORT)))

    @middleware
    async def error_middleware(self, request: Request, handler):
        self.urls.append(str(request.url))
        resp = await self.interceptor.checkUrl(request)
        if resp is not None:
            return resp
        for error in self.match_errors:
            if re.match(error['url'], request.url.path):
                if error['attempts'] <= 0:
                    await self.readAll(request)
                    return Response(status=error['status'])
                else:
                    error['attempts'] = error['attempts'] - 1
        try:
            resp = await handler(request)
            return resp
        except Exception as ex:
            await self.readAll(request)
            if isinstance(ex, HttpMultiException):
                return Response(status=ex.status_code)
            elif isinstance(ex, HTTPException):
                raise
            else:
                logger.printException(ex)
            return json_response(str(ex), status=500)

    def createApp(self):
        app = Application(middlewares=[self.error_middleware])
        app.add_routes(self.routes())
        self._authserver.buildApp(app)
        return app

    async def start(self, port):
        self.runner = aiohttp.web.AppRunner(self.createApp())
        await self.runner.setup()
        site = aiohttp.web.TCPSite(self.runner, "0.0.0.0", port=port)
        await site.start()

    async def stop(self):
        await self.runner.shutdown()
        await self.runner.cleanup()

    def toggleBlockSnapshot(self, request: Request):
        self.snapshot_in_progress = not self.snapshot_in_progress
        resp = "Blocking" if self.snapshot_in_progress else "Not Blocking"
        return Response(text=resp)

    def routes(self):
        return [
            post('/addons/self/options', self.hassioUpdateOptions),
            post("/core/api/services/persistent_notification/dismiss", self.dismissNotification),
            post("/core/api/services/persistent_notification/create", self.createNotification),
            post("/core/api/events/{name}", self.haEventUpdate),
            post("/core/api/states/{entity}", self.haStateUpdate),
            post('/auth', self.hassioAuthenticate),
            get('/auth', self.hassioAuthenticate),
            get('/info', self.hassioInfo),
            get('/addons/self/info', self.hassioSelfInfo),
            get('/snapshots/{slug}/download', self.hassioSnapshotDownload),
            get('/snapshots/{slug}/info', self.hassioSnapshotInfo),
            post('/snapshots/{slug}/remove', self.hassioDelete),
            post('/snapshots/new/upload', self.uploadNewSnapshot),
            get('/snapshots/new/upload', self.uploadNewSnapshot),
            get('/debug/toggleblock', self.toggleBlockSnapshot),
            post('/snapshots/new/partial', self.hassioNewPartialSnapshot),
            post('/snapshots/new/full', self.hassioNewFullSnapshot),
            get('/snapshots/new/full', self.hassioNewFullSnapshot),
            get('/core/info', self.haInfo),
            get('/supervisor/info', self.hassioSupervisorInfo),
            get('/supervisor/logs', self.supervisorLogs),
            get('/core/logs', self.coreLogs),
            get('/snapshots', self.hassioSnapshots),
            post('/updatesettings', self.updateSettings),
            get('/readfile', self.readFile),
            post('/uploadfile', self.uploadfile),
            post('/doareset', self.reset),
            get('/hassio/ingress/self_slug', self.slugRedirect)
        ] + self.google.routes()


class SimServerModule(BaseModule):
    def __init__(self, config: Config):
        super().__init__(config, override_dns=False)
        self.config = config

    @provider
    @singleton
    def getPorts(self) -> Ports:
        return Ports(56153, self.config.get(Setting.PORT), self.config.get(Setting.INGRESS_PORT))


async def main():
    port = 56153
    base = URL("http://localhost").with_port(port)
    config = Config.withOverrides({
        Setting.DRIVE_AUTHORIZE_URL: str(base.with_path("o/oauth2/v2/auth")),
        Setting.AUTHENTICATE_URL: str(base.with_path("drive/authorize")),
        Setting.DRIVE_TOKEN_URL: str(base.with_path("token")),
        Setting.DRIVE_REFRESH_URL: str(base.with_path("oauth2/v4/token"))
    })
    injector = Injector(SimServerModule(config))
    server = injector.get(SimulationServer)
    await server.reset({
        'snapshot_min_size': 1024 * 1024 * 3,
        'snapshot_max_size': 1024 * 1024 * 5,
        "snapshot_wait_time": 0,
        "hassio_header": "test_header"
    })

    # start the server
    runner = aiohttp.web.AppRunner(server.createApp())
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", port=port)
    await site.start()
    print("Server started on port " + str(port))


if __name__ == '__main__':
    aiorun.run(main())
