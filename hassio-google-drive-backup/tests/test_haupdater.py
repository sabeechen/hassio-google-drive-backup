import pytest

from backup.util import GlobalInfo
from backup.ha import HaUpdater
from backup.ha.haupdater import REASSURING_MESSAGE
from backup.logbase import LogBase
from .faketime import FakeTime
from .helpers import HelperTestSource
from dev.simulationserver import SimulationServer

STALE_ATTRIBUTES = {
    "friendly_name": "Snapshots Stale"
}


@pytest.fixture
def source():
    return HelperTestSource("Source")


@pytest.fixture
def dest():
    return HelperTestSource("Dest")


@pytest.mark.asyncio
async def test_init(updater: HaUpdater, global_info, server):
    await updater.update()
    assert not updater._stale()
    assert updater._state() == "waiting"
    verifyEntity(server, "binary_sensor.snapshots_stale",
                 False, STALE_ATTRIBUTES)
    verifyEntity(server, "sensor.snapshot_backup", "waiting", {
        'friendly_name': 'Snapshot State',
        'last_snapshot': 'Never',
        'snapshots': [],
        'snapshots_in_google_drive': 0,
        'snapshots_in_hassio': 0
    })
    assert server.getNotification() is None

    global_info.success()
    assert not updater._stale()
    assert updater._state() == "backed_up"


@pytest.mark.asyncio
async def test_init_failure(updater: HaUpdater, global_info: GlobalInfo, time: FakeTime, server):
    await updater.update()
    assert not updater._stale()
    assert updater._state() == "waiting"

    global_info.failed(Exception())
    assert not updater._stale()
    assert updater._state() == "backed_up"
    assert server.getNotification() is None

    time.advanceDay()
    assert updater._stale()
    assert updater._state() == "error"
    await updater.update()
    assert server.getNotification() == {
        'message': 'The add-on is having trouble backing up your snapshots and needs attention.  Please visit the add-on status page for details.',
        'title': 'Hass.io Google Drive Backup is Having Trouble',
        'notification_id': 'backup_broken'
    }


@pytest.mark.asyncio
async def test_failure_backoff_502(updater: HaUpdater, server, time: FakeTime):
    server.setHomeAssistantError(502)
    for x in range(9):
        await updater.update()
    assert time.sleeps == [60, 120, 240, 300, 300, 300, 300, 300, 300]

    server.setHomeAssistantError(None)
    await updater.update()
    assert time.sleeps == [60, 120, 240, 300, 300, 300, 300, 300, 300]


@pytest.mark.asyncio
async def test_failure_backoff_510(updater: HaUpdater, server, time: FakeTime):
    server.setHomeAssistantError(510)
    for x in range(9):
        await updater.update()
    assert time.sleeps == [60, 120, 240, 300, 300, 300, 300, 300, 300]

    server.setHomeAssistantError(None)
    await updater.update()
    assert time.sleeps == [60, 120, 240, 300, 300, 300, 300, 300, 300]


@pytest.mark.asyncio
async def test_failure_backoff_other(updater: HaUpdater, server, time: FakeTime):
    server.setHomeAssistantError(400)
    for x in range(9):
        await updater.update()
    assert time.sleeps == [60, 120, 240, 300, 300, 300, 300, 300, 300]
    server.setHomeAssistantError(None)
    await updater.update()
    assert time.sleeps == [60, 120, 240, 300, 300, 300, 300, 300, 300]


@pytest.mark.asyncio
async def test_update_snapshots(updater: HaUpdater, server, time: FakeTime):
    await updater.update()
    assert not updater._stale()
    assert updater._state() == "waiting"
    verifyEntity(server, "binary_sensor.snapshots_stale",
                 False, STALE_ATTRIBUTES)
    verifyEntity(server, "sensor.snapshot_backup", "waiting", {
        'friendly_name': 'Snapshot State',
        'last_snapshot': 'Never',
        'snapshots': [],
        'snapshots_in_google_drive': 0,
        'snapshots_in_hassio': 0
    })


@pytest.mark.asyncio
async def test_update_snapshots_sync(updater: HaUpdater, server, time: FakeTime, snapshot):
    await updater.update()
    assert not updater._stale()
    assert updater._state() == "backed_up"
    verifyEntity(server, "binary_sensor.snapshots_stale",
                 False, STALE_ATTRIBUTES)
    date = '1985-12-06T05:00:00+00:00'
    verifyEntity(server, "sensor.snapshot_backup", "backed_up", {
        'friendly_name': 'Snapshot State',
        'last_snapshot': date,
        'snapshots': [{
            'date': date,
            'name': snapshot.name(),
            'size': snapshot.sizeString(),
            'state': snapshot.status()
        }
        ],
        'snapshots_in_google_drive': 1,
        'snapshots_in_hassio': 1
    })


@pytest.mark.asyncio
async def test_notification_link(updater: HaUpdater, server, time: FakeTime, global_info):
    await updater.update()
    assert not updater._stale()
    assert updater._state() == "waiting"
    verifyEntity(server, "binary_sensor.snapshots_stale",
                 False, STALE_ATTRIBUTES)
    verifyEntity(server, "sensor.snapshot_backup", "waiting", {
        'friendly_name': 'Snapshot State',
        'last_snapshot': 'Never',
        'snapshots': [],
        'snapshots_in_google_drive': 0,
        'snapshots_in_hassio': 0
    })
    assert server.getNotification() is None

    global_info.failed(Exception())
    global_info.url = "http://localhost/test"
    time.advanceDay()
    await updater.update()
    assert server.getNotification() == {
        'message': 'The add-on is having trouble backing up your snapshots and needs attention.  Please visit the add-on [status page](http://localhost/test) for details.',
        'title': 'Hass.io Google Drive Backup is Having Trouble',
        'notification_id': 'backup_broken'
    }


@pytest.mark.asyncio
async def test_notification_clears(updater: HaUpdater, server, time: FakeTime, global_info):
    await updater.update()
    assert not updater._stale()
    assert updater._state() == "waiting"
    assert server.getNotification() is None

    global_info.failed(Exception())
    time.advanceDay()
    await updater.update()
    assert server.getNotification() is not None

    global_info.success()
    await updater.update()
    assert server.getNotification() is None


@pytest.mark.asyncio
async def test_publish_for_failure(updater: HaUpdater, server, time: FakeTime, global_info: GlobalInfo):
    global_info.success()
    await updater.update()
    assert server.getNotification() is None

    time.advanceDay()
    global_info.failed(Exception())
    await updater.update()
    assert server.getNotification() is not None

    time.advanceDay()
    global_info.failed(Exception())
    await updater.update()
    assert server.getNotification() is not None

    global_info.success()
    await updater.update()
    assert server.getNotification() is None


@pytest.mark.asyncio
async def test_failure_logging(updater: HaUpdater, server, time: FakeTime):
    server.setHomeAssistantError(501)
    assert LogBase.getLast() is None
    await updater.update()
    assert LogBase.getLast() is None

    time.advance(minutes=1)
    await updater.update()
    assert LogBase.getLast() is None

    time.advance(minutes=5)
    await updater.update()
    assert LogBase.getLast().msg == REASSURING_MESSAGE.format(501)

    last_log = LogBase.getLast()
    time.advance(minutes=5)
    await updater.update()
    assert LogBase.getLast() is not last_log
    assert LogBase.getLast().msg == REASSURING_MESSAGE.format(501)

    last_log = LogBase.getLast()
    server.setHomeAssistantError(None)
    await updater.update()
    assert LogBase.getLast() is last_log


@pytest.mark.asyncio
@pytest.mark.flaky(reruns=5, reruns_delay=2)
async def test_publish_retries(updater: HaUpdater, server: SimulationServer, time: FakeTime, snapshot, drive):
    await updater.update()
    assert server.getEntity("sensor.snapshot_backup") is not None

    # Shoudlnt update after 59 minutes
    server.clearEntities()
    time.advance(minutes=59)
    await updater.update()
    assert server.getEntity("sensor.snapshot_backup") is None

    # after that it should
    server.clearEntities()
    time.advance(minutes=2)
    await updater.update()
    assert server.getEntity("sensor.snapshot_backup") is not None

    server.clearEntities()
    await drive.delete(snapshot)
    await updater.update()
    assert server.getEntity("sensor.snapshot_backup") is not None


def verifyEntity(backend, name, state, attributes):
    assert backend.getEntity(name) == state
    assert backend.getAttributes(name) == attributes
