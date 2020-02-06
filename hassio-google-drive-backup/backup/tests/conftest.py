import os
import pytest
import tempfile
import aiohttp
import socket
import logging
import json

from .faketime import FakeTime
from ..time import Time
from ..config import Config
from oauth2client.client import OAuth2Credentials
from ..drivesource import DriveSource
from ..hasource import HaSource
from ..harequests import HaRequests
from ..driverequests import DriveRequests
from ..debugworker import DebugWorker
from ..coordinator import Coordinator
from ..globalinfo import GlobalInfo
from ..model import Model, SnapshotDestination, SnapshotSource
from ..haupdater import HaUpdater
from .helpers import Uploader
from ..resolver import SubvertingResolver
from ..settings import Setting
from ..logbase import LogBase
from ..estimator import Estimator
from ..dev.simulationserver import SimulationServer
from injector import Injector, Module, singleton, provider, ClassAssistedBuilder, inject
from aiohttp import ClientSession, TCPConnector


@singleton
class FsFaker():
    @inject
    def __init__(self):
        self.bytes_free = 1024 * 1024 * 1024
        self.bytes_total = 1024 * 1024 * 1024
        self.old_method = None

    def start(self):
        self.old_method = os.statvfs
        os.statvfs = self._hijack

    def stop(self):
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

    def configure(self, binder):
        binder.bind(SnapshotSource, to=HaSource, scope=singleton)
        binder.bind(SnapshotDestination, to=DriveSource, scope=singleton)

    @provider
    @singleton
    def getSession(self, resolver: SubvertingResolver) -> ClientSession:
        conn = TCPConnector(resolver=resolver, family=socket.AF_INET)
        return ClientSession(connector=conn)

    @provider
    @singleton
    def getDriveCreds(self) -> OAuth2Credentials:
        return OAuth2Credentials("", "test_client_id", "test_client_secret", refresh_token="test_Refresh_token", token_expiry="", token_uri="", user_agent="")

    @provider
    @singleton
    def getTime(self) -> Time:
        return FakeTime()

    @provider
    @singleton
    def getConfig(self, drive_creds: OAuth2Credentials) -> Config:
        with open(os.path.join(self.cleandir, "secrets.yaml"), "w") as f:
            f.write("for_unit_tests: \"password value\"\n")

        with open(os.path.join(self.cleandir, "credentials.dat"), "w") as f:
            f.write(drive_creds.to_json())

        with open(os.path.join(self.cleandir, "options.json"), "w") as f:
            json.dump({}, f)

        config = Config(os.path.join(self.cleandir, "options.json"))
        config.override(Setting.DRIVE_URL, self.server_url)
        config.override(Setting.HASSIO_URL, self.server_url + "/")
        config.override(Setting.HOME_ASSISTANT_URL, self.server_url + "/homeassistant/api/")
        config.override(Setting.AUTHENTICATE_URL, self.server_url + "/external/drivecreds/")
        config.override(Setting.ERROR_REPORT_URL, self.server_url + "/errorreport")
        config.override(Setting.HASSIO_TOKEN, "test_header")
        config.override(Setting.SECRETS_FILE_PATH, "secrets.yaml")
        config.override(Setting.CREDENTIALS_FILE_PATH, "credentials.dat")
        config.override(Setting.FOLDER_FILE_PATH, "folder.dat")
        config.override(Setting.RETAINED_FILE_PATH, "retained.json")
        config.override(Setting.INGRESS_TOKEN_FILE_PATH, "ingress.dat")
        config.override(Setting.DEFAULT_DRIVE_CLIENT_ID, "test_client_id")
        config.override(Setting.BACKUP_DIRECTORY_PATH, self.cleandir)
        config.override(Setting.PORT, self.ui_port)
        config.override(Setting.INGRESS_PORT, self.ingress_port)

        return config


@pytest.fixture
async def injector(cleandir, server_url, ui_port, ingress_port):
    # logging.getLogger('injector').setLevel(logging.DEBUG)
    return Injector(TestModule(cleandir, server_url, ui_port, ingress_port))


@pytest.fixture
async def uploader(injector: Injector, server_url):
    return injector.get(ClassAssistedBuilder[Uploader]).build(host=server_url)


@pytest.fixture
async def server(injector, port, drive_creds, session):
    server = injector.get(ClassAssistedBuilder[SimulationServer]).build(port=port)
    await server.reset({
        "drive_refresh_token": drive_creds.refresh_token,
        "drive_client_id": drive_creds.client_id,
        "drive_client_secret": drive_creds.client_secret,
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
async def updater(time, config, global_info, ha_requests):
    return HaUpdater(ha_requests, config, time, global_info)


@pytest.fixture()
async def cleandir():
    newpath = tempfile.mkdtemp()
    os.chdir(newpath)
    return newpath


@pytest.fixture
async def time(injector):
    LogBase.reset()
    return injector.get(Time)


@pytest.fixture
async def config(injector):
    return injector.get(Config)


@pytest.fixture
async def drive_creds(injector):
    return injector.get(OAuth2Credentials)


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
    return injector.get(SubvertingResolver)


@pytest.fixture
async def client_identifier(injector):
    return injector.get(Config).clientIdentifier()


@pytest.fixture
async def debug_worker(injector):
    return injector.get(DebugWorker)
