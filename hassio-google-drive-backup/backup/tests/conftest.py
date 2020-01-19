import os
import pytest
import tempfile
import requests
import re

from .faketime import FakeTime
from ..config import Config
from oauth2client.client import OAuth2Credentials
from ..drivesource import DriveSource
from ..hasource import HaSource
from ..harequests import HaRequests
from ..driverequests import DriveRequests
from ..dev.flaskserver import app, cleanupInstance, getInstance, initInstance
from threading import Thread, Lock
from ..coordinator import Coordinator
from ..globalinfo import GlobalInfo
from ..model import Model
from ..haupdater import HaUpdater
from .helpers import HelperTestSource, LockBlocker
from ..dev.testbackend import HelperTestBackend
from ..resolver import Resolver
from ..settings import Setting
from ..logbase import LogBase
from ..estimator import Estimator


class FsFaker():
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


class ServerThread():
    def __init__(self, port):
        self.base = "http://localhost:" + str(port)
        self.thread: Thread = Thread(target=self.run_server, name="server thread")
        self.thread.setDaemon(True)
        self.port = port

    def startServer(self):
        self.thread.start()
        while True:
            if self._ping():
                break

    def _ping(self):
        try:
            requests.get(self.base, timeout=0.5)
            return True
        except requests.exceptions.ReadTimeout:
            return False
        except requests.exceptions.ConnectionError:
            return False

    def run_server(self):
        try:
            app.run(debug=False, host='0.0.0.0', threaded=True, port=self.port)
        except Exception as e:
            if "[Errno 98] Address already in use" not in str(e):
                print("TEST ERROR: " + str(e))


class ServerInstance():
    def __init__(self, id, time, port):
        self.base = "http://localhost:" + str(port)
        self.id = id
        initInstance(id, time, port=port)

    def reset(self, config={"update": "true"}):
        self.getServer().reset()
        self.update(config)

    def getServer(self) -> HelperTestBackend:
        return getInstance(self.id)

    def update(self, config):
        self.getServer().update(config)

    def blockSnapshots(self):
        return LockBlocker().block(self.getServer()._snapshot_lock)

    def getClient(self):
        return requests

    def cleanup(self):
        cleanupInstance(self.id)


class RequestsMock():
    def __init__(self):
        self.lock: Lock = Lock()
        self.old_method = None
        self.exception = None
        self.attempts = None
        self.url_filter = None
        self.urls = []

    def __enter__(self):
        with self.lock:
            self.old_method = requests.request
            requests.request = self._override
        return self

    def __exit__(self, a, b, c):
        with self.lock:
            requests.request = self.old_method
            self.old_method = None

    def _override(self, *args, **kwargs):
        if len(args) >= 2:
            self.urls.append(args[1])

        if len(args) >= 2 and self.exception is not None and (self.url_filter is None or re.match(self.url_filter, args[1])):
            if self.attempts is None or self.attempts <= 0:
                raise self.exception
            else:
                self.attempts -= 1

        return self.old_method(*args, **kwargs)

    def setFailure(self, attempts, url_filter, exception):
        self.attempts = attempts
        self.exception = exception
        self.url_filter = url_filter


@pytest.fixture
def snapshot(coord, source, dest):
    coord.sync()
    assert len(coord.snapshots()) == 1
    return coord.snapshots()[0]


@pytest.fixture
def fs(config, global_info):
    faker = FsFaker()
    faker.start()
    yield faker
    faker.stop()


@pytest.fixture
def estimator(config, global_info, fs):
    yield Estimator(config, global_info)


@pytest.fixture
def model(source, dest, time, simple_config, global_info, estimator):
    return Model(simple_config, time, source, dest, global_info, estimator)


@pytest.fixture
def source():
    return HelperTestSource("Source")


@pytest.fixture
def dest():
    return HelperTestSource("Dest")


@pytest.fixture
def simple_config():
    config = Config()
    return config


@pytest.fixture
def blocker():
    return LockBlocker()


@pytest.fixture
def global_info(time):
    return GlobalInfo(time)


@pytest.fixture
def port():
    return 1234


@pytest.fixture
def coord(model, time, simple_config, global_info, estimator):
    updater = HaUpdater(None, simple_config, time, global_info)
    return Coordinator(model, time, simple_config, global_info, updater, estimator)


@pytest.fixture()
def updater(time, config, global_info, ha_requests):
    return HaUpdater(ha_requests, config, time, global_info)


@pytest.fixture()
def cleandir():
    newpath = tempfile.mkdtemp()
    os.chdir(newpath)
    return newpath


@pytest.fixture
def time():
    LogBase.reset()
    return FakeTime()


@pytest.fixture
def config(cleandir, drive_creds: OAuth2Credentials):
    with open(os.path.join(cleandir, "secrets.yaml"), "w") as f:
        f.write("for_unit_tests: \"password value\"\n")

    with open(os.path.join(cleandir, "credentials.dat"), "w") as f:
        f.write(drive_creds.to_json())

    config = Config()
    config.override(Setting.DRIVE_URL, "http://localhost:1234")
    config.override(Setting.HASSIO_URL, "http://localhost:1234/")
    config.override(Setting.HOME_ASSISTANT_URL, "http://localhost:1234/homeassistant/api/")
    config.override(Setting.AUTHENTICATE_URL, "http://localhost:1234/external/drivecreds/")
    config.override(Setting.HASSIO_TOKEN, "test_header")
    config.override(Setting.SECRETS_FILE_PATH, "secrets.yaml")
    config.override(Setting.CREDENTIALS_FILE_PATH, "credentials.dat")
    config.override(Setting.FOLDER_FILE_PATH, "folder.dat")
    config.override(Setting.RETAINED_FILE_PATH, "retained.json")
    config.override(Setting.INGRESS_TOKEN_FILE_PATH, "ingress.dat")
    config.override(Setting.DEFAULT_DRIVE_CLIENT_ID, "test_client_id")
    config.override(Setting.BACKUP_DIRECTORY_PATH, cleandir)

    return config


@pytest.fixture
def drive_creds():
    return OAuth2Credentials("", "test_client_id", "test_client_secret", refresh_token="test_Refresh_token", token_expiry="", token_uri="", user_agent="")


@pytest.fixture
def drive(time, config, drive_creds, drive_requests, global_info):
    return DriveSource(config, time, drive_requests, global_info)


@pytest.fixture
def ha(time, config, ha_requests, global_info):
    return HaSource(config, time, ha_requests, global_info)


@pytest.fixture
def ha_requests(config, request_client):
    return HaRequests(config, request_client)


@pytest.fixture
def drive_requests(config, time, request_client, resolver):
    return DriveRequests(config, time, request_client, resolver)


@pytest.fixture
def resolver(time):
    return Resolver(time)


@pytest.fixture
def request_client(requests_mock, server):
    with requests_mock:
        yield requests


@pytest.fixture
def requests_mock():
    return RequestsMock()


@pytest.fixture
def client_identifier(config: Config):
    return config.clientIdentifier()


@pytest.fixture
def server(drive_creds: OAuth2Credentials, webserver_raw, client_identifier, time, port):
    instance = ServerInstance(client_identifier, time, port)
    instance.reset({
        "drive_refresh_token": drive_creds.refresh_token,
        "drive_client_id": drive_creds.client_id,
        "drive_client_secret": drive_creds.client_secret,
        "hassio_header": "test_header"
    })
    yield instance
    instance.cleanup()


@pytest.fixture()
def webserver_raw(port, cleandir):
    os.mkdir("www")
    server = ServerThread(port)
    server.startServer()
    return server


def run_server():
    app.run(debug=False, host='0.0.0.0', threaded=True, port=1234)
