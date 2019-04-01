import pytest
import mock 

from ..engine import Engine
from ..time import Time
from ..drive import Drive
from ..hassio import Hassio
from ..config import Config
from ..snapshots import Snapshot, HASnapshot, DriveSnapshot
from pytest_mock import mocker
from datetime import datetime, timedelta, timezone
from dateutil.tz import gettz

base_date: datetime = datetime(1985, 12, 6, 1, 0, 0, tzinfo=timezone.utc)
next_minute: datetime = datetime(1985, 12, 6, 1, 1, 0, tzinfo=timezone.utc)
prev_minute: datetime = datetime(1985, 12, 6, 0, 59, 0, tzinfo=timezone.utc)
next_day: datetime = datetime(1985, 12, 7, 1, 0, 0, tzinfo=timezone.utc)
test_tz=gettz('Egypt Standard Time')
def test_engine_no_work_do_nothing(mocker) -> None:
    time: Time = getMockTime(mocker)
    config: Config = Config([])
    drive: Drive = Drive(config)
    hassio: Hassio = getMockHassio(mocker, config)

    engine: Engine = Engine(config, drive, hassio, time)
    engine.doBackupWorkflow()

    assert len(engine.snapshots) == 0
    hassio.readSnapshots.assert_called_with()

def test_read_hassio_snapshots(mocker) -> None:
    snapshot = makeHASnapshot("test", datetime.now())
    time: Time = getMockTime(mocker)
    config: Config = Config([])
    drive: Drive = Drive(config)
    hassio: Hassio = getMockHassio(mocker, config, snapshots=[snapshot])

    engine: Engine = Engine(config, drive, hassio, time)
    engine.doBackupWorkflow()

    hassio.readSnapshots.assert_called_with()
    assert len(engine.snapshots) == 1
    assert engine.snapshots[0].ha == snapshot
    assert engine.snapshots[0].driveitem is None

def test_next_backup_time(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config: Config = Config([])
    drive: Drive = Drive(config)
    
    hassio: Hassio = getMockHassio(mocker, config, snapshots=[])

    engine: Engine = Engine(config, drive, hassio, time)
    engine.doBackupWorkflow()
    assert engine.getNextSnapshotTime() == (base_date - timedelta(days = 1))


def test_next_backup_time_old_snapshot(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config: Config = Config([])
    drive: Drive = Drive(config)

    old_snapshot = makeHASnapshot("test", base_date)
    hassio: Hassio = getMockHassio(mocker, config, snapshots=[old_snapshot])

    engine: Engine = Engine(config, drive, hassio, time)
    engine.doBackupWorkflow()
    assert engine.getNextSnapshotTime() == (base_date + timedelta(days=config.daysBetweenSnapshots()))

def test_next_backup_time_new_snapshot(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config: Config = Config([])
    drive: Drive = Drive(config)
    
    new_snapshot = makeHASnapshot("test", base_date + timedelta(days=2))
    hassio: Hassio = getMockHassio(mocker, config, snapshots=[new_snapshot])

    engine: Engine = Engine(config, drive, hassio, time)
    engine.doBackupWorkflow()
    assert engine.getNextSnapshotTime() == (base_date + timedelta(days=2) + timedelta(days=config.daysBetweenSnapshots()))

def test_next_backup_time_with_snapshot_time_before_snapshot(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config: Config = Config(extra_config={"snapshot_time_of_day": "01:00", "days_between_snapshots" : 1})
    drive: Drive = Drive(config)
    
    date_local = datetime(1928, 12, 6, 0, 59, tzinfo=test_tz)
    new_snapshot = makeHASnapshot("test", time.toUtc(date_local))
    hassio: Hassio = getMockHassio(mocker, config, snapshots=[new_snapshot])

    engine: Engine = Engine(config, drive, hassio, time)
    engine.doBackupWorkflow()
    assert engine.getNextSnapshotTime() == datetime(1928, 12, 6, 1, 00, tzinfo=test_tz)


def test_next_backup_time_with_snapshot_time_after_snapshot(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config: Config = Config(extra_config={"snapshot_time_of_day": "01:00", "days_between_snapshots" : 1})
    drive: Drive = Drive(config)
    
    date_local = datetime(1928, 12, 6, 1, 1, tzinfo=test_tz)
    new_snapshot = makeHASnapshot("test", time.toUtc(date_local))
    hassio: Hassio = getMockHassio(mocker, config, snapshots=[new_snapshot])

    engine: Engine = Engine(config, drive, hassio, time)
    engine.doBackupWorkflow()
    assert engine.getNextSnapshotTime() == datetime(1928, 12, 7, 1, 00, tzinfo=test_tz)

def test_next_backup_time_with_broken_time_of_day(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config: Config = Config(extra_config={"snapshot_time_of_day": "24:00", "days_between_snapshots" : 1})
    drive: Drive = Drive(config)
    
    date_local = datetime(1928, 12, 6, 1, 1, tzinfo=test_tz)
    new_snapshot = makeHASnapshot("test", time.toUtc(date_local))
    hassio: Hassio = getMockHassio(mocker, config, snapshots=[new_snapshot])

    engine: Engine = Engine(config, drive, hassio, time)
    engine.doBackupWorkflow()
    assert engine.getNextSnapshotTime() == date_local + timedelta(days=1)


def getMockHassio(mocker, config: Config, snapshots=[]):
    hassio: Hassio = Hassio(config)
    mocker.patch.object(hassio, 'readAddonInfo')
    hassio.readAddonInfo.return_value = {"web_ui": "http://test"}

    mocker.patch.object(hassio, 'readHostInfo')
    hassio.readAddonInfo.return_value = {"hostname": "localhost"}

    mocker.patch.object(hassio, 'deleteSnapshot')
    mocker.patch.object(hassio, 'readSnapshots')
    hassio.readSnapshots.return_value = snapshots

    mocker.patch.object(hassio, 'sendNotification')
    mocker.patch.object(hassio, 'dismissNotification')
    mocker.patch.object(hassio, 'updateSnapshotStaleSensor')
    mocker.patch.object(hassio, 'updateSnapshotsSensor')
    mocker.patch.object(hassio, 'sendNotification')
    return hassio

def getMockTime(mocker, mock_time=datetime.now()):
    time: Time = Time(local_tz=test_tz)
    mocker.patch.object(time, 'now')
    time.now.return_value = mock_time

    mocker.patch.object(time, 'nowLocal')
    time.nowLocal.return_Value = time.toLocal(mock_time)
    return time

def makeHASnapshot(slug, date, name=None) -> HASnapshot:
    if not name:
        name = slug
    snapshot = HASnapshot({"slug": slug, "date": str(date), "name": name})
    return snapshot