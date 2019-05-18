import pytest
import requests

from ..const import SOURCE_GOOGLE_DRIVE, SOURCE_HA, ERROR_NO_SNAPSHOT, ERROR_CREDS_EXPIRED, ERROR_MULTIPLE_DELETES
from ..uiserver import UIServer
from .faketime import FakeTime
from ..config import Config
from ..snapshots import Snapshot
from ..coordinator import Coordinator
from ..globalinfo import GlobalInfo
from ..hasource import HaSource
from ..model import CreateOptions
from .conftest import ServerInstance
from .test_config import defaultAnd
from urllib.parse import quote

URL = "http://localhost:1627/"


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
    ha.init()
    data = getjson("getstatus")
    assert data['ask_error_reports'] is True
    assert data['cred_version'] == 0
    assert data['drive_enabled'] is True
    assert data['firstSync'] is True
    assert data['folder_id'] is None
    assert data['last_error'] is None
    assert data['last_snapshot'] == "Never"
    assert data['maxSnapshotsInDrive'] == config.maxSnapshotsInGoogleDrive()
    assert data['maxSnapshotsInHasssio'] == config.maxSnapshotsInHassio()
    assert data['next_snapshot'] == "right now"
    assert data['restore_link'] == "http://{host}:1337/hassio/snapshots"
    assert data['snapshot_name_template'] == config.snapshotName()
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
    assert config.daysBetweenSnapshots() == 20
    assert server.getServer()._options == defaultAnd({'days_between_snapshots': 20})
    assert ui_server._starts == 1


def test_auth_and_restart(ui_server, config: Config, server: ServerInstance):
    update = {"config": {"require_login": True}}
    assert ui_server._starts == 1
    assert not config.requireLogin()
    assert postjson("saveconfig", json=update) == {'message': 'Settings saved'}
    assert config.requireLogin()
    assert server.getServer()._options['require_login']
    assert ui_server._starts == 2

    get("getstatus", status=401)
    get("getstatus", auth=("user", "pass"))


def test_sync_error():
    # TODO: write this test
    pass


def test_update_ingress(ui_server):
    # INGRESS: write this test when ingre
    pass


def test_update_error_reports_true(ui_server, config: Config, server: ServerInstance):
    assert config.sendErrorReports() is None
    assert getjson("errorreports?send=true") == {'message': 'Configuration updated'}
    assert config.sendErrorReports() is True
    assert server.getServer()._options == defaultAnd({"send_error_reports": True})


def test_update_error_reports_false(ui_server, config: Config, server: ServerInstance):
    assert config.sendErrorReports() is None
    assert getjson("errorreports?send=false") == {'message': 'Configuration updated'}
    assert config.sendErrorReports() is False
    assert server.getServer()._options == defaultAnd()


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
    requests.get(config.authenticateUrl() + "?redirectbacktoken=" + quote(URL + "token")).raise_for_status()
    status = getjson("sync")["last_error"] is ERROR_CREDS_EXPIRED
    assert global_info.credVersion == 1


def test_confirm_multiple_deletes(ui_server, server: ServerInstance, config: Config, time: FakeTime, ha: HaSource):
    # reconfigure to only store 1 snapshot
    server.getServer()._options.update({"max_snapshots_in_hassio": 1, "max_snapshots_in_google_drive": 1})
    config.config.update({"max_snapshots_in_hassio": 1, "max_snapshots_in_google_drive": 1})

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
    assert config.confirmMultipleDeletes()

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
    assert not config.confirmMultipleDeletes()


def getjson(path, status=200, json=None, auth=None):
    resp = requests.get(URL + path, json=json, auth=auth)
    assert resp.status_code == status
    data = resp.json()
    return data


def get(path, status=200, json=None, auth=None):
    resp = requests.get(URL + path, json=json, auth=auth)
    assert resp.status_code == status


def postjson(path, status=200, json=None):
    resp = requests.post(URL + path, json=json)
    assert resp.status_code == status
    data = resp.json()
    return data


def assertError(path, error_type="generic_error", status=500):
    data = getjson(path, status=status)
    assert data['error_type'] == error_type
