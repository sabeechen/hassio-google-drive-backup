import json
import logging
import os
import tempfile
import asyncio
import platform
import aiohttp
from yarl import URL

import pytest
from aiohttp import ClientSession
from injector import (ClassAssistedBuilder, Injector, Module, inject, provider,
                      singleton)

from backup.config import Config, Setting
from backup.model import Coordinator
from dev.simulationserver import SimulationServer
from backup.drive import DriveRequests, DriveSource, FolderFinder, AuthCodeQuery
from backup.util import GlobalInfo, Estimator, Resolver, DataCache
from backup.ha import HaRequests, HaSource, HaUpdater
from backup.logger import reset
from backup.model import Model
from backup.model import DummyBackup
from backup.time import Time
from backup.module import BaseModule
from backup.debugworker import DebugWorker
from backup.creds import Creds
from backup.server import ErrorStore
from backup.ha import AddonStopper
from backup.ui import UiServer
from .faketime import FakeTime
from .helpers import Uploader, createBackupTar
from dev.ports import Ports
from dev.simulated_google import SimulatedGoogle
from dev.request_interceptor import RequestInterceptor
from dev.simulated_supervisor import SimulatedSupervisor


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


class ReaderHelper:
    def __init__(self, session, ui_port, ingress_port):
        self.session = session
        self.ui_port = ui_port
        self.ingress_port = ingress_port
        self.timeout = aiohttp.ClientTimeout(total=20)

    def getUrl(self, ingress=True, ssl=False):
        if ssl:
            protocol = "https"
        else:
            protocol = "http"
        if ingress:
            return protocol + "://localhost:" + str(self.ingress_port) + "/"
        else:
            return protocol + "://localhost:" + str(self.ui_port) + "/"

    async def getjson(self, path, status=200, json=None, auth=None, ingress=True, ssl=False, sslcontext=None):
        async with self.session.get(self.getUrl(ingress, ssl) + path, json=json, auth=auth, ssl=sslcontext, timeout=self.timeout) as resp:
            assert resp.status == status
            return await resp.json()

    async def get(self, path, status=200, json=None, auth=None, ingress=True, ssl=False):
        async with self.session.get(self.getUrl(ingress, ssl) + path, json=json, auth=auth, timeout=self.timeout) as resp:
            if resp.status != status:
                import logging
                logging.getLogger().error(resp.text())
                assert resp.status == status
            return await resp.text()

    async def postjson(self, path, status=200, json=None, ingress=True):
        async with self.session.post(self.getUrl(ingress) + path, json=json, timeout=self.timeout) as resp:
            assert resp.status == status
            return await resp.json()

    async def assertError(self, path, error_type="generic_error", status=500, ingress=True, json=None):
        logging.getLogger().info("Requesting " + path)
        data = await self.getjson(path, status=status, ingress=ingress, json=json)
        assert data['error_type'] == error_type


# This module should onyl ever have bindings that can also be satisfied by MainModule
class TestModule(Module):
    def __init__(self, config: Config, ports: Ports):
        self.ports = ports
        self.config = config

    @provider
    @singleton
    def getDriveCreds(self, time: Time) -> Creds:
        return Creds(time, "test_client_id", time.now(), "test_access_token", "test_refresh_token", "test_client_secret")

    @provider
    @singleton
    def getTime(self) -> Time:
        return FakeTime()

    @provider
    @singleton
    def getPorts(self) -> Ports:
        return self.ports

    @provider
    @singleton
    def getConfig(self) -> Config:
        return self.config


@pytest.fixture
def event_loop():
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.new_event_loop()


@pytest.fixture
async def generate_config(server_url: URL, ports, cleandir):
    return Config.withOverrides({
        Setting.DRIVE_URL: str(server_url),
        Setting.SUPERVISOR_URL: str(server_url) + "/",
        Setting.AUTHORIZATION_HOST: str(server_url),
        Setting.TOKEN_SERVER_HOSTS: str(server_url),
        Setting.DRIVE_REFRESH_URL: str(server_url.with_path("/oauth2/v4/token")),
        Setting.DRIVE_AUTHORIZE_URL: str(server_url.with_path("/o/oauth2/v2/auth")),
        Setting.DRIVE_TOKEN_URL: str(server_url.with_path("/token")),
        Setting.DRIVE_DEVICE_CODE_URL: str(server_url.with_path("/device/code")),
        Setting.SUPERVISOR_TOKEN: "test_header",
        Setting.SECRETS_FILE_PATH: "secrets.yaml",
        Setting.CREDENTIALS_FILE_PATH: "credentials.dat",
        Setting.FOLDER_FILE_PATH: "folder.dat",
        Setting.RETAINED_FILE_PATH: "retained.json",
        Setting.ID_FILE_PATH: "id.json",
        Setting.DATA_CACHE_FILE_PATH: "data_cache.json",
        Setting.STOP_ADDON_STATE_PATH: "stop_addon.json",
        Setting.INGRESS_TOKEN_FILE_PATH: "ingress.dat",
        Setting.DEFAULT_DRIVE_CLIENT_ID: "test_client_id",
        Setting.DEFAULT_DRIVE_CLIENT_SECRET: "test_client_secret",
        Setting.BACKUP_DIRECTORY_PATH: cleandir,
        Setting.PORT: ports.ui,
        Setting.INGRESS_PORT: ports.ingress,
        Setting.BACKUP_STARTUP_DELAY_MINUTES: 0,
    })


@pytest.fixture
async def injector(cleandir, ports, generate_config):
    drive_creds = Creds(FakeTime(), "test_client_id", None, "test_access_token", "test_refresh_token")
    with open(os.path.join(cleandir, "secrets.yaml"), "w") as f:
        f.write("for_unit_tests: \"password value\"\n")

    with open(os.path.join(cleandir, "credentials.dat"), "w") as f:
        f.write(json.dumps(drive_creds.serialize()))

    return Injector([BaseModule(), TestModule(generate_config, ports)])


@pytest.fixture
async def ui_server(injector, server):
    os.mkdir("static")
    server = injector.get(UiServer)
    await server.run()
    yield server
    await server.shutdown()


@pytest.fixture
def reader(server, ui_server, session, ui_port, ingress_port):
    return ReaderHelper(session, ui_port, ingress_port)


@pytest.fixture
async def uploader(injector: Injector, server_url):
    return injector.get(ClassAssistedBuilder[Uploader]).build(host=str(server_url))


@pytest.fixture
async def google(injector: Injector):
    return injector.get(SimulatedGoogle)


@pytest.fixture
async def interceptor(injector: Injector):
    return injector.get(RequestInterceptor)


@pytest.fixture
async def supervisor(injector: Injector, server, session):
    return injector.get(SimulatedSupervisor)


@pytest.fixture
async def addon_stopper(injector: Injector):
    return injector.get(AddonStopper)


@pytest.fixture
async def server(injector, port, drive_creds: Creds, session):
    server = injector.get(SimulationServer)

    # start the server
    logging.getLogger().info("Starting SimulationServer on port " + str(port))
    await server.start(port)
    yield server
    await server.stop()


@pytest.fixture
async def data_cache(injector):
    return injector.get(DataCache)


@pytest.fixture
async def session(injector):
    async with injector.get(ClientSession) as session:
        yield session


@pytest.fixture
async def backup(coord, source, dest):
    await coord.sync()
    assert len(coord.backups()) == 1
    return coord.backups()[0]


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
async def device_code(injector):
    return injector.get(AuthCodeQuery)


@pytest.fixture
async def error_store(injector):
    return injector.get(ErrorStore)


@pytest.fixture
async def model(injector):
    return injector.get(Model)


@pytest.fixture
async def global_info(injector):
    return injector.get(GlobalInfo)


@pytest.fixture
async def server_url(port):
    return URL("http://localhost:").with_port(port)


@pytest.fixture
async def ports(unused_tcp_port_factory):
    return Ports(unused_tcp_port_factory(), unused_tcp_port_factory(), unused_tcp_port_factory())


@pytest.fixture
async def port(ports: Ports):
    return ports.server


@pytest.fixture
async def ui_url(ports: Ports):
    return URL("http://localhost").with_port(ports.ingress)


@pytest.fixture
async def ui_port(ports: Ports):
    return ports.ui


@pytest.fixture
async def ingress_port(ports: Ports):
    return ports.ingress


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


@pytest.fixture()
async def folder_finder(injector):
    return injector.get(FolderFinder)


class BackupHelper():
    def __init__(self, uploader, time):
        self.time = time
        self.uploader = uploader

    async def createFile(self, size=1024 * 1024 * 2, slug="testslug", name="Test Name"):
        from_backup: DummyBackup = DummyBackup(
            name, self.time.toUtc(self.time.local(1985, 12, 6)), "fake source", slug)
        data = await self.uploader.upload(createBackupTar(slug, name, self.time.now(), size))
        return from_backup, data


@pytest.fixture
def backup_helper(uploader, time):
    return BackupHelper(uploader, time)
