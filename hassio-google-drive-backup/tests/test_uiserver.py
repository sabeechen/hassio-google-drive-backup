import logging
import os
from os.path import abspath, join
from shutil import copyfile
from urllib.parse import quote

import aiohttp
import pytest
from aiohttp import BasicAuth

from oauth2client.client import OAuth2Credentials

from backup.util import AsyncHttpGetter, GlobalInfo, File
from backup.server import AsyncServer, Restarter
from backup.config import Config, Setting, CreateOptions
from backup.const import (ERROR_CREDS_EXPIRED, ERROR_EXISTING_FOLDER,
                          ERROR_MULTIPLE_DELETES, ERROR_NO_SNAPSHOT,
                          SOURCE_GOOGLE_DRIVE, SOURCE_HA)
from backup.model import Coordinator, Snapshot
from backup.drive import DriveSource
from backup.ha import HaSource
from .faketime import FakeTime
from .helpers import compareStreams


class ReaderHelper:
    def __init__(self, session, ui_port, ingress_port):
        self.session = session
        self.ui_port = ui_port
        self.ingress_port = ingress_port
        self.timeout = aiohttp.ClientTimeout(total=3)

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

    async def assertError(self, path, error_type="generic_error", status=500, ingress=True):
        logging.getLogger().info("Requesting " + path)
        data = await self.getjson(path, status=status, ingress=ingress)
        assert data['error_type'] == error_type


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
async def ui_server(injector, server):
    os.mkdir("static")
    server = injector.get(AsyncServer)
    await server.run()
    yield server
    await server.shutdown()


@pytest.fixture
async def restarter(injector, server):
    restarter = injector.get(Restarter)
    await restarter.start()
    return restarter


@pytest.fixture
def reader(ui_server, session, ui_port, ingress_port):
    return ReaderHelper(session, ui_port, ingress_port)


@pytest.mark.asyncio
async def test_AsyncServer_start(ui_server: AsyncServer):
    assert ui_server.running


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_AsyncServer_static_files(reader):
    await reader.get("")
    await reader.get("reauthenticate")
    await reader.get("pp")
    await reader.get("tos")


@pytest.mark.asyncio
async def test_getstatus(reader, config: Config, ha, server):
    File.touch(config.get(Setting.INGRESS_TOKEN_FILE_PATH))
    await ha.init()
    data = await reader.getjson("getstatus")
    assert data['ask_error_reports'] is True
    assert data['cred_version'] == 0
    assert data['drive_enabled'] is True
    assert data['firstSync'] is True
    assert data['folder_id'] is None
    assert data['last_error'] is None
    assert data['last_snapshot'] == "Never"
    assert data['maxSnapshotsInDrive'] == config.get(
        Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE)
    assert data['maxSnapshotsInHasssio'] == config.get(
        Setting.MAX_SNAPSHOTS_IN_HASSIO)
    assert data['next_snapshot'] == "right now"
    assert data['restore_link'] == "http://{host}:1337/hassio/snapshots"
    assert data['snapshot_name_template'] == config.get(Setting.SNAPSHOT_NAME)
    assert data['warn_ingress_upgrade'] is False
    assert len(data['snapshots']) == 0
    assert data['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 0,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 0,
        'snapshots': 0,
        'size': '0.0 B'
    }
    assert data['sources'][SOURCE_HA] == {
        'deletable': 0,
        'name': SOURCE_HA,
        'retained': 0,
        'snapshots': 0,
        'size': '0.0 B'
    }
    assert len(data['sources']) == 2


@pytest.mark.asyncio
@pytest.mark.flaky(reruns=5, reruns_delay=2)
async def test_getstatus_sync(reader, config: Config, snapshot: Snapshot):
    data = await reader.getjson("getstatus")
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
        'snapshots': 1,
        'size': data['sources'][SOURCE_GOOGLE_DRIVE]['size']
    }
    assert data['sources'][SOURCE_HA] == {
        'deletable': 1,
        'name': SOURCE_HA,
        'retained': 0,
        'snapshots': 1,
        'size': data['sources'][SOURCE_HA]['size']
    }
    assert len(data['sources']) == 2


@pytest.mark.asyncio
@pytest.mark.flaky(reruns=5, reruns_delay=2)
async def test_retain(reader, config: Config, snapshot: Snapshot, coord: Coordinator):
    slug = snapshot.slug()
    assert await reader.getjson("retain?slug={0}&drive=true&ha=true".format(slug)) == {
        'message': "Updated the snapshot's settings"
    }
    status = await reader.getjson("getstatus")
    assert status['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 0,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 1,
        'snapshots': 1,
        'size': status['sources'][SOURCE_GOOGLE_DRIVE]['size']
    }
    assert status['sources'][SOURCE_HA] == {
        'deletable': 0,
        'name': SOURCE_HA,
        'retained': 1,
        'snapshots': 1,
        'size': status['sources'][SOURCE_HA]['size']
    }

    await reader.getjson("retain?slug={0}&drive=false&ha=false".format(slug))
    status = await reader.getjson("getstatus")
    assert status['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 1,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 0,
        'snapshots': 1,
        'size': status['sources'][SOURCE_GOOGLE_DRIVE]['size']
    }
    assert status['sources'][SOURCE_HA] == {
        'deletable': 1,
        'name': SOURCE_HA,
        'retained': 0,
        'snapshots': 1,
        'size': status['sources'][SOURCE_HA]['size']
    }
    await reader.getjson("deleteSnapshot?slug={0}&drive=true&ha=false".format(slug))
    await reader.getjson("retain?slug={0}&drive=true&ha=true".format(slug))
    status = await reader.getjson("getstatus")
    assert status['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 0,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 0,
        'snapshots': 0,
        'size': status['sources'][SOURCE_GOOGLE_DRIVE]['size']
    }
    assert status['sources'][SOURCE_HA] == {
        'deletable': 0,
        'name': SOURCE_HA,
        'retained': 1,
        'snapshots': 1,
        'size': status['sources'][SOURCE_HA]['size']
    }

    # sync again, which should upoload the snapshot to Drive
    await coord.sync()
    status = await reader.getjson("getstatus")
    assert status['sources'][SOURCE_GOOGLE_DRIVE]['snapshots'] == 1
    assert status['sources'][SOURCE_GOOGLE_DRIVE]['retained'] == 1

    # it shoudl be retained, since we indicated it should be retained in the last call with drive=true
    assert status['snapshots'][0]['driveRetain']


@pytest.mark.asyncio
@pytest.mark.flaky(reruns=5, reruns_delay=2)
async def test_sync(reader, ui_server, coord: Coordinator, time: FakeTime, session):
    assert len(coord.snapshots()) == 0
    status = await reader.getjson("sync")
    assert len(coord.snapshots()) == 1
    assert status == await reader.getjson("getstatus")
    time.advance(days=7)
    assert len((await reader.getjson("sync"))['snapshots']) == 2


@pytest.mark.asyncio
async def test_delete(reader, ui_server, snapshot):
    slug = snapshot.slug()
    await reader.assertError("deleteSnapshot?slug={}&drive=true&ha=false".format("bad_slug"), error_type=ERROR_NO_SNAPSHOT)
    status = await reader.getjson("getstatus")
    assert len(status['snapshots']) == 1
    assert await reader.getjson("deleteSnapshot?slug={}&drive=true&ha=false".format(slug)) == {"message": "Deleted from Google Drive"}
    await reader.assertError("deleteSnapshot?slug={}&drive=true&ha=false".format(slug), error_type=ERROR_NO_SNAPSHOT)
    status = await reader.getjson("getstatus")
    assert len(status['snapshots']) == 1
    assert status['sources'][SOURCE_GOOGLE_DRIVE]['snapshots'] == 0
    assert await reader.getjson("deleteSnapshot?slug={}&drive=false&ha=true".format(slug)) == {"message": "Deleted from Home Assistant"}
    status = await reader.getjson("getstatus")
    assert len(status['snapshots']) == 0
    await reader.assertError("deleteSnapshot?slug={}&drive=false&ha=false".format(slug), error_type=ERROR_NO_SNAPSHOT)


@pytest.mark.asyncio
async def test_backup_now(reader, ui_server, time: FakeTime, snapshot: Snapshot, coord: Coordinator):
    assert len(coord.snapshots()) == 1
    assert (await reader.getjson("getstatus"))["snapshots"][0]["date"] == time.now().isoformat()

    time.advance(hours=1)
    assert await reader.getjson("snapshot?custom_name=TestName&retain_drive=False&retain_ha=False") == {
        'message': "Requested snapshot 'TestName'"
    }
    status = await reader.getjson('getstatus')
    assert len(status["snapshots"]) == 2
    assert status["snapshots"][1]["date"] == time.now().isoformat()
    assert status["snapshots"][1]["name"] == "TestName"
    assert not status["snapshots"][1]["driveRetain"]
    assert not status["snapshots"][1]["haRetain"]

    time.advance(hours=1)
    assert await reader.getjson("snapshot?custom_name=TestName2&retain_drive=True&retain_ha=False") == {
        'message': "Requested snapshot 'TestName2'"
    }
    await coord.sync()
    status = await reader.getjson('getstatus')
    assert len(status["snapshots"]) == 3
    assert not status["snapshots"][1]["driveRetain"]
    assert status["snapshots"][2]["date"] == time.now().isoformat()
    assert status["snapshots"][2]["name"] == "TestName2"
    assert not status["snapshots"][2]["haRetain"]
    assert status["snapshots"][2]["driveRetain"]

    time.advance(hours=1)
    assert await reader.getjson("snapshot?custom_name=TestName3&retain_drive=False&retain_ha=True") == {
        'message': "Requested snapshot 'TestName3'"
    }
    await coord.sync()
    status = await reader.getjson('getstatus')
    assert len(status["snapshots"]) == 4
    assert not status["snapshots"][1]["driveRetain"]
    assert status["snapshots"][3]["date"] == time.now().isoformat()
    assert status["snapshots"][3]["name"] == "TestName3"
    assert status["snapshots"][3]["haRetain"]
    assert not status["snapshots"][3]["driveRetain"]


@pytest.mark.asyncio
async def test_config(reader, ui_server, config: Config, server):
    update = {
        "config": {
            "days_between_snapshots": 20,
            "drive_ipv4": ""
        },
        "snapshot_folder": "unused"
    }
    assert ui_server._starts == 1
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved'}
    assert config.get(Setting.DAYS_BETWEEN_SNAPSHOTS) == 20
    assert server._options["days_between_snapshots"] == 20
    assert ui_server._starts == 1


@pytest.mark.asyncio
@pytest.mark.flaky(reruns=5, reruns_delay=2)
async def test_auth_and_restart(reader, ui_server, config: Config, server, restarter):
    update = {"config": {"require_login": True,
                         "expose_extra_server": True}, "snapshot_folder": "unused"}
    assert ui_server._starts == 1
    assert not config.get(Setting.REQUIRE_LOGIN)
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved'}
    await restarter.waitForRestart()
    assert config.get(Setting.REQUIRE_LOGIN)
    assert server._options['require_login']
    assert ui_server._starts == 2

    await reader.get("getstatus", status=401, ingress=False)
    await reader.get("getstatus", auth=BasicAuth("user", "badpassword"), status=401, ingress=False)
    await reader.get("getstatus", auth=BasicAuth("user", "pass"), ingress=False)
    status = await reader.getjson("sync", auth=BasicAuth("user", "pass"), ingress=False)

    # verify a the sync succeeded (no errors)
    assert status["last_error"] is None

    # The ingress server shouldn't require login, even though its turned on for the extra server
    await reader.get("getstatus")
    # even a bad user/pass should work
    await reader.get("getstatus", auth=BasicAuth("baduser", "badpassword"))


@pytest.mark.asyncio
@pytest.mark.timeout(10)
@pytest.mark.flaky(5)
async def test_expose_extra_server_option(reader, ui_server: AsyncServer, config: Config):
    with pytest.raises(aiohttp.client_exceptions.ClientConnectionError):
        await reader.getjson("sync", ingress=False)
    config.override(Setting.EXPOSE_EXTRA_SERVER, True)
    await ui_server.run()
    await reader.getjson("sync", ingress=False)
    await ui_server.run()
    await reader.getjson("sync", ingress=False)
    config.override(Setting.EXPOSE_EXTRA_SERVER, False)
    await ui_server.run()
    with pytest.raises(aiohttp.client_exceptions.ClientConnectionError):
        await reader.getjson("sync", ingress=False)
    await reader.getjson("sync")


@pytest.mark.asyncio
@pytest.mark.flaky(reruns=5, reruns_delay=2)
async def test_expose_extra_server_override(reader, ui_server: AsyncServer, config: Config, ha: HaSource):
    with pytest.raises(aiohttp.client_exceptions.ClientConnectionError):
        await reader.getjson("sync", ingress=False)
    ha._temporary_extra_server = True
    await ui_server.run()
    await reader.getjson("sync", ingress=False)
    await ui_server.run()
    await reader.getjson("sync", ingress=False)
    ha._temporary_extra_server = False
    await ui_server.run()
    with pytest.raises(aiohttp.client_exceptions.ClientConnectionError):
        await reader.getjson("sync", ingress=False)
    await reader.getjson("sync")


@pytest.mark.asyncio
async def test_update_ingress_true(reader, ui_server: AsyncServer, ha: HaSource, config: Config, restarter):
    # Simulate a user who upgraded from a non-ingress aware version
    await ha.init()
    assert ha.runTemporaryServer()
    assert not config.get(Setting.EXPOSE_EXTRA_SERVER)
    await ui_server.run()
    assert (await reader.getjson('getstatus'))['warn_ingress_upgrade']
    assert (await reader.getjson('getstatus', ingress=False))['warn_ingress_upgrade']

    # Expose the extra server, verify its still available
    assert await reader.getjson('exposeserver?expose=true') == {'message': 'Configuration updated', 'redirect': ''}
    assert config.get(Setting.EXPOSE_EXTRA_SERVER)
    await restarter.waitForRestart()
    assert not (await reader.getjson('getstatus'))['warn_ingress_upgrade']
    assert not (await reader.getjson('getstatus', ingress=False))['warn_ingress_upgrade']


@pytest.mark.asyncio
async def test_update_ingress_false(reader, ui_server: AsyncServer, ha: HaSource, config: Config, restarter: Restarter):
    # Simulate a user who upgraded from a non-ingress aware version
    await ha.init()
    update = {
        "config": {
            "require_login": True,
            "ues_ssl": True,
            "expose_extra_server": False
        },
        "snapshot_folder": "unused"
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved'}

    await restarter.waitForRestart()

    assert ha.runTemporaryServer()
    assert not config.get(Setting.EXPOSE_EXTRA_SERVER)
    await ui_server.run()
    assert (await reader.getjson('getstatus', auth=BasicAuth("user", "pass")))['warn_ingress_upgrade']
    assert (await reader.getjson('getstatus', auth=BasicAuth("user", "pass"), ingress=False))['warn_ingress_upgrade']

    # Turn off the extra server, verify its off
    assert await reader.getjson('exposeserver?expose=false', auth=BasicAuth("user", "pass")) == {'message': 'Configuration updated', 'redirect': ''}
    await restarter.waitForRestart()
    assert not config.get(Setting.EXPOSE_EXTRA_SERVER)
    assert not config.get(Setting.USE_SSL)
    assert not config.get(Setting.REQUIRE_LOGIN)
    assert not (await reader.getjson('getstatus'))['warn_ingress_upgrade']
    with pytest.raises(aiohttp.client_exceptions.ClientConnectionError):
        assert not (await reader.getjson('getstatus', ingress=False))['warn_ingress_upgrade']


@pytest.mark.asyncio
async def test_update_expose_server_redirect(reader, ui_server: AsyncServer, ha: HaSource, config: Config):
    await ha.init()
    assert ha.runTemporaryServer()
    assert not config.get(Setting.EXPOSE_EXTRA_SERVER)
    await ui_server.run()
    assert (await reader.getjson('getstatus'))['warn_ingress_upgrade']

    # Verify the extra server is running
    assert (await reader.getjson('getstatus', ingress=False))['warn_ingress_upgrade']

    assert await reader.getjson('exposeserver?expose=true', ingress=False) == {
        'message': 'Configuration updated',
        'redirect': 'http://{host}:1337/hassio/ingress/self_slug'}


@pytest.mark.asyncio
async def test_update_error_reports_true(reader, ui_server, config: Config, server):
    assert config.get(Setting.SEND_ERROR_REPORTS) is False
    assert not config.isExplicit(Setting.SEND_ERROR_REPORTS)
    assert await reader.getjson("errorreports?send=true") == {'message': 'Configuration updated'}
    assert config.get(Setting.SEND_ERROR_REPORTS) is True
    assert config.isExplicit(Setting.SEND_ERROR_REPORTS)
    assert server._options["send_error_reports"] is True


@pytest.mark.asyncio
async def test_update_error_reports_false(reader, ui_server, config: Config, server):
    assert config.get(Setting.SEND_ERROR_REPORTS) is False
    assert not config.isExplicit(Setting.SEND_ERROR_REPORTS)
    assert await reader.getjson("errorreports?send=false") == {'message': 'Configuration updated'}
    assert config.get(Setting.SEND_ERROR_REPORTS) is False
    assert config.isExplicit(Setting.SEND_ERROR_REPORTS)
    assert server._options["send_error_reports"] is False


@pytest.mark.asyncio
async def test_drive_cred_generation(reader, ui_server, snapshot, server, config: Config, global_info: GlobalInfo, session):
    status = await reader.getjson("getstatus")
    assert len(status["snapshots"]) == 1
    assert global_info.credVersion == 0
    # Invalidate the drive creds, sync, then verify we see an error
    server.update({
        "drive_client_id": "another_client_id",
        "drive_client_secret": "another_client_secret",
        "drive_refresh_token": "another_refresh_token",
        "drive_auth_token": "another_auth_token"
    })
    status = await reader.getjson("sync")
    assert status["last_error"]["error_type"] == "creds_bad"

    # simulate the user going through the Drive authentication workflow
    async with session.get(config.get(Setting.AUTHENTICATE_URL) + "?redirectbacktoken=" + quote(reader.getUrl(True) + "token")) as resp:
        resp.raise_for_status()
    status = (await reader.getjson("sync"))["last_error"] is ERROR_CREDS_EXPIRED
    assert global_info.credVersion == 1


@pytest.mark.asyncio
@pytest.mark.flaky(reruns=5, reruns_delay=2)
async def test_confirm_multiple_deletes(reader, ui_server, server, config: Config, time: FakeTime, ha: HaSource):
    # reconfigure to only store 1 snapshot
    server._options.update(
        {"max_snapshots_in_hassio": 1, "max_snapshots_in_google_drive": 1})
    config.override(Setting.MAX_SNAPSHOTS_IN_HASSIO, 1)
    config.override(Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE, 1)

    # create three snapshots
    await ha.create(CreateOptions(time.now(), "Name1"))
    await ha.create(CreateOptions(time.now(), "Name2"))
    await ha.create(CreateOptions(time.now(), "Name3"))

    # verify we have 3 snapshots an the multiple delete error
    status = await reader.getjson("sync")
    assert len(status['snapshots']) == 3
    assert status["last_error"]["error_type"] == ERROR_MULTIPLE_DELETES
    assert status["last_error"]["data"] == {
        SOURCE_GOOGLE_DRIVE: 0,
        SOURCE_HA: 2
    }

    # request that multiple deletes be allowed
    assert await reader.getjson("confirmdelete?always=false") == {
        'message': 'Snapshots deleted this one time'
    }
    assert config.get(Setting.CONFIRM_MULTIPLE_DELETES)

    # backup, verify the deletes go through
    status = await reader.getjson("sync")
    assert status["last_error"] is None
    assert len(status["snapshots"]) == 1

    # create another snapshot, verify we delete the one
    await ha.create(CreateOptions(time.now(), "Name1"))
    status = await reader.getjson("sync")
    assert len(status['snapshots']) == 1
    assert status["last_error"] is None

    # create two mroe snapshots, verify we see the error again
    await ha.create(CreateOptions(time.now(), "Name1"))
    await ha.create(CreateOptions(time.now(), "Name2"))
    status = await reader.getjson("sync")
    assert len(status['snapshots']) == 3
    assert status["last_error"]["error_type"] == ERROR_MULTIPLE_DELETES
    assert status["last_error"]["data"] == {
        SOURCE_GOOGLE_DRIVE: 0,
        SOURCE_HA: 2
    }


@pytest.mark.asyncio
@pytest.mark.flaky(reruns=5, reruns_delay=2)
async def test_update_multiple_deletes_setting(reader, ui_server, server, config: Config, time: FakeTime, ha: HaSource, global_info: GlobalInfo):
    assert await reader.getjson("confirmdelete?always=true") == {
        'message': 'Configuration updated, I\'ll never ask again'
    }
    assert not config.get(Setting.CONFIRM_MULTIPLE_DELETES)


@pytest.mark.asyncio
async def test_resolve_folder_reuse(reader, config: Config, snapshot, time, drive):
    # Simulate an existing folder error
    old_folder = await drive.getFolderId()
    os.remove(config.get(Setting.FOLDER_FILE_PATH))
    time.advance(days=1)
    status = await reader.getjson("sync")
    assert status["last_error"]["error_type"] == ERROR_EXISTING_FOLDER

    assert (await reader.getjson("resolvefolder?use_existing=true")) == {'message': 'Done'}
    status = await reader.getjson("sync")
    assert status["last_error"] is None
    assert old_folder == await drive.getFolderId()


@pytest.mark.asyncio
async def test_resolve_folder_new(reader, config: Config, snapshot, time, drive):
    # Simulate an existing folder error
    old_folder = await drive.getFolderId()
    os.remove(config.get(Setting.FOLDER_FILE_PATH))
    time.advance(days=1)
    status = await reader.getjson("sync")
    assert status["last_error"]["error_type"] == ERROR_EXISTING_FOLDER

    assert (await reader.getjson("resolvefolder?use_existing=false")) == {'message': 'Done'}
    status = await reader.getjson("sync")
    assert status["last_error"] is None
    assert old_folder != await drive.getFolderId()


@pytest.mark.asyncio
async def test_ssl_server(reader: ReaderHelper, ui_server: AsyncServer, config, server, cleandir, restarter):
    ssl_dir = abspath(join(__file__, "..", "..", "dev", "ssl"))
    copyfile(join(ssl_dir, "localhost.crt"), join(cleandir, "localhost.crt"))
    copyfile(join(ssl_dir, "localhost.key"), join(cleandir, "localhost.key"))
    update = {
        "config": {
            "use_ssl": True,
            "expose_extra_server": True,
            "certfile": join(cleandir, "localhost.crt"),
            "keyfile": join(cleandir, "localhost.key")
        },
        "snapshot_folder": "unused"
    }
    assert ui_server._starts == 1
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved'}
    await restarter.waitForRestart()
    assert ui_server._starts == 2


@pytest.mark.asyncio
async def test_bad_ssl_config_missing_files(reader: ReaderHelper, ui_server: AsyncServer, config, server, cleandir, restarter):
    update = {
        "config": {
            "use_ssl": True,
            "expose_extra_server": True,
            "certfile": join(cleandir, "localhost.crt"),
            "keyfile": join(cleandir, "localhost.key")
        },
        "snapshot_folder": "unused"
    }
    assert ui_server._starts == 1
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved'}
    await restarter.waitForRestart()
    assert ui_server._starts == 2

    # Verify the ingress endpoint is still up, but not the SSL one
    await reader.getjson("getstatus")
    with pytest.raises(aiohttp.client_exceptions.ClientConnectionError):
        await reader.getjson("getstatus", ingress=False, ssl=True, sslcontext=False)


@pytest.mark.asyncio
async def test_bad_ssl_config_wrong_files(reader: ReaderHelper, ui_server: AsyncServer, config, server, cleandir, restarter):
    ssl_dir = abspath(join(__file__, "..", "..", "dev", "ssl"))
    copyfile(join(ssl_dir, "localhost.crt"), join(cleandir, "localhost.crt"))
    copyfile(join(ssl_dir, "localhost.key"), join(cleandir, "localhost.key"))
    update = {
        "config": {
            "use_ssl": True,
            "expose_extra_server": True,
            "certfile": join(cleandir, "localhost.key"),
            "keyfile": join(cleandir, "localhost.crt")
        },
        "snapshot_folder": "unused"
    }
    assert ui_server._starts == 1
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved'}
    await restarter.waitForRestart()
    assert ui_server._starts == 2

    # Verify the ingress endpoint is still up, but not the SSL one
    await reader.getjson("getstatus")
    with pytest.raises(aiohttp.client_exceptions.ClientConnectionError):
        await reader.getjson("getstatus", ingress=False, ssl=True, sslcontext=False)


@pytest.mark.asyncio
@pytest.mark.flaky(reruns=5, reruns_delay=2)
async def test_download_drive(reader, ui_server, snapshot, drive: DriveSource, ha: HaSource, session):
    await ha.delete(snapshot)
    # download the item from Google Drive
    from_drive = await drive.read(snapshot)
    # Download rom the web server
    from_server = AsyncHttpGetter(
        reader.getUrl() + "download?slug=" + snapshot.slug(), {}, session)
    await compareStreams(from_drive, from_server)


@pytest.mark.asyncio
@pytest.mark.flaky(reruns=5, reruns_delay=2)
async def test_download_home_assistant(reader: ReaderHelper, ui_server, snapshot, drive: DriveSource, ha: HaSource, session):
    await drive.delete(snapshot)
    # download the item from Google Drive
    from_ha = await ha.read(snapshot)
    # Download rom the web server
    from_server = AsyncHttpGetter(
        reader.getUrl() + "download?slug=" + snapshot.slug(), {}, session)
    await compareStreams(from_ha, from_server)


@pytest.mark.asyncio
async def test_cancel_and_startsync(reader: ReaderHelper, coord: Coordinator):
    coord._sync_wait.set()
    status = await reader.getjson("startSync")
    assert status["syncing"]
    cancel = await reader.getjson('cancelSync')
    assert not cancel["syncing"]
    assert cancel["last_error"]["error_type"] == "cancelled"


@pytest.mark.asyncio
async def test_token(reader: ReaderHelper, coord: Coordinator, ha, drive: DriveSource):
    creds = OAuth2Credentials("new_access_token", "client_credentials", "new_client_secret", "new_refresh_token", "token_expiry", "token_uri", "user_agent")
    assert "window.location.assign(\"" + ha.getAddonUrl() + "\")" in await reader.get("token?creds=" + quote(creds.to_json()))
    assert drive.drivebackend.cred_bearer == 'new_access_token'
    assert drive.drivebackend.cred_refresh == 'new_refresh_token'
    assert drive.drivebackend.cred_secret == 'new_client_secret'


@pytest.mark.asyncio
async def test_token_extra_server(reader: ReaderHelper, coord: Coordinator, ha, drive: DriveSource, restarter):
    update = {
        "config": {
            "expose_extra_server": True
        },
        "snapshot_folder": "unused"
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved'}
    await restarter.waitForRestart()
    creds = OAuth2Credentials("a", "b", "c", "d", "e", "f", "g")
    resp = await reader.get("token?creds=" + quote(creds.to_json()), ingress=False)
    assert "window.location.assign(\"/\")" in resp


@pytest.mark.asyncio
async def test_changefolder(reader: ReaderHelper, coord: Coordinator, ha, ui_server):
    assert "window.location.assign(\"" + ha.getAddonUrl() + "\")" in await reader.get("changefolder?id=12345")
    assert ui_server._coord._model.dest._folderId == "12345"


@pytest.mark.asyncio
async def test_changefolder_extra_server(reader: ReaderHelper, coord: Coordinator, ha, drive: DriveSource, restarter, ui_server):
    update = {
        "config": {
            "expose_extra_server": True
        },
        "snapshot_folder": "unused"
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved'}
    await restarter.waitForRestart()
    resp = await reader.get("changefolder?id=12345", ingress=False)
    assert "window.location.assign(\"/\")" in resp
    assert ui_server._coord._model.dest._folderId == "12345"
