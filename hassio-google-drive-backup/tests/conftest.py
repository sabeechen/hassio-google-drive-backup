import json
import logging
import os
import tempfile
import asyncio
import platform

import aiohttp
import pytest
from aiohttp import ClientSession
from injector import (ClassAssistedBuilder, Injector, Module, inject, provider,
                      singleton)

from backup.config import Config, Setting
from backup.model import Coordinator
from dev.simulationserver import SimulationServer
from backup.drive import DriveRequests, DriveSource
from backup.util import GlobalInfo, Estimator, Resolver
from backup.ha import HaRequests, HaSource, HaUpdater
from backup.logger import reset
from backup.model import Model
from backup.time import Time
from backup.module import BaseModule
from backup.worker import DebugWorker
from backup.creds import Creds
from .faketime import FakeTime
from .helpers import Uploader


@singleton
class FsFaker():
    @inject
    def __init__(self):
        self.bytes_free = 1024 * 1024 * 1024
        self.bytes_total = 1024 * 1024 * 1024
        self.old_method = None

    def start(self):
        if platform.system() != "Windows":
            self.old_method = os.statvfs
            os.statvfs = self._hijack

    def stop(self):
        if platform.system() != "Windows":
            os.statvfs = self.old_method

    def _hijack(self, path):
        return os.statvfs_result((0, 1, int(self.bytes_total), int(self.bytes_free), 0, 0, 0, 0, 0, 255))

    def setFreeBytes(self, bytes_free, bytes_total=1):
        self.bytes_free = bytes_free
        self.bytes_total = bytes_total
        if self.bytes_free > self.bytes_total:
            self.bytes_total = self.bytes_free


# This module should onyl ever have bindings that can also be satisfied by MainModule
class TestModule(Module):
    def __init__(self, cleandir, server_url, ui_port, ingress_port):
        self.cleandir = cleandir
        self.server_url = server_url
        self.ui_port = ui_port
        self.ingress_port = ingress_port

    @provider
    @singleton
    def getDriveCreds(self, time: Time) -> Creds:
        return Creds(time, "test_client_id", time.now(), "test_access_token", "test_refresh_token", "test_client_secret")

    @provider
    @singleton
    def getTime(self) -> Time:
        return FakeTime()


@pytest.yield_fixture()
def event_loop():
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.new_event_loop()


@pytest.fixture
async def injector(cleandir, server_url, ui_port, ingress_port):
    drive_creds = Creds(time, "test_client_id", None, "test_access_token", "test_refresh_token", "test_client_secret")
    with open(os.path.join(cleandir, "secrets.yaml"), "w") as f:
        f.write("for_unit_tests: \"password value\"\n")

    with open(os.path.join(cleandir, "credentials.dat"), "w") as f:
        f.write(json.dumps(drive_creds.serialize()))

    with open(os.path.join(cleandir, "options.json"), "w") as f:
        json.dump({}, f)

    config = Config(os.path.join(cleandir, "options.json"))
    config.override(Setting.DRIVE_URL, server_url)
    config.override(Setting.HASSIO_URL, server_url + "/")
    config.override(Setting.HOME_ASSISTANT_URL,
                    server_url + "/homeassistant/api/")
    config.override(Setting.AUTHENTICATE_URL,
                    server_url + "/drive/authorize")
    config.override(Setting.DRIVE_REFRESH_URL,
                    server_url + "/oauth2/v4/token")
    config.override(Setting.DRIVE_AUTHORIZE_URL,
                    server_url + "/o/oauth2/v2/auth")
    config.override(Setting.DRIVE_TOKEN_URL,
                    server_url + "/token")
    config.override(Setting.REFRESH_URL,
                    server_url + "/drive/refresh")
    config.override(Setting.ERROR_REPORT_URL,
                    server_url + "/logerror")
    config.override(Setting.HASSIO_TOKEN, "test_header")
    config.override(Setting.SECRETS_FILE_PATH, "secrets.yaml")
    config.override(Setting.CREDENTIALS_FILE_PATH, "credentials.dat")
    config.override(Setting.FOLDER_FILE_PATH, "folder.dat")
    config.override(Setting.RETAINED_FILE_PATH, "retained.json")
    config.override(Setting.INGRESS_TOKEN_FILE_PATH, "ingress.dat")
    config.override(Setting.DEFAULT_DRIVE_CLIENT_ID, "test_client_id")
    config.override(Setting.BACKUP_DIRECTORY_PATH, cleandir)
    config.override(Setting.PORT, ui_port)
    config.override(Setting.INGRESS_PORT, ingress_port)

    # PROBLEM: Something in uploading snapshot chunks hangs between the client and server, so his keeps tests from
    # taking waaaaaaaay too long.  Remove this line and the @pytest.mark.flaky annotations once the problem is identified.
    config.override(Setting.GOOGLE_DRIVE_TIMEOUT_SECONDS, 5)

    # logging.getLogger('injector').setLevel(logging.DEBUG)
    return Injector([BaseModule(config), TestModule(cleandir, server_url, ui_port, ingress_port)])


@pytest.fixture
async def uploader(injector: Injector, server_url):
    return injector.get(ClassAssistedBuilder[Uploader]).build(host=server_url)


@pytest.fixture
async def server(injector, port, drive_creds: Creds, session):
    server = injector.get(
        ClassAssistedBuilder[SimulationServer]).build(port=port)
    await server.reset({
        "drive_refresh_token": drive_creds.refresh_token,
        "drive_client_id": drive_creds.id,
        "drive_client_secret": drive_creds.secret,
        "hassio_header": "test_header"
    })

    # start the server
    logging.getLogger().info("Starting SimulationServer on port " + str(port))
    runner = aiohttp.web.AppRunner(server.createApp())
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", port=port)
    await site.start()
    yield server
    await runner.shutdown()
    await runner.cleanup()


@pytest.fixture
async def session(injector):
    async with injector.get(ClientSession) as session:
        yield session


@pytest.fixture
async def snapshot(coord, source, dest):
    await coord.sync()
    assert len(coord.snapshots()) == 1
    return coord.snapshots()[0]


@pytest.fixture
async def fs(injector):
    faker = injector.get(FsFaker)
    faker.start()
    yield faker
    faker.stop()


@pytest.fixture
async def estimator(injector, fs):
    return injector.get(Estimator)


@pytest.fixture
async def model(injector):
    return injector.get(Model)


@pytest.fixture
async def global_info(injector):
    return injector.get(GlobalInfo)


@pytest.fixture
async def server_url(port):
    return "http://localhost:" + str(port)


@pytest.fixture
async def port(unused_tcp_port_factory):
    return unused_tcp_port_factory()


@pytest.fixture
async def ui_port(unused_tcp_port_factory):
    return unused_tcp_port_factory()


@pytest.fixture
async def ingress_port(unused_tcp_port_factory):
    return unused_tcp_port_factory()


@pytest.fixture
async def coord(injector):
    return injector.get(Coordinator)


@pytest.fixture()
async def updater(injector):
    return injector.get(HaUpdater)


@pytest.fixture()
async def cleandir():
    newpath = tempfile.mkdtemp()
    os.chdir(newpath)
    return newpath


@pytest.fixture
async def time(injector):
    reset()
    return injector.get(Time)


@pytest.fixture
async def config(injector):
    return injector.get(Config)


@pytest.fixture
async def drive_creds(injector):
    return injector.get(Creds)


@pytest.fixture
async def drive(injector, server, session):
    return injector.get(DriveSource)


@pytest.fixture
async def ha(injector, server, session):
    return injector.get(HaSource)


@pytest.fixture
async def ha_requests(injector, server):
    return injector.get(HaRequests)


@pytest.fixture
async def drive_requests(injector, server):
    return injector.get(DriveRequests)


@pytest.fixture
async def resolver(injector):
    return injector.get(Resolver)


@pytest.fixture
async def client_identifier(injector):
    return injector.get(Config).clientIdentifier()


@pytest.fixture
async def debug_worker(injector):
    return injector.get(DebugWorker)
