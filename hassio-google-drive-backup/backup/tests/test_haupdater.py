from ..haupdater import HaUpdater
from ..globalinfo import GlobalInfo
from .faketime import FakeTime
from ..dev.testbackend import TestBackend

STALE_ATTRIBUTES = { 
    "device_class": "problem",
    "friendly_name": "Snapshots Stale"
}


def test_init(updater: HaUpdater, global_info, server):
    backend: TestBackend = server.getServer()
    updater.update()
    assert not updater._stale()
    assert updater._state() == "waiting"
    verifyEntity(backend, "binary_sensor.snapshots_stale", False, STALE_ATTRIBUTES)
    verifyEntity(backend, "sensor.snapshot_backup", "waiting", {
        'friendly_name': 'Snapshot State',
        'last_snapshot': 'Never',
        'snapshots': [],
        'snapshots_in_google_drive': 0,
        'snapshots_in_hassio': 0
    })
    assert backend.getNotification() is None

    global_info.success()
    assert not updater._stale()
    assert updater._state() == "backed_up"


def test_init_failure(updater: HaUpdater, global_info: GlobalInfo, time: FakeTime, server):
    backend: TestBackend = server.getServer()
    updater.update()
    assert not updater._stale()
    assert updater._state() == "waiting"

    global_info.failed(Exception())
    assert not updater._stale()
    assert updater._state() == "backed_up"
    assert backend.getNotification() is None

    time.advanceDay()
    assert updater._stale()
    assert updater._state() == "error"
    updater.update()
    assert backend.getNotification() == {
        'message': 'The add-on is having trouble backing up your snapshots and needs attention.  Please visit the add-on status page for details.',
        'title': 'Hass.io Google Drive Backup is Having Trouble',
        'notification_id': 'backup_broken'
    }


def test_failure_backoff_502(updater: HaUpdater, server, time: FakeTime):
    backend: TestBackend = server.getServer()
    backend.setHomeAssistantError(502)
    for x in range(9):
        updater.update()
    assert updater._ha_offline
    assert time.sleeps == [20, 40, 80, 160, 300, 300, 300, 300, 300]

    backend.setHomeAssistantError(None)
    updater.update()
    assert not updater._ha_offline

def test_failure_backoff_510(updater: HaUpdater, server, time: FakeTime):
    backend: TestBackend = server.getServer()
    backend.setHomeAssistantError(510)
    for x in range(9):
        updater.update()
    assert updater._ha_offline
    assert time.sleeps == [20, 40, 80, 160, 300, 300, 300, 300, 300]

    backend.setHomeAssistantError(None)
    updater.update()
    assert not updater._ha_offline


def test_failure_backoff_other(updater: HaUpdater, server, time: FakeTime):
    backend: TestBackend = server.getServer()
    backend.setHomeAssistantError(400)
    for x in range(9):
        updater.update()
    assert not updater._ha_offline
    assert time.sleeps == [20, 40, 80, 160, 300, 300, 300, 300, 300]
    backend.setHomeAssistantError(None)
    updater.update()
    assert not updater._ha_offline


def test_update_snapshots(updater: HaUpdater, server, time: FakeTime):
    backend: TestBackend = server.getServer()
    updater.update()
    assert not updater._stale()
    assert updater._state() == "waiting"
    verifyEntity(backend, "binary_sensor.snapshots_stale", False, STALE_ATTRIBUTES)
    verifyEntity(backend, "sensor.snapshot_backup", "waiting", {
        'friendly_name': 'Snapshot State',
        'last_snapshot': 'Never',
        'snapshots': [],
        'snapshots_in_google_drive': 0,
        'snapshots_in_hassio': 0
    })


def test_notification_link(updater: HaUpdater, server, time: FakeTime, global_info):
    backend: TestBackend = server.getServer()
    updater.update()
    assert not updater._stale()
    assert updater._state() == "waiting"
    verifyEntity(backend, "binary_sensor.snapshots_stale", False, STALE_ATTRIBUTES)
    verifyEntity(backend, "sensor.snapshot_backup", "waiting", {
        'friendly_name': 'Snapshot State',
        'last_snapshot': 'Never',
        'snapshots': [],
        'snapshots_in_google_drive': 0,
        'snapshots_in_hassio': 0
    })
    assert backend.getNotification() is None

    global_info.failed(Exception())
    global_info.url = "http://localhost/test"
    time.advanceDay()
    updater.update()
    assert backend.getNotification() == {
        'message': 'The add-on is having trouble backing up your snapshots and needs attention.  Please visit the add-on [status page](http://localhost/test) for details.',
        'title': 'Hass.io Google Drive Backup is Having Trouble',
        'notification_id': 'backup_broken'
    }


def test_notification_clears(updater: HaUpdater, server, time: FakeTime, global_info):
    backend: TestBackend = server.getServer()
    updater.update()
    assert not updater._stale()
    assert updater._state() == "waiting"
    assert backend.getNotification() is None

    global_info.failed(Exception())
    time.advanceDay()
    updater.update()
    assert backend.getNotification() is not None

    global_info.success()
    updater.update()
    assert backend.getNotification() is None


def test_publish_for_failure(updater: HaUpdater, server, time: FakeTime, global_info: GlobalInfo):
    backend: TestBackend = server.getServer()
    global_info.success()
    updater.update()
    assert backend.getNotification() is None

    time.advanceDay()
    global_info.failed(Exception())
    updater.update()
    assert backend.getNotification() is not None

    time.advanceDay()
    global_info.failed(Exception())
    updater.update()
    assert backend.getNotification() is not None

    global_info.success()
    updater.update()
    assert backend.getNotification() is None


def verifyEntity(backend, name, state, attributes):
    assert backend.getEntity(name) == state
    assert backend.getAttributes(name) == attributes
