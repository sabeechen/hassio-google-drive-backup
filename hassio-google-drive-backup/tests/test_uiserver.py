from datetime import timedelta
import os
import json
from os.path import abspath, join
from shutil import copyfile
from urllib.parse import quote

import aiohttp
import pytest
import asyncio
import base64
from aiohttp import BasicAuth
from aiohttp.client import ClientSession

from backup.util import AsyncHttpGetter, GlobalInfo, File, DataCache, UpgradeFlags
from backup.ui import UiServer, Restarter
from backup.config import Config, Setting, CreateOptions
from backup.const import (ERROR_CREDS_EXPIRED, ERROR_EXISTING_FOLDER,
                          ERROR_MULTIPLE_DELETES, ERROR_NO_BACKUP,
                          SOURCE_GOOGLE_DRIVE, SOURCE_HA)
from backup.creds import Creds
from backup.model import Coordinator, Backup
from backup.drive import DriveSource, FolderFinder
from backup.drive.drivesource import FOLDER_MIME_TYPE, DriveRequests
from backup.ha import HaSource, HaUpdater
from backup.config import VERSION
from .faketime import FakeTime
from .helpers import compareStreams
from yarl import URL
from dev.ports import Ports
from dev.simulated_supervisor import SimulatedSupervisor
from dev.simulationserver import SimulationServer
from dev.simulated_google import SimulatedGoogle
from bs4 import BeautifulSoup
from .conftest import ReaderHelper


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
async def restarter(injector, server):
    restarter = injector.get(Restarter)
    await restarter.start()
    return restarter


@pytest.mark.asyncio
async def test_uiserver_start(ui_server: UiServer):
    assert ui_server.running


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_uiserver_static_files(reader: ReaderHelper):
    await reader.get("")
    await reader.get("reauthenticate")
    await reader.get("pp")
    await reader.get("tos")


@pytest.mark.asyncio
async def test_getstatus(reader, config: Config, ha, server, ports: Ports):
    File.touch(config.get(Setting.INGRESS_TOKEN_FILE_PATH))
    await ha.init()
    data = await reader.getjson("getstatus")
    assert data['ask_error_reports'] is True
    assert data['cred_version'] == 0
    assert data['firstSync'] is True
    assert data['folder_id'] is None
    assert data['last_error'] is None
    assert data['last_backup_text'] == "Never"
    assert data['next_backup_text'] == "right now"
    assert data['backup_name_template'] == config.get(Setting.BACKUP_NAME)
    assert data['warn_ingress_upgrade'] is False
    assert len(data['backups']) == 0
    assert data['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 0,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 0,
        'backups': 0,
        'latest': None,
        'size': '0.0 B',
        'enabled': True,
        'max': config.get(Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE),
        'title': "Google Drive",
        'icon': 'google-drive',
        'ignored': 0,
        'ignored_size': '0.0 B',
    }
    assert data['sources'][SOURCE_HA] == {
        'deletable': 0,
        'name': SOURCE_HA,
        'retained': 0,
        'backups': 0,
        'latest': None,
        'size': '0.0 B',
        'enabled': True,
        'max': config.get(Setting.MAX_BACKUPS_IN_HA),
        'title': "Home Assistant",
        'free_space': "0.0 B",
        'icon': 'home-assistant',
        'ignored': 0,
        'ignored_size': '0.0 B',
    }
    assert len(data['sources']) == 2


@pytest.mark.asyncio
async def test_getstatus_sync(reader, config: Config, backup: Backup, time: FakeTime):
    data = await reader.getjson("getstatus")
    assert data['firstSync'] is False
    assert data['folder_id'] is not None
    assert data['last_error'] is None
    assert data['last_backup_text'] != "Never"
    assert data['next_backup_text'] != "right now"
    assert len(data['backups']) == 1
    assert data['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 1,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 0,
        'backups': 1,
        'latest': time.asRfc3339String(time.now()),
        'size': data['sources'][SOURCE_GOOGLE_DRIVE]['size'],
        'enabled': True,
        'max': config.get(Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE),
        'title': "Google Drive",
        'icon': 'google-drive',
        'free_space': "4.0 GB",
        'ignored': 0,
        'ignored_size': '0.0 B',
    }
    assert data['sources'][SOURCE_HA] == {
        'deletable': 1,
        'name': SOURCE_HA,
        'retained': 0,
        'backups': 1,
        'latest': time.asRfc3339String(time.now()),
        'size': data['sources'][SOURCE_HA]['size'],
        'enabled': True,
        'max': config.get(Setting.MAX_BACKUPS_IN_HA),
        'title': "Home Assistant",
        'free_space': data['sources'][SOURCE_HA]['free_space'],
        'icon': 'home-assistant',
        'ignored': 0,
        'ignored_size': '0.0 B',
    }
    assert len(data['sources']) == 2


@pytest.mark.asyncio
async def test_retain(reader: ReaderHelper, config: Config, backup: Backup, coord: Coordinator, time: FakeTime):
    slug = backup.slug()
    assert await reader.getjson("retain", json={'slug': slug, 'sources': {"GoogleDrive": True, "HomeAssistant": True}}) == {
        'message': "Updated the backup's settings"
    }
    status = await reader.getjson("getstatus")
    assert status['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 0,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 1,
        'backups': 1,
        'latest': time.asRfc3339String(backup.date()),
        'size': status['sources'][SOURCE_GOOGLE_DRIVE]['size'],
        'enabled': True,
        'max': config.get(Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE),
        'title': "Google Drive",
        'icon': 'google-drive',
        'free_space': "4.0 GB",
        'ignored': 0,
        'ignored_size': '0.0 B',
    }
    assert status['sources'][SOURCE_HA] == {
        'deletable': 0,
        'name': SOURCE_HA,
        'retained': 1,
        'backups': 1,
        'latest': time.asRfc3339String(backup.date()),
        'size': status['sources'][SOURCE_HA]['size'],
        'enabled': True,
        'max': config.get(Setting.MAX_BACKUPS_IN_HA),
        'title': "Home Assistant",
        'free_space': status['sources'][SOURCE_HA]["free_space"],
        'icon': 'home-assistant',
        'ignored': 0,
        'ignored_size': '0.0 B',
    }

    await reader.getjson("retain", json={'slug': slug, 'sources': {"GoogleDrive": False, "HomeAssistant": False}})
    status = await reader.getjson("getstatus")
    assert status['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 1,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 0,
        'backups': 1,
        'latest': time.asRfc3339String(backup.date()),
        'size': status['sources'][SOURCE_GOOGLE_DRIVE]['size'],
        'enabled': True,
        'max': config.get(Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE),
        'title': "Google Drive",
        'icon': 'google-drive',
        'free_space': "4.0 GB",
        'ignored': 0,
        'ignored_size': '0.0 B',
    }
    assert status['sources'][SOURCE_HA] == {
        'deletable': 1,
        'name': SOURCE_HA,
        'retained': 0,
        'backups': 1,
        'latest': time.asRfc3339String(backup.date()),
        'size': status['sources'][SOURCE_HA]['size'],
        'enabled': True,
        'max': config.get(Setting.MAX_BACKUPS_IN_HA),
        'title': "Home Assistant",
        'free_space': status['sources'][SOURCE_HA]["free_space"],
        'icon': 'home-assistant',
        'ignored': 0,
        'ignored_size': '0.0 B',
    }
    delete_req = {
        "slug": slug,
        "sources": ["GoogleDrive"]
    }
    await reader.getjson("deleteSnapshot", json=delete_req)
    await reader.getjson("retain", json={'slug': slug, 'sources': {"HomeAssistant": True}})
    status = await reader.getjson("getstatus")
    assert status['sources'][SOURCE_GOOGLE_DRIVE] == {
        'deletable': 0,
        'name': SOURCE_GOOGLE_DRIVE,
        'retained': 0,
        'backups': 0,
        'latest': None,
        'size': status['sources'][SOURCE_GOOGLE_DRIVE]['size'],
        'enabled': True,
        'max': config.get(Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE),
        'title': "Google Drive",
        'icon': 'google-drive',
        'free_space': "4.0 GB",
        'ignored': 0,
        'ignored_size': '0.0 B',
    }
    assert status['sources'][SOURCE_HA] == {
        'deletable': 0,
        'name': SOURCE_HA,
        'retained': 1,
        'backups': 1,
        'latest': time.asRfc3339String(backup.date()),
        'size': status['sources'][SOURCE_HA]['size'],
        'enabled': True,
        'max': config.get(Setting.MAX_BACKUPS_IN_HA),
        'title': "Home Assistant",
        'free_space': status['sources'][SOURCE_HA]["free_space"],
        'icon': 'home-assistant',
        'ignored': 0,
        'ignored_size': '0.0 B',
    }

    # sync again, which should upoload the backup to Drive
    await coord.sync()
    status = await reader.getjson("getstatus")
    assert status['sources'][SOURCE_GOOGLE_DRIVE]['backups'] == 1
    assert status['sources'][SOURCE_GOOGLE_DRIVE]['retained'] == 0
    assert status['sources'][SOURCE_GOOGLE_DRIVE]['backups'] == 1


@pytest.mark.asyncio
async def test_sync(reader, ui_server, coord: Coordinator, time: FakeTime, session):
    assert len(coord.backups()) == 0
    status = await reader.getjson("sync")
    assert len(coord.backups()) == 1
    assert status == await reader.getjson("getstatus")
    time.advance(days=7)
    assert len((await reader.getjson("sync"))['backups']) == 2


@pytest.mark.asyncio
async def test_delete(reader: ReaderHelper, ui_server, backup):
    slug = backup.slug()

    data = {"slug": "bad_slug", "sources": ["GoogleDrive"]}
    await reader.assertError("deleteSnapshot", json=data, error_type=ERROR_NO_BACKUP)
    status = await reader.getjson("getstatus")
    assert len(status['backups']) == 1
    data["slug"] = slug
    assert await reader.getjson("deleteSnapshot", json=data) == {"message": "Deleted from 1 place(s)"}
    await reader.assertError("deleteSnapshot", json=data, error_type=ERROR_NO_BACKUP)
    status = await reader.getjson("getstatus")
    assert len(status['backups']) == 1
    assert status['sources'][SOURCE_GOOGLE_DRIVE]['backups'] == 0
    data["sources"] = ["HomeAssistant"]
    assert await reader.getjson("deleteSnapshot", json=data) == {"message": "Deleted from 1 place(s)"}
    status = await reader.getjson("getstatus")
    assert len(status['backups']) == 0
    data["sources"] = []
    await reader.assertError("deleteSnapshot", json=data, error_type=ERROR_NO_BACKUP)


@pytest.mark.asyncio
async def test_backup_now(reader, ui_server, time: FakeTime, backup: Backup, coord: Coordinator):
    assert len(coord.backups()) == 1
    assert (await reader.getjson("getstatus"))["backups"][0]["date"] == time.toLocal(time.now()).strftime("%c")

    time.advance(hours=1)
    assert await reader.getjson("backup?custom_name=TestName&retain_drive=False&retain_ha=False") == {
        'message': "Requested backup 'TestName'"
    }
    status = await reader.getjson('getstatus')
    assert len(status["backups"]) == 2
    assert status["backups"][1]["date"] == time.toLocal(time.now()).strftime("%c")
    assert status["backups"][1]["name"] == "TestName"
    assert status["backups"][1]['sources'][0]['retained'] is False
    assert len(status["backups"][1]['sources']) == 1

    time.advance(hours=1)
    assert await reader.getjson("backup?custom_name=TestName2&retain_drive=True&retain_ha=False") == {
        'message': "Requested backup 'TestName2'"
    }
    await coord.sync()
    status = await reader.getjson('getstatus')
    assert len(status["backups"]) == 3
    assert status["backups"][2]["date"] == time.toLocal(time.now()).strftime("%c")
    assert status["backups"][2]["name"] == "TestName2"
    assert status["backups"][2]['sources'][0]['retained'] is False
    assert status["backups"][2]['sources'][1]['retained'] is True

    time.advance(hours=1)
    assert await reader.getjson("backup?custom_name=TestName3&retain_drive=False&retain_ha=True") == {
        'message': "Requested backup 'TestName3'"
    }
    await coord.sync()
    status = await reader.getjson('getstatus')
    assert len(status["backups"]) == 4
    assert status["backups"][3]['sources'][0]['retained'] is True
    assert status["backups"][3]['sources'][1]['retained'] is False
    assert status["backups"][3]["date"] == time.toLocal(time.now()).strftime("%c")
    assert status["backups"][3]["name"] == "TestName3"


@pytest.mark.asyncio
async def test_config(reader, ui_server, config: Config, supervisor: SimulatedSupervisor):
    update = {
        "config": {
            "days_between_backups": 20,
            "drive_ipv4": ""
        },
        "backup_folder": "unused"
    }
    assert ui_server._starts == 1
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}
    assert config.get(Setting.DAYS_BETWEEN_BACKUPS) == 20
    assert supervisor._options["days_between_backups"] == 20
    assert ui_server._starts == 1


@pytest.mark.asyncio
async def test_auth_and_restart(reader, ui_server, config: Config, restarter, coord: Coordinator, supervisor: SimulatedSupervisor):
    update = {"config": {"require_login": True,
                         "expose_extra_server": True}, "backup_folder": "unused"}
    assert ui_server._starts == 1
    assert not config.get(Setting.REQUIRE_LOGIN)
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}
    await restarter.waitForRestart()
    assert config.get(Setting.REQUIRE_LOGIN)
    assert supervisor._options['require_login']
    assert ui_server._starts == 2

    await reader.get("getstatus", status=401, ingress=False)
    await reader.get("getstatus", auth=BasicAuth("user", "badpassword"), status=401, ingress=False)
    await reader.get("getstatus", auth=BasicAuth("user", "pass"), ingress=False)
    await coord.waitForSyncToFinish()
    status = await reader.getjson("getstatus", auth=BasicAuth("user", "pass"), ingress=False)

    # verify a the sync succeeded (no errors)
    assert status["last_error"] is None

    # The ingress server shouldn't require login, even though its turned on for the extra server
    await reader.get("getstatus")
    # even a bad user/pass should work
    await reader.get("getstatus", auth=BasicAuth("baduser", "badpassword"))


@pytest.mark.asyncio
@pytest.mark.timeout(100)
async def test_expose_extra_server_option(reader, ui_server: UiServer, config: Config):
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
async def test_update_error_reports_true(reader, ui_server, config: Config, supervisor: SimulatedSupervisor):
    assert config.get(Setting.SEND_ERROR_REPORTS) is False
    assert not config.isExplicit(Setting.SEND_ERROR_REPORTS)
    assert await reader.getjson("errorreports?send=true") == {'message': 'Configuration updated'}
    assert config.get(Setting.SEND_ERROR_REPORTS) is True
    assert config.isExplicit(Setting.SEND_ERROR_REPORTS)
    assert supervisor._options["send_error_reports"] is True


@pytest.mark.asyncio
async def test_update_error_reports_false(reader, ui_server, config: Config, supervisor: SimulatedSupervisor):
    assert config.get(Setting.SEND_ERROR_REPORTS) is False
    assert not config.isExplicit(Setting.SEND_ERROR_REPORTS)
    assert await reader.getjson("errorreports?send=false") == {'message': 'Configuration updated'}
    assert config.get(Setting.SEND_ERROR_REPORTS) is False
    assert config.isExplicit(Setting.SEND_ERROR_REPORTS)
    assert supervisor._options["send_error_reports"] is False


@pytest.mark.asyncio
async def test_drive_cred_generation(reader: ReaderHelper, ui_server: UiServer, backup, config: Config, global_info: GlobalInfo, session: ClientSession, google):
    status = await reader.getjson("getstatus")
    assert len(status["backups"]) == 1
    assert global_info.credVersion == 0
    # Invalidate the drive creds, sync, then verify we see an error
    google.expireCreds()
    status = await reader.getjson("sync")
    assert status["last_error"]["error_type"] == ERROR_CREDS_EXPIRED

    # simulate the user going through the Drive authentication workflow
    auth_url = URL(status['authenticate_url']).with_query({
        "redirectbacktoken": reader.getUrl(True) + "token",
        "version": VERSION,
        "return": reader.getUrl(True)
    })
    async with session.get(auth_url) as resp:
        resp.raise_for_status()
        html = await resp.text()
        page = BeautifulSoup(html, 'html.parser')
        area = page.find("textarea")
        creds = str(area.getText()).strip()

    cred_url = URL(reader.getUrl(True) + "token").with_query({"creds": creds, "host": reader.getUrl(True)})
    async with session.get(cred_url) as resp:
        resp.raise_for_status()
        # verify we got redirected to the addon main page.
        assert resp.url == URL(reader.getUrl(True))
    await ui_server.sync(None)
    assert global_info._last_error is None
    assert global_info.credVersion == 1


@pytest.mark.asyncio
async def test_confirm_multiple_deletes(reader, ui_server, server, config: Config, time: FakeTime, ha: HaSource):
    # reconfigure to only store 1 backup
    config.override(Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE, 1)
    config.override(Setting.MAX_BACKUPS_IN_HA, 1)

    # create three backups
    await ha.create(CreateOptions(time.now(), "Name1"))
    await ha.create(CreateOptions(time.now(), "Name2"))
    await ha.create(CreateOptions(time.now(), "Name3"))

    # verify we have 3 backups an the multiple delete error
    status = await reader.getjson("sync")
    assert len(status['backups']) == 3
    assert status["last_error"]["error_type"] == ERROR_MULTIPLE_DELETES
    assert status["last_error"]["data"] == {
        SOURCE_GOOGLE_DRIVE: 0,
        SOURCE_HA: 2
    }

    # request that multiple deletes be allowed
    assert await reader.getjson("confirmdelete?always=false") == {
        'message': 'Backups deleted this one time'
    }
    assert config.get(Setting.CONFIRM_MULTIPLE_DELETES)

    # backup, verify the deletes go through
    status = await reader.getjson("sync")
    assert status["last_error"] is None
    assert len(status["backups"]) == 1

    # create another backup, verify we delete the one
    await ha.create(CreateOptions(time.now(), "Name1"))
    status = await reader.getjson("sync")
    assert len(status['backups']) == 1
    assert status["last_error"] is None

    # create two mroe backups, verify we see the error again
    await ha.create(CreateOptions(time.now(), "Name1"))
    await ha.create(CreateOptions(time.now(), "Name2"))
    status = await reader.getjson("sync")
    assert len(status['backups']) == 3
    assert status["last_error"]["error_type"] == ERROR_MULTIPLE_DELETES
    assert status["last_error"]["data"] == {
        SOURCE_GOOGLE_DRIVE: 0,
        SOURCE_HA: 2
    }


@pytest.mark.asyncio
async def test_update_multiple_deletes_setting(reader, ui_server, server, config: Config, time: FakeTime, ha: HaSource, global_info: GlobalInfo):
    assert await reader.getjson("confirmdelete?always=true") == {
        'message': 'Configuration updated, I\'ll never ask again'
    }
    assert not config.get(Setting.CONFIRM_MULTIPLE_DELETES)


@pytest.mark.asyncio
async def test_resolve_folder_reuse(reader, config: Config, backup, time, drive):
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
async def test_resolve_folder_new(reader, config: Config, backup, time, drive):
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
async def test_ssl_server(reader: ReaderHelper, ui_server: UiServer, config, server, cleandir, restarter):
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
        "backup_folder": "unused"
    }
    assert ui_server._starts == 1
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}
    await restarter.waitForRestart()
    assert ui_server._starts == 2


@pytest.mark.asyncio
async def test_bad_ssl_config_missing_files(reader: ReaderHelper, ui_server: UiServer, config, server, cleandir, restarter):
    update = {
        "config": {
            "use_ssl": True,
            "expose_extra_server": True,
            "certfile": join(cleandir, "localhost.crt"),
            "keyfile": join(cleandir, "localhost.key")
        },
        "backup_folder": "unused"
    }
    assert ui_server._starts == 1
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}
    await restarter.waitForRestart()
    assert ui_server._starts == 2

    # Verify the ingress endpoint is still up, but not the SSL one
    await reader.getjson("getstatus")
    with pytest.raises(aiohttp.client_exceptions.ClientConnectionError):
        await reader.getjson("getstatus", ingress=False, ssl=True, sslcontext=False)


@pytest.mark.asyncio
async def test_bad_ssl_config_wrong_files(reader: ReaderHelper, ui_server: UiServer, config, server, cleandir, restarter):
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
        "backup_folder": "unused"
    }
    assert ui_server._starts == 1
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}
    await restarter.waitForRestart()
    assert ui_server._starts == 2

    # Verify the ingress endpoint is still up, but not the SSL one
    await reader.getjson("getstatus")
    with pytest.raises(aiohttp.client_exceptions.ClientConnectionError):
        await reader.getjson("getstatus", ingress=False, ssl=True, sslcontext=False)


@pytest.mark.asyncio
async def test_download_drive(reader, ui_server, backup, drive: DriveSource, ha: HaSource, session, time):
    await ha.delete(backup)
    # download the item from Google Drive
    from_drive = await drive.read(backup)
    # Download rom the web server
    from_server = AsyncHttpGetter(
        reader.getUrl() + "download?slug=" + backup.slug(), {}, session, time=time)
    await compareStreams(from_drive, from_server)


@pytest.mark.asyncio
async def test_download_home_assistant(reader: ReaderHelper, ui_server, backup, drive: DriveSource, ha: HaSource, session, time):
    await drive.delete(backup)
    # download the item from Google Drive
    from_ha = await ha.read(backup)
    # Download rom the web server
    from_server = AsyncHttpGetter(
        reader.getUrl() + "download?slug=" + backup.slug(), {}, session, time=time)
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
    creds = {
        "client_id": "new_access_token",
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "token_expiry": "2022-01-01T00:00:00"
    }
    serialized = str(base64.b64encode(json.dumps(creds).encode("utf-8")), "utf-8")
    await reader.get("token?creds={0}&host={1}".format(quote(serialized), quote(reader.getUrl(True))))
    assert drive.drivebackend.creds.access_token == 'new_access_token'
    assert drive.drivebackend.creds.refresh_token == 'new_refresh_token'
    assert drive.drivebackend.creds.secret is None


@pytest.mark.asyncio
async def test_token_with_secret(reader: ReaderHelper, coord: Coordinator, ha, drive: DriveSource):
    creds = {
        "client_id": "new_access_token",
        "client_secret": "new_client_secret",
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "token_expiry": "2022-01-01T00:00:00"
    }
    serialized = str(base64.b64encode(json.dumps(creds).encode("utf-8")), "utf-8")
    await reader.get("token?creds={0}&host={1}".format(quote(serialized), quote(reader.getUrl(True))))
    assert drive.drivebackend.creds.access_token == 'new_access_token'
    assert drive.drivebackend.creds.refresh_token == 'new_refresh_token'
    assert drive.drivebackend.creds.secret == 'new_client_secret'


@pytest.mark.asyncio
async def test_token_extra_server(reader: ReaderHelper, coord: Coordinator, ha, drive: DriveSource, restarter, time):
    update = {
        "config": {
            "expose_extra_server": True
        },
        "backup_folder": "unused"
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}
    await restarter.waitForRestart()
    creds = Creds(time, "id", time.now(), "token", "refresh")
    serialized = str(base64.b64encode(json.dumps(creds.serialize()).encode("utf-8")), "utf-8")
    await reader.get("token?creds={0}&host={1}".format(quote(serialized), quote(reader.getUrl(False))), ingress=False)
    assert drive.drivebackend.creds.access_token == 'token'


@pytest.mark.asyncio
async def test_changefolder(reader: ReaderHelper, coord: Coordinator, ha, ui_server, folder_finder: FolderFinder):
    assert await reader.get("changefolder?id=12345") == '{}'
    assert await folder_finder.get() == "12345"


@pytest.mark.asyncio
async def test_changefolder_extra_server(reader: ReaderHelper, coord: Coordinator, ha, drive: DriveSource, restarter, ui_server, folder_finder: FolderFinder):
    update = {
        "config": {
            "expose_extra_server": True
        },
        "backup_folder": "unused"
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}
    await restarter.waitForRestart()

    # create a folder
    folder_metadata = {
        'name': "Other Folder",
        'mimeType': FOLDER_MIME_TYPE,
        'appProperties': {
            "backup_folder": "true",
        },
    }

    # create two folders at different times
    id = (await drive.drivebackend.createFolder(folder_metadata))['id']

    await reader.get("changefolder?id=" + str(id), ingress=False)
    assert await folder_finder.get() == id


@pytest.mark.asyncio
async def test_update_sync_interval(reader, ui_server, config: Config, supervisor: SimulatedSupervisor):
    # Make sure the default saves nothing
    update = {
        "config": {
            "max_sync_interval_seconds": '1 hour',
        },
        "backup_folder": "unused"
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}
    assert config.get(Setting.MAX_SYNC_INTERVAL_SECONDS) == 60 * 60
    assert "max_sync_interval_seconds" not in supervisor._options

    # Update custom
    update = {
        "config": {
            "max_sync_interval_seconds": '2 hours',
        },
        "backup_folder": "unused"
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}
    assert config.get(Setting.MAX_SYNC_INTERVAL_SECONDS) == 60 * 60 * 2
    assert supervisor._options["max_sync_interval_seconds"] == 60 * 60 * 2


@pytest.mark.asyncio
async def test_manual_creds(reader: ReaderHelper, ui_server: UiServer, config: Config, server: SimulationServer, session, drive: DriveSource):
    periodic_check = await reader.getjson("checkManualAuth")
    assert periodic_check['message'] == "No request for authorization is in progress."
    drive.saveCreds(None)
    assert not drive.enabled()

    # get the auth url
    req_path = URL("manualauth").with_query({
        "client_id": server.google._custom_drive_client_id,
        "client_secret": server.google._custom_drive_client_secret})
    data = await reader.getjson(str(req_path))
    assert "auth_url" in data
    assert "code" in data
    assert "expires" in data

    periodic_check = await reader.getjson("checkManualAuth")
    assert periodic_check['message'] == "Waiting for you to authorize the add-on."

    # Authorize the device using the url and device code provided
    authorize_url = URL(data["auth_url"]).with_query({"code": data['code']})
    async with session.get(str(authorize_url), allow_redirects=False) as resp:
        resp.raise_for_status()

    # TODO: Wait for new credentials in a smarter way.
    await asyncio.sleep(2)

    # verify creds are saved and drive is enabled
    assert drive.enabled()


@pytest.mark.asyncio
async def test_manual_creds_failure(reader: ReaderHelper, ui_server: UiServer, config: Config, server: SimulationServer, session, drive: DriveSource):
    drive.saveCreds(None)
    assert not drive.enabled()

    # Try with a bad client_id
    req_path = URL("manualauth").with_query({
        "client_id": "wrong_id",
        "client_secret": server.google._custom_drive_client_secret})
    data = await reader.getjson(str(req_path), status=500)
    assert data["message"] == "Google responded with error status HTTP 401.  Please verify your credentials are set up correctly."

    # Try with a bad client_secret
    req_path = URL("manualauth").with_query({
        "client_id": server.google._custom_drive_client_id,
        "client_secret": "wrong_secret"})
    data = await reader.getjson(str(req_path))

    await asyncio.sleep(2)

    periodic_check = await reader.getjson("checkManualAuth", status=500)
    assert periodic_check['message'] == "Failed unexpectedly while trying to reach Google.  See the add-on logs for details."

    # verify creds are saved and drive is enabled
    assert not drive.enabled()


@pytest.mark.asyncio
async def test_setting_cancels_and_resyncs(reader: ReaderHelper, ui_server: UiServer, config: Config, server, session, drive: DriveSource, coord: Coordinator):
    # Create a blocking sync task
    coord._sync_wait.set()
    sync = asyncio.create_task(coord.sync(), name="Sync from saving settings")
    await coord._sync_start.wait()
    assert not sync.cancelled()
    assert not sync.done()

    # Change some config
    update = {
        "config": {
            "days_between_backups": 20,
            "drive_ipv4": ""
        },
        "backup_folder": "unused"
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}

    # verify the previous sync is done and another one is running
    assert sync.done()
    assert coord.isSyncing()


@pytest.mark.asyncio
async def test_change_specify_folder_setting(reader: ReaderHelper, server, session, coord: Coordinator, folder_finder: FolderFinder):
    await coord.sync()
    assert folder_finder.getCachedFolder() is not None

    old_folder = folder_finder.getCachedFolder()
    # Change some config
    update = {
        "config": {
            "specify_backup_folder": True
        },
        "backup_folder": ""
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}

    # verify the backup folder was reset, which triggers the error dialog to find a new folder
    assert folder_finder.getCachedFolder() == old_folder

    await coord.waitForSyncToFinish()
    result = await reader.postjson("getstatus")
    assert result["last_error"] is None


@pytest.mark.asyncio
async def test_change_specify_folder_setting_with_manual_creds(reader: ReaderHelper, google: SimulatedGoogle, session, coord: Coordinator, folder_finder: FolderFinder, drive: DriveSource, config):
    google.resetDriveAuth()
    drive.saveCreds(None)
    assert not drive.enabled()

    # get the auth url
    req_path = URL("manualauth").with_query({
        "client_id": google._custom_drive_client_id,
        "client_secret": google._custom_drive_client_secret})
    data = await reader.getjson(str(req_path))

    # Authorize the device using the url and device code provided
    authorize_url = URL(data["auth_url"]).with_query({"code": data['code']})
    async with session.get(str(authorize_url), allow_redirects=False) as resp:
        resp.raise_for_status()

    # TODO: wait for creds in a smarter way
    await asyncio.sleep(2)

    assert drive.enabled()
    assert drive.isCustomCreds()

    await coord.sync()
    assert folder_finder.getCachedFolder() is not None

    # Specify the backup folder, which should cache the new one
    update = {
        "config": {
            Setting.SPECIFY_BACKUP_FOLDER.value: True
        },
        "backup_folder": "12345"
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}
    assert folder_finder.getCachedFolder() == "12345"

    # Un change the folder, which should keep the existing folder
    update = {
        "config": {
            Setting.SPECIFY_BACKUP_FOLDER.value: False
        },
        "backup_folder": ""
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}
    assert folder_finder.getCachedFolder() == "12345"


@pytest.mark.asyncio
async def test_update_non_ui_setting(reader: ReaderHelper, server, session, coord: Coordinator, folder_finder: FolderFinder, config: Config):
    await coord.sync()
    # Change some config
    update = {
        "config": {
            Setting.NEW_BACKUP_TIMEOUT_SECONDS.value: 10
        },
        "backup_folder": ""
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}

    assert config.get(Setting.NEW_BACKUP_TIMEOUT_SECONDS) == 10

    update = {
        "config": {
            Setting.MAX_BACKUPS_IN_HA.value: 1
        },
        "backup_folder": ""
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": False}
    assert config.get(Setting.NEW_BACKUP_TIMEOUT_SECONDS) == 10


@pytest.mark.asyncio
async def test_update_disable_drive(reader: ReaderHelper, server, coord: Coordinator, config: Config, drive_requests: DriveRequests):
    # Disable drive
    drive_requests.creds = None
    os.remove(config.get(Setting.CREDENTIALS_FILE_PATH))
    assert not coord.enabled()
    await coord.sync()
    assert len(coord.backups()) == 0

    # Disable Drive Upload
    update = {
        "config": {
            Setting.ENABLE_DRIVE_UPLOAD.value: False
        },
        "backup_folder": ""
    }
    assert await reader.postjson("saveconfig", json=update) == {'message': 'Settings saved', "reload_page": True}
    assert config.get(Setting.ENABLE_DRIVE_UPLOAD) is False

    # Verify the app is working fine.
    assert coord.enabled()
    await coord.waitForSyncToFinish()
    assert len(coord.backups()) == 1


@pytest.mark.asyncio
async def test_update_ignore(reader: ReaderHelper, time: FakeTime, coord: Coordinator, config: Config, supervisor: SimulatedSupervisor, ha: HaSource, drive: DriveSource):
    config.override(Setting.IGNORE_UPGRADE_BACKUPS, True)
    config.override(Setting.DAYS_BETWEEN_BACKUPS, 0)

    # make an ignored_backup
    slug = await supervisor.createBackup({'name': "Ignore_me", 'folders': ['homeassistant'], 'addons': []}, date=time.now())

    await coord.sync()
    assert len(await drive.get()) == 0
    assert len(await ha.get()) == 1
    assert len(coord.backups()) == 1

    # Disable Drive Upload
    update = {
        "ignore": False,
        "slug": slug,
    }
    await reader.postjson("ignore", json=update)
    await coord.waitForSyncToFinish()
    assert len(coord.backups()) == 1
    assert len(await drive.get()) == 1
    assert len(await ha.get()) == 1


@pytest.mark.asyncio
async def test_check_ignored_backup_notification(reader: ReaderHelper, time: FakeTime, coord: Coordinator, config: Config, supervisor: SimulatedSupervisor, ha: HaSource, drive: DriveSource):
    # Create an "ignored" backup after upgrade to the current version.
    time.advance(days=1)
    await supervisor.createBackup({'name': "test_name"}, date=time.now())

    # cerate one that isn't ignored.
    time.advance(days=1)
    await ha.create(CreateOptions(time.now(), name_template=None))

    update = {
        "config": {
            Setting.IGNORE_OTHER_BACKUPS.value: True
        },
        "backup_folder": ""
    }
    await reader.postjson("saveconfig", json=update)
    await coord.waitForSyncToFinish()

    status = await reader.getjson("getstatus")
    assert status["backups"][0]["ignored"]
    assert not status["backups"][1]["ignored"]
    assert not status["notify_check_ignored"]

    # Create an ignored backup from "before" the addon was upgraded to v0.104.0
    await supervisor.createBackup({'name': "test_name"}, date=time.now() - timedelta(days=10))
    await coord.sync()

    # The UI should nofify about checking ignored backups
    status = await reader.getjson("getstatus")
    assert status["backups"][0]["ignored"]
    assert status["backups"][1]["ignored"]
    assert not status["backups"][2]["ignored"]
    assert status["notify_check_ignored"]

    # Acknowledge the notification
    await reader.postjson("ackignorecheck") == {'message': "Acknowledged."}
    status = await reader.getjson("getstatus")
    assert not status["notify_check_ignored"]


@pytest.mark.asyncio
async def test_snapshot_to_backup_upgrade_use_new_values(reader: ReaderHelper, time: FakeTime, coord: Coordinator, config: Config, supervisor: SimulatedSupervisor, ha: HaSource, drive: DriveSource, data_cache: DataCache, updater: HaUpdater):
    """ Test the path where a user upgrades from the addon before the backup rename and then chooses to use the new names"""
    status = await reader.getjson("getstatus")
    assert not status["warn_backup_upgrade"]

    # simulate upgrading config
    supervisor._options = {
        Setting.DEPRECTAED_MAX_BACKUPS_IN_HA.value: 7
    }
    await coord.sync()
    assert Setting.CALL_BACKUP_SNAPSHOT.value in supervisor._options
    assert Setting.DEPRECTAED_MAX_BACKUPS_IN_HA.value not in supervisor._options
    assert config.get(Setting.CALL_BACKUP_SNAPSHOT)

    status = await reader.getjson("getstatus")
    assert status["warn_backup_upgrade"]
    assert not data_cache.checkFlag(UpgradeFlags.NOTIFIED_ABOUT_BACKUP_RENAME)
    assert not updater._trigger_once

    # simulate user clicking the button to use new names
    assert await reader.getjson("callbackupsnapshot?switch=true") == {'message': 'Configuration updated'}
    assert data_cache.checkFlag(UpgradeFlags.NOTIFIED_ABOUT_BACKUP_RENAME)
    assert not config.get(Setting.CALL_BACKUP_SNAPSHOT)
    status = await reader.getjson("getstatus")
    assert not status["warn_backup_upgrade"]
    assert updater._trigger_once


@pytest.mark.asyncio
async def test_snapshot_to_backup_upgrade_use_old_values(reader: ReaderHelper, time: FakeTime, coord: Coordinator, config: Config, supervisor: SimulatedSupervisor, ha: HaSource, drive: DriveSource, data_cache: DataCache, updater: HaUpdater):
    """ Test the path where a user upgrades from the addon before the backup rename and then chooses to use the old names"""
    status = await reader.getjson("getstatus")
    assert not status["warn_backup_upgrade"]

    # simulate upgrading config
    supervisor._options = {
        Setting.DEPRECTAED_MAX_BACKUPS_IN_HA.value: 7
    }
    await coord.sync()
    assert Setting.CALL_BACKUP_SNAPSHOT.value in supervisor._options
    assert config.get(Setting.CALL_BACKUP_SNAPSHOT)

    status = await reader.getjson("getstatus")
    assert status["warn_backup_upgrade"]
    assert not data_cache.checkFlag(UpgradeFlags.NOTIFIED_ABOUT_BACKUP_RENAME)
    assert not updater._trigger_once

    # simulate user clicking the button to use new names
    assert await reader.getjson("callbackupsnapshot?switch=false") == {'message': 'Configuration updated'}
    assert data_cache.checkFlag(UpgradeFlags.NOTIFIED_ABOUT_BACKUP_RENAME)
    status = await reader.getjson("getstatus")
    assert not status["warn_backup_upgrade"]
    assert config.get(Setting.CALL_BACKUP_SNAPSHOT)


@pytest.mark.asyncio
async def test_snapshot_to_backup_upgrade_avoid_default_overwrite(reader: ReaderHelper, time: FakeTime, coord: Coordinator, config: Config, supervisor: SimulatedSupervisor, ha: HaSource, drive: DriveSource, data_cache: DataCache, updater: HaUpdater):
    """ Test the path where a user upgrades from the addon but a new value with a default value gets overwritten"""
    status = await reader.getjson("getstatus")
    assert not status["warn_backup_upgrade"]

    # simulate upgrading config
    supervisor._options = {
        Setting.DEPRECTAED_MAX_BACKUPS_IN_HA.value: 7,
        Setting.MAX_BACKUPS_IN_HA.value: 4  # defuault, should get overridden
    }
    await coord.sync()
    assert Setting.CALL_BACKUP_SNAPSHOT.value in supervisor._options
    assert config.get(Setting.CALL_BACKUP_SNAPSHOT)
    assert config.get(Setting.MAX_BACKUPS_IN_HA) == 7


@pytest.mark.asyncio
async def test_ha_upload(reader: ReaderHelper, backup_helper, ui_server: UiServer, drive: DriveSource, ha: HaSource, config: Config, model, time):
    from_backup, data = await backup_helper.createFile()
    backup = await drive.save(from_backup, data)

    config.override(Setting.DAYS_BETWEEN_BACKUPS, 0)
    await model.sync(time.now())
    assert len(await ha.get()) == 0
    assert len(await drive.get()) == 1

    reply = await reader.getjson(str(URL("upload").with_query({"slug": backup.slug()})))
    assert reply['message'] == "Uploading backup in the background"
    await ui_server.waitForUpload()
    assert len(await ha.get()) == 1
