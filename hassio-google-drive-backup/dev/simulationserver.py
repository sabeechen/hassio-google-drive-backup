import re
from typing import Dict
from yarl import URL
import aiohttp
from aiohttp.web import (Application,
                         HTTPException,
                         Request, Response, get,
                         json_response, middleware, post, HTTPSeeOther)
from aiohttp.client import ClientSession
from injector import inject, singleton, Injector, provider

from backup.time import Time
from backup.logger import getLogger
from backup.server import Server
from tests.faketime import FakeTime
from backup.module import BaseModule
from backup.config import Config, Setting
from .http_exception import HttpMultiException
from .simulated_google import SimulatedGoogle
from .base_server import BaseServer
from .ports import Ports
from .request_interceptor import RequestInterceptor
from .simulated_supervisor import SimulatedSupervisor
from .apiingress import APIIngress
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
    def __init__(self, ports: Ports, time: Time, session: ClientSession, authserver: Server, config: Config, google: SimulatedGoogle, supervisor: SimulatedSupervisor, api_ingress: APIIngress, interceptor: RequestInterceptor):
        self.interceptor = interceptor
        self.google = google
        self.supervisor = supervisor
        self.config = config
        self.id_counter = 0
        self.files: Dict[str, bytearray] = {}
        self._port = ports.server
        self._time: FakeTime = time
        self.urls = []
        self.relative = True
        self._authserver = authserver
        self._api_ingress = api_ingress

    def wasUrlRequested(self, pattern):
        for url in self.urls:
            if pattern in url:
                return True
        return False

    def blockBackups(self):
        self.block_backups = True

    def unBlockBackups(self):
        self.block_backups = False

    async def uploadfile(self, request: Request):
        name: str = str(request.query.get("name", "test"))
        self.files[name] = await self.readAll(request)
        return Response(text="")

    async def readFile(self, request: Request):
        return self.serve_bytes(request, self.files[request.query.get("name", "test")])

    async def slugRedirect(self, request: Request):
        raise HTTPSeeOther("https://localhost:" + str(self.config.get(Setting.INGRESS_PORT)))

    @middleware
    async def error_middleware(self, request: Request, handler):
        self.urls.append(str(request.url))
        resp = await self.interceptor.checkUrl(request)
        if resp is not None:
            return resp
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

    def routes(self):
        return [
            get('/readfile', self.readFile),
            post('/uploadfile', self.uploadfile),
            get('/ingress/self_slug', self.slugRedirect),
            get('/debug/config', self.debug_config)
        ] + self.google.routes() + self.supervisor.routes() + self._api_ingress.routes()

    async def debug_config(self, request: Request):
        return json_response(self.supervisor._options)


class SimServerModule(BaseModule):
    def __init__(self, base_url: URL):
        super().__init__(override_dns=False)
        self._base_url = base_url

    @provider
    @singleton
    def getConfig(self) -> Config:
        return Config.withOverrides({
            Setting.DRIVE_AUTHORIZE_URL: str(self._base_url.with_path("o/oauth2/v2/auth")),
            Setting.AUTHORIZATION_HOST: str(self._base_url),
            Setting.TOKEN_SERVER_HOSTS: str(self._base_url),
            Setting.DRIVE_TOKEN_URL: str(self._base_url.with_path("token")),
            Setting.DRIVE_DEVICE_CODE_URL: str(self._base_url.with_path("device/code")),
            Setting.DRIVE_REFRESH_URL: str(self._base_url.with_path("oauth2/v4/token")),
            Setting.INGRESS_PORT: 56152
        })

    @provider
    @singleton
    def getPorts(self) -> Ports:
        return Ports(56153, 56151, 56152)


async def main():
    port = 56153
    base = URL("http://localhost").with_port(port)
    injector = Injector(SimServerModule(base))
    server = injector.get(SimulationServer)

    # start the server
    runner = aiohttp.web.AppRunner(server.createApp())
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", port=port)
    await site.start()
    print("Server started on port " + str(port))
    print("Open a browser at http://localhost:" + str(port))


if __name__ == '__main__':
    aiorun.run(main())
