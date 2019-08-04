import pytest
import requests

from ..const import SOURCE_GOOGLE_DRIVE, SOURCE_HA, ERROR_NO_SNAPSHOT, ERROR_CREDS_EXPIRED, ERROR_MULTIPLE_DELETES
from ..uiserver import UIServer
from ..helpers import touch
from .faketime import FakeTime
from ..config import Config
from ..snapshots import Snapshot
from ..coordinator import Coordinator
from ..globalinfo import GlobalInfo
from ..hasource import HaSource
from ..model import CreateOptions
from ..settings import Setting
from .conftest import ServerInstance
from urllib.parse import quote
from requests.exceptions import ConnectionError

URL = "http://localhost:8099/"
EXTRA_SERVER_URL = "http://localhost:1627/"


@pytest.fixture
def source(ha):
    return ha


@pytest.fixture
def dest(drive):
    return drive


@pytest.fixture
def simple_config(config):
    return config


@pytest.fixture
def ui_server(coord, ha, ha_requests, time: FakeTime, global_info, config):
    server = UIServer(coord, ha, ha_requests, time, config, global_info)
    server.run()
    yield server
    server.stop()


def test_uiserver_start(ui_server: UIServer):
    assert ui_server.running


def test_uiserver_static_files(ui_server: UIServer):
    requests.get("http://localhost:8099").raise_for_status()
    requests.get("http://localhost:8099/reauthenticate").raise_for_status()
    requests.get("http://localhost:8099/pp").raise_for_status()
    requests.get("http://localhost:8099/tos").raise_for_status()
    requests.get("http://localhost:8099/redirect?url=test").raise_for_status()


def test_getstatus(ui_server, config: Config, ha):
    touch(config.get(Setting.INGRESS_TOKEN_FILE_PATH))
    ha.init()
    data = getjson("getstatus")
    assert data['ask_error_reports'] is True
    assert data['cred_version'] == 0
    assert data['drive_enabled'] is True
    assert data['firstSync'] is True
    assert data['folder_id'] is None
    assert data['last_error'] is None
    assert data['last_snapshot'] == "Never"
    assert data['maxSnapshotsInDrive'] == config.get(Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE)
    assert data['maxSnapshotsInHasssio'] == config.get(Setting.MAX_SNAPSHOTS_IN_HASSIO)
    assert data['next_snapshot'] == "right now"
    assert data['restore_link'] == "http://{host}:1337/hassio/snapshots"
    assert data['snapshot_name_template'] == config.get(Setting.SNAPSHOT_NAME)
    assert data['warn_ingress_upgrade'] is False
    assert len(data['snapshots']) == 0
    assert data['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 0,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 0,
        'snapshots': 0
    }
    assert data['sources'][SOURCE_HA] == {
        'deletable': 0,
        'name': SOURCE_HA,
        'retained': 0,
        'snapshots': 0
    }
    assert len(data['sources']) == 2


def test_getstatus_sync(ui_server, config: Config, snapshot: Snapshot):
    data = getjson("getstatus")
    assert data['firstSync'] is False
    assert data['folder_id'] is not None
    assert data['last_error'] is None
    assert data['last_snapshot'] != "Never"
    assert data['next_snapshot'] != "right now"
    assert len(data['snapshots']) == 1
    assert data['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 1,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 0,
        'snapshots': 1
    }
    assert data['sources'][SOURCE_HA] == {
        'deletable': 1,
        'name': SOURCE_HA,
        'retained': 0,
        'snapshots': 1
    }
    assert len(data['sources']) == 2


def test_retain(ui_server, config: Config, snapshot: Snapshot, coord: Coordinator):
    slug = snapshot.slug()
    assert getjson("retain?slug={0}&drive=true&ha=true".format(slug)) == {
        'message': "Updated the snapshot's settings"
    }
    status = getjson("getstatus")
    assert status['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 0,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 1,
        'snapshots': 1
    }
    assert status['sources'][SOURCE_HA] == {
        'deletable': 0,
        'name': SOURCE_HA,
        'retained': 1,
        'snapshots': 1
    }

    getjson("retain?slug={0}&drive=false&ha=false".format(slug))
    status = getjson("getstatus")
    assert status['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 1,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 0,
        'snapshots': 1
    }
    assert status['sources'][SOURCE_HA] == {
        'deletable': 1,
        'name': SOURCE_HA,
        'retained': 0,
        'snapshots': 1
    }
    getjson("deleteSnapshot?slug={0}&drive=true&ha=false".format(slug))
    getjson("retain?slug={0}&drive=true&ha=true".format(slug))
    status = getjson("getstatus")
    assert status['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 0,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 0,
        'snapshots': 0
    }
    assert status['sources'][SOURCE_HA] == {
        'deletable': 0,
        'name': SOURCE_HA,
        'retained': 1,
        'snapshots': 1
    }

    # sync again, which should upoload the snapshot to Drive
    coord.sync()
    status = getjson("getstatus")
    assert status['sources'][SOURCE_GOOGLE_DRIVE]['snapshots'] == 1
    assert status['sources'][SOURCE_GOOGLE_DRIVE]['retained'] == 1

    # it shoudl be retained, since we indicated it should be retained in the last call with drive=true
    assert status['snapshots'][0]['driveRetain']


def test_sync(ui_server, coord: Coordinator, time: FakeTime):
    assert len(coord.snapshots()) == 0
    status = getjson("sync")
    assert len(coord.snapshots()) == 1
    assert status == getjson("getstatus")
    time.advance(days=7)
    assert len(getjson("sync")['snapshots']) == 2


def test_delete(ui_server, snapshot):
    slug = snapshot.slug()
    assertError("deleteSnapshot?slug={}&drive=true&ha=false".format("bad_slug"), error_type=ERROR_NO_SNAPSHOT)
    status = getjson("getstatus")
    assert len(status['snapshots']) == 1
    assert getjson("deleteSnapshot?slug={}&drive=true&ha=false".format(slug)) == {"message": "Its gone!"}
    assertError("deleteSnapshot?slug={}&drive=true&ha=false".format(slug), error_type=ERROR_NO_SNAPSHOT)
    status = getjson("getstatus")
    assert len(status['snapshots']) == 1
    assert status['sources'][SOURCE_GOOGLE_DRIVE]['snapshots'] == 0
    assert getjson("deleteSnapshot?slug={}&drive=false&ha=true".format(slug)) == {"message": "Its gone!"}
    status = getjson("getstatus")
    assert len(status['snapshots']) == 0
    assertError("deleteSnapshot?slug={}&drive=false&ha=false".format(slug), error_type=ERROR_NO_SNAPSHOT)


def test_backup_now(ui_server, time: FakeTime, snapshot: Snapshot, coord: Coordinator):
    assert len(coord.snapshots()) == 1
    assert getjson("getstatus")["snapshots"][0]["date"] == time.now().isoformat()

    time.advance(hours=1)
    assert getjson("snapshot?custom_name=TestName&retain_drive=False&retain_ha=False") == {
        'message': "Requested snapshot 'TestName'"
    }
    status = getjson('getstatus')
    assert len(status["snapshots"]) == 2
    assert status["snapshots"][1]["date"] == time.now().isoformat()
    assert status["snapshots"][1]["name"] == "TestName"
    assert not status["snapshots"][1]["driveRetain"]
    assert not status["snapshots"][1]["haRetain"]

    time.advance(hours=1)
    assert getjson("snapshot?custom_name=TestName2&retain_drive=True&retain_ha=False") == {
        'message': "Requested snapshot 'TestName2'"
    }
    coord.sync()
    status = getjson('getstatus')
    assert len(status["snapshots"]) == 3
    assert not status["snapshots"][1]["driveRetain"]
    assert status["snapshots"][2]["date"] == time.now().isoformat()
    assert status["snapshots"][2]["name"] == "TestName2"
    assert not status["snapshots"][2]["haRetain"]
    assert status["snapshots"][2]["driveRetain"]

    time.advance(hours=1)
    assert getjson("snapshot?custom_name=TestName3&retain_drive=False&retain_ha=True") == {
        'message': "Requested snapshot 'TestName3'"
    }
    coord.sync()
    status = getjson('getstatus')
    assert len(status["snapshots"]) == 4
    assert not status["snapshots"][1]["driveRetain"]
    assert status["snapshots"][3]["date"] == time.now().isoformat()
    assert status["snapshots"][3]["name"] == "TestName3"
    assert status["snapshots"][3]["haRetain"]
    assert not status["snapshots"][3]["driveRetain"]


def test_config(ui_server, config: Config, server: ServerInstance):
    update = {
        "config": {
            "days_between_snapshots": 20,
            "drive_ipv4": ""
        }
    }
    assert ui_server._starts == 1
    assert postjson("saveconfig", json=update) == {'message': 'Settings saved'}
    assert config.get(Setting.DAYS_BETWEEN_SNAPSHOTS) == 20
    assert server.getServer()._options["days_between_snapshots"] == 20
    assert ui_server._starts == 1


def test_auth_and_restart(ui_server, config: Config, server: ServerInstance):
    update = {"config": {"require_login": True, "expose_extra_server": True}}
    assert ui_server._starts == 1
    assert not config.get(Setting.REQUIRE_LOGIN)
    assert postjson("saveconfig", json=update) == {'message': 'Settings saved'}
    assert config.get(Setting.REQUIRE_LOGIN)
    assert server.getServer()._options['require_login']
    assert ui_server._starts == 2

    get("getstatus", status=401, url=EXTRA_SERVER_URL)
    get("getstatus", auth=("user", "badpassword"), status=401, url=EXTRA_SERVER_URL)
    get("getstatus", auth=("user", "pass"), url=EXTRA_SERVER_URL)
    status = getjson("sync", auth=("user", "pass"), url=EXTRA_SERVER_URL)

    # verify a the sync succeeded (no errors)
    assert status["last_error"] is None

    # The ingress server shouldn't require login, even though its turned on for the extra server
    get("getstatus")
    # even a bad user/pass should work
    get("getstatus", auth=("baduser", "badpassword"))


def test_expose_extra_server_option(ui_server: UIServer, config: Config):
    with pytest.raises(ConnectionError):
        getjson("sync", url=EXTRA_SERVER_URL)
    config.override(Setting.EXPOSE_EXTRA_SERVER, True)
    ui_server.run()
    getjson("sync", url=EXTRA_SERVER_URL)
    ui_server.run()
    getjson("sync", url=EXTRA_SERVER_URL)
    config.override(Setting.EXPOSE_EXTRA_SERVER, False)
    ui_server.run()
    with pytest.raises(ConnectionError):
        getjson("sync", url=EXTRA_SERVER_URL)
    getjson("sync")


def test_expose_extra_server_override(ui_server: UIServer, config: Config, ha: HaSource):
    with pytest.raises(ConnectionError):
        getjson("sync", url=EXTRA_SERVER_URL)
    ha._temporary_extra_server = True
    ui_server.run()
    getjson("sync", url=EXTRA_SERVER_URL)
    ui_server.run()
    getjson("sync", url=EXTRA_SERVER_URL)
    ha._temporary_extra_server = False
    ui_server.run()
    with pytest.raises(ConnectionError):
        getjson("sync", url=EXTRA_SERVER_URL)
    getjson("sync")


def test_update_ingress_true(ui_server: UIServer, ha: HaSource, config: Config):
    # Simulate a user who upgraded from a non-ingress aware version
    ha.init()
    assert ha.runTemporaryServer()
    assert not config.get(Setting.EXPOSE_EXTRA_SERVER)
    ui_server.run()
    assert getjson('getstatus')['warn_ingress_upgrade']
    assert getjson('getstatus', url=EXTRA_SERVER_URL)['warn_ingress_upgrade']

    # Expose the extra server, verify its still available
    assert getjson('exposeserver?expose=true') == {'message': 'Configuration updated', 'redirect': ''}
    assert config.get(Setting.EXPOSE_EXTRA_SERVER)
    assert not getjson('getstatus')['warn_ingress_upgrade']
    assert not getjson('getstatus', url=EXTRA_SERVER_URL)['warn_ingress_upgrade']


def test_update_ingress_false(ui_server: UIServer, ha: HaSource, config: Config):
    # Simulate a user who upgraded from a non-ingress aware version
    ha.init()
    update = {
        "config": {
            "require_login": True,
            "ues_ssl": True,
            "expose_extra_server": False
        }
    }
    assert postjson("saveconfig", json=update) == {'message': 'Settings saved'}

    assert ha.runTemporaryServer()
    assert not config.get(Setting.EXPOSE_EXTRA_SERVER)
    ui_server.run()
    assert getjson('getstatus', auth=("user", "pass"))['warn_ingress_upgrade']
    assert getjson('getstatus', auth=("user", "pass"), url=EXTRA_SERVER_URL)['warn_ingress_upgrade']

    # Turn off the extra server, verify its off
    assert getjson('exposeserver?expose=false', auth=("user", "pass")) == {'message': 'Configuration updated', 'redirect': ''}
    assert not config.get(Setting.EXPOSE_EXTRA_SERVER)
    assert not config.get(Setting.USE_SSL)
    assert not config.get(Setting.REQUIRE_LOGIN)
    assert not getjson('getstatus')['warn_ingress_upgrade']
    with pytest.raises(ConnectionError):
        assert not getjson('getstatus', url=EXTRA_SERVER_URL)['warn_ingress_upgrade']


def test_update_expose_server_redirect(ui_server: UIServer, ha: HaSource, config: Config):
    ha.init()
    assert ha.runTemporaryServer()
    assert not config.get(Setting.EXPOSE_EXTRA_SERVER)
    ui_server.run()
    assert getjson('getstatus')['warn_ingress_upgrade']

    # Verify the extra server is running
    assert getjson('getstatus', url=EXTRA_SERVER_URL)['warn_ingress_upgrade']

    assert getjson('exposeserver?expose=true', url=EXTRA_SERVER_URL) == {
        'message': 'Configuration updated',
        'redirect': 'http://{host}:1337/hassio/ingress/self_slug'}


def test_update_error_reports_true(ui_server, config: Config, server: ServerInstance):
    assert config.get(Setting.SEND_ERROR_REPORTS) is False
    assert not config.isExplicit(Setting.SEND_ERROR_REPORTS)
    assert getjson("errorreports?send=true") == {'message': 'Configuration updated'}
    assert config.get(Setting.SEND_ERROR_REPORTS) is True
    assert config.isExplicit(Setting.SEND_ERROR_REPORTS)
    assert server.getServer()._options["send_error_reports"] is True


def test_update_error_reports_false(ui_server, config: Config, server: ServerInstance):
    assert config.get(Setting.SEND_ERROR_REPORTS) is False
    assert not config.isExplicit(Setting.SEND_ERROR_REPORTS)
    assert getjson("errorreports?send=false") == {'message': 'Configuration updated'}
    assert config.get(Setting.SEND_ERROR_REPORTS) is False
    assert config.isExplicit(Setting.SEND_ERROR_REPORTS)
    assert server.getServer()._options["send_error_reports"] is False


def test_drive_cred_generation(ui_server, snapshot, server: ServerInstance, config: Config, global_info: GlobalInfo):
    status = getjson("getstatus")
    assert len(status["snapshots"]) == 1
    assert global_info.credVersion == 0
    # Invalidate the drive creds, sync, then verify we see an error
    server.update({
        "drive_client_id": "another_client_id",
        "drive_client_secret": "another_client_secret",
        "drive_refresh_token": "another_refresh_token",
        "drive_auth_token": "another_auth_token"
    })
    status = getjson("sync")
    assert status["last_error"]["error_type"] == "creds_bad"

    # simulate the user going through the Drive authentication workflow
    requests.get(config.get(Setting.AUTHENTICATE_URL) + "?redirectbacktoken=" + quote(URL + "token")).raise_for_status()
    status = getjson("sync")["last_error"] is ERROR_CREDS_EXPIRED
    assert global_info.credVersion == 1


def test_confirm_multiple_deletes(ui_server, server: ServerInstance, config: Config, time: FakeTime, ha: HaSource):
    # reconfigure to only store 1 snapshot
    server.getServer()._options.update({"max_snapshots_in_hassio": 1, "max_snapshots_in_google_drive": 1})
    config.override(Setting.MAX_SNAPSHOTS_IN_HASSIO, 1)
    config.override(Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE, 1)

    # create three snapshots
    ha.create(CreateOptions(time.now(), "Name1"))
    ha.create(CreateOptions(time.now(), "Name2"))
    ha.create(CreateOptions(time.now(), "Name3"))

    # verify we have 3 snapshots an the multiple delete error
    status = getjson("sync")
    assert len(status['snapshots']) == 3
    assert status["last_error"]["error_type"] == ERROR_MULTIPLE_DELETES
    assert status["last_error"]["data"] == {
        SOURCE_GOOGLE_DRIVE: 0,
        SOURCE_HA: 2
    }

    # request that multiple deletes be allowed
    assert getjson("confirmdelete?always=false") == {
        'message': 'Snapshots deleted this one time'
    }
    assert config.get(Setting.CONFIRM_MULTIPLE_DELETES)

    # backup, verify the deletes go through
    status = getjson("sync")
    assert status["last_error"] is None
    assert len(status["snapshots"]) == 1

    # create another snapshot, verify we delete the one
    ha.create(CreateOptions(time.now(), "Name1"))
    status = getjson("sync")
    assert len(status['snapshots']) == 1
    assert status["last_error"] is None

    # create two mroe snapshots, verify we see the error again
    ha.create(CreateOptions(time.now(), "Name1"))
    ha.create(CreateOptions(time.now(), "Name2"))
    status = getjson("sync")
    assert len(status['snapshots']) == 3
    assert status["last_error"]["error_type"] == ERROR_MULTIPLE_DELETES
    assert status["last_error"]["data"] == {
        SOURCE_GOOGLE_DRIVE: 0,
        SOURCE_HA: 2
    }


def test_update_multiple_deletes_setting(ui_server, server: ServerInstance, config: Config, time: FakeTime, ha: HaSource, global_info: GlobalInfo):
    assert getjson("confirmdelete?always=true") == {
        'message': 'Configuration updated, I\'ll never ask again'
    }
    assert not config.get(Setting.CONFIRM_MULTIPLE_DELETES)


def getjson(path, status=200, json=None, auth=None, url=None):
    if url is None:
        url = URL
    resp = requests.get(url + path, json=json, auth=auth)
    assert resp.status_code == status
    data = resp.json()
    return data


def get(path, status=200, json=None, auth=None, url=None):
    if url is None:
        url = URL
    resp = requests.get(url + path, json=json, auth=auth)
    assert resp.status_code == status


def postjson(path, status=200, json=None, url=None):
    if url is None:
        url = URL
    resp = requests.post(url + path, json=json)
    assert resp.status_code == status
    data = resp.json()
    return data


def assertError(path, error_type="generic_error", status=500, url=None):
    data = getjson(path, status=status, url=url)
    assert data['error_type'] == error_type
