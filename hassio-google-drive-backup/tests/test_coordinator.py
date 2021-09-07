import asyncio
from datetime import timedelta

import pytest
from pytest import raises

from backup.config import Config, Setting, CreateOptions
from backup.exceptions import LogicError, LowSpaceError, NoBackup, PleaseWait, UserCancelledError
from backup.util import GlobalInfo, DataCache
from backup.model import Coordinator, Model, Backup
from .conftest import FsFaker
from .faketime import FakeTime
from .helpers import HelperTestSource, skipForWindows


@pytest.fixture
def source():
    return HelperTestSource("Source")


@pytest.fixture
def dest():
    return HelperTestSource("Dest")


@pytest.fixture
def simple_config():
    config = Config()
    config.override(Setting.BACKUP_STARTUP_DELAY_MINUTES, 0)
    return config


@pytest.fixture
def model(source, dest, time, simple_config, global_info, estimator, data_cache: DataCache):
    return Model(simple_config, time, source, dest, global_info, estimator, data_cache)


@pytest.fixture
def coord(model, time, simple_config, global_info, estimator):
    return Coordinator(model, time, simple_config, global_info, estimator)


@pytest.mark.asyncio
async def test_enabled(coord: Coordinator, dest, time):
    dest.setEnabled(True)
    assert coord.enabled()
    dest.setEnabled(False)
    assert not coord.enabled()


@pytest.mark.asyncio
async def test_sync(coord: Coordinator, global_info: GlobalInfo, time: FakeTime):
    await coord.sync()
    assert global_info._syncs == 1
    assert global_info._successes == 1
    assert global_info._last_sync_start == time.now()
    assert len(coord.backups()) == 1


@pytest.mark.asyncio
async def test_blocking(coord: Coordinator):
    # This just makes sure the wait thread is blocked while we do stuff
    event_start = asyncio.Event()
    event_end = asyncio.Event()
    asyncio.create_task(coord._withSoftLock(lambda: sleepHelper(event_start, event_end)))
    await event_start.wait()

    # Make sure PleaseWait gets called on these
    with raises(PleaseWait):
        await coord.delete(None, None)
    with raises(PleaseWait):
        await coord.sync()
    with raises(PleaseWait):
        await coord.uploadBackups(None)
    with raises(PleaseWait):
        await coord.startBackup(None)
    event_end.set()


async def sleepHelper(event_start: asyncio.Event, event_end: asyncio.Event):
    event_start.set()
    await event_end.wait()


@pytest.mark.asyncio
async def test_new_backup(coord: Coordinator, time: FakeTime, source, dest):
    await coord.startBackup(CreateOptions(time.now(), "Test Name"))
    backups = coord.backups()
    assert len(backups) == 1
    assert backups[0].name() == "Test Name"
    assert backups[0].getSource(source.name()) is not None
    assert backups[0].getSource(dest.name()) is None


@pytest.mark.asyncio
async def test_sync_error(coord: Coordinator, global_info: GlobalInfo, time: FakeTime, model):
    error = Exception("BOOM")
    old_sync = model.sync
    model.sync = lambda s: doRaise(error)
    await coord.sync()
    assert global_info._last_error is error
    assert global_info._last_failure_time == time.now()
    assert global_info._successes == 0
    model.sync = old_sync
    await coord.sync()
    assert global_info._last_error is None
    assert global_info._successes == 1
    assert global_info._last_success == time.now()
    await coord.sync()


def doRaise(error):
    raise error


@pytest.mark.asyncio
async def test_delete(coord: Coordinator, backup, source, dest):
    assert backup.getSource(source.name()) is not None
    assert backup.getSource(dest.name()) is not None
    await coord.delete([source.name()], backup.slug())
    assert len(coord.backups()) == 1
    assert backup.getSource(source.name()) is None
    assert backup.getSource(dest.name()) is not None
    await coord.delete([dest.name()], backup.slug())
    assert backup.getSource(source.name()) is None
    assert backup.getSource(dest.name()) is None
    assert backup.isDeleted()
    assert len(coord.backups()) == 0

    await coord.sync()
    assert len(coord.backups()) == 1
    await coord.delete([source.name(), dest.name()], coord.backups()[0].slug())
    assert len(coord.backups()) == 0


@pytest.mark.asyncio
async def test_delete_errors(coord: Coordinator, source, dest, backup):
    with raises(NoBackup):
        await coord.delete([source.name()], "badslug")
    bad_source = HelperTestSource("bad")
    with raises(NoBackup):
        await coord.delete([bad_source.name()], backup.slug())


@pytest.mark.asyncio
async def test_retain(coord: Coordinator, source, dest, backup):
    assert not backup.getSource(source.name()).retained()
    assert not backup.getSource(dest.name()).retained()
    await coord.retain({
        source.name(): True,
        dest.name(): True
    }, backup.slug())
    assert backup.getSource(source.name()).retained()
    assert backup.getSource(dest.name()).retained()


@pytest.mark.asyncio
async def test_retain_errors(coord: Coordinator, source, dest, backup):
    with raises(NoBackup):
        await coord.retain({source.name(): True}, "badslug")
    bad_source = HelperTestSource("bad")
    with raises(NoBackup):
        await coord.delete({bad_source.name(): True}, backup.slug())


@pytest.mark.asyncio
async def test_freshness(coord: Coordinator, source: HelperTestSource, dest: HelperTestSource, backup: Backup, time: FakeTime):
    source.setMax(2)
    dest.setMax(2)
    await coord.sync()
    assert backup.getPurges() == {
        source.name(): False,
        dest.name(): False
    }

    source.setMax(1)
    dest.setMax(1)
    await coord.sync()
    assert backup.getPurges() == {
        source.name(): True,
        dest.name(): True
    }

    dest.setMax(0)
    await coord.sync()
    assert backup.getPurges() == {
        source.name(): True,
        dest.name(): False
    }

    source.setMax(0)
    await coord.sync()
    assert backup.getPurges() == {
        source.name(): False,
        dest.name(): False
    }

    source.setMax(2)
    dest.setMax(2)
    time.advance(days=7)
    await coord.sync()
    assert len(coord.backups()) == 2
    assert backup.getPurges() == {
        source.name(): True,
        dest.name(): True
    }
    assert coord.backups()[1].getPurges() == {
        source.name(): False,
        dest.name(): False
    }

    # should refresh on delete
    source.setMax(1)
    dest.setMax(1)
    await coord.delete([source.name()], backup.slug())
    assert coord.backups()[0].getPurges() == {
        dest.name(): True
    }
    assert coord.backups()[1].getPurges() == {
        source.name(): True,
        dest.name(): False
    }

    # should update on retain
    await coord.retain({dest.name(): True}, backup.slug())
    assert coord.backups()[0].getPurges() == {
        dest.name(): False
    }
    assert coord.backups()[1].getPurges() == {
        source.name(): True,
        dest.name(): True
    }

    # should update on upload
    await coord.uploadBackups(coord.backups()[0].slug())
    assert coord.backups()[0].getPurges() == {
        dest.name(): False,
        source.name(): True
    }
    assert coord.backups()[1].getPurges() == {
        source.name(): False,
        dest.name(): True
    }


@pytest.mark.asyncio
async def test_upload(coord: Coordinator, source: HelperTestSource, dest: HelperTestSource, backup):
    await coord.delete([source.name()], backup.slug())
    assert backup.getSource(source.name()) is None
    await coord.uploadBackups(backup.slug())
    assert backup.getSource(source.name()) is not None

    with raises(LogicError):
        await coord.uploadBackups(backup.slug())

    with raises(NoBackup):
        await coord.uploadBackups("bad slug")

    await coord.delete([dest.name()], backup.slug())
    with raises(NoBackup):
        await coord.uploadBackups(backup.slug())


@pytest.mark.asyncio
async def test_download(coord: Coordinator, source, dest, backup):
    await coord.download(backup.slug())
    await coord.delete([source.name()], backup.slug())
    await coord.download(backup.slug())

    with raises(NoBackup):
        await coord.download("bad slug")


@pytest.mark.asyncio
async def test_backoff(coord: Coordinator, model, source: HelperTestSource, dest: HelperTestSource, backup, time: FakeTime, simple_config: Config):
    assert coord.check()
    simple_config.override(Setting.DAYS_BETWEEN_BACKUPS, 1)
    simple_config.override(Setting.MAX_SYNC_INTERVAL_SECONDS, 60 * 60 * 6)

    assert coord.nextSyncAttempt() == time.now() + timedelta(hours=6)
    assert not coord.check()
    error = Exception("BOOM")
    old_sync = model.sync
    model.sync = lambda s: doRaise(error)
    await coord.sync()

    # first backoff should be 0 seconds
    assert coord.nextSyncAttempt() == time.now()
    assert coord.check()

    # backoff maxes out at 1 hr = 3600 seconds
    for seconds in [10, 20, 40, 80, 160, 320, 640, 1280, 2560, 3600, 3600, 3600]:
        await coord.sync()
        assert coord.nextSyncAttempt() == time.now() + timedelta(seconds=seconds)
        assert not coord.check()
        assert not coord.check()
        assert not coord.check()

    # a good sync resets it back to 6 hours from now
    model.sync = old_sync
    await coord.sync()
    assert coord.nextSyncAttempt() == time.now() + timedelta(hours=6)
    assert not coord.check()

    # if the next backup is less that 6 hours from the last one, that that shoudl be when we sync
    simple_config.override(Setting.DAYS_BETWEEN_BACKUPS, 1.0 / 24.0)
    assert coord.nextSyncAttempt() == time.now() + timedelta(hours=1)
    assert not coord.check()

    time.advance(hours=2)
    assert coord.nextSyncAttempt() == time.now() - timedelta(hours=1)
    assert coord.check()


def test_save_creds(coord: Coordinator, source, dest):
    pass


@pytest.mark.asyncio
async def test_check_size_new_backup(coord: Coordinator, source: HelperTestSource, dest: HelperTestSource, time, fs: FsFaker):
    skipForWindows()
    fs.setFreeBytes(0)
    with raises(LowSpaceError):
        await coord.startBackup(CreateOptions(time.now(), "Test Name"))


@pytest.mark.asyncio
async def test_check_size_sync(coord: Coordinator, source: HelperTestSource, dest: HelperTestSource, time, fs: FsFaker, global_info: GlobalInfo):
    skipForWindows()
    fs.setFreeBytes(0)
    await coord.sync()
    assert len(coord.backups()) == 0
    assert global_info._last_error is not None

    await coord.sync()
    assert len(coord.backups()) == 0
    assert global_info._last_error is not None

    # Verify it resets the global size skip check, but gets through once
    global_info.setSkipSpaceCheckOnce(True)
    await coord.sync()
    assert len(coord.backups()) == 1
    assert global_info._last_error is None
    assert not global_info.isSkipSpaceCheckOnce()

    # Next attempt to backup shoudl fail again.
    time.advance(days=7)
    await coord.sync()
    assert len(coord.backups()) == 1
    assert global_info._last_error is not None


@pytest.mark.asyncio
async def test_cancel(coord: Coordinator, global_info: GlobalInfo):
    coord._sync_wait.clear()
    asyncio.create_task(coord.sync())
    await coord._sync_start.wait()
    await coord.cancel()
    assert isinstance(global_info._last_error, UserCancelledError)


@pytest.mark.asyncio
async def test_working_through_upload(coord: Coordinator, global_info: GlobalInfo, dest):
    coord._sync_wait.clear()
    assert not coord.isWorkingThroughUpload()
    sync_task = asyncio.create_task(coord.sync())
    await coord._sync_start.wait()
    assert not coord.isWorkingThroughUpload()
    dest.working = True
    assert coord.isWorkingThroughUpload()
    coord._sync_wait.set()
    await asyncio.wait([sync_task])
    assert not coord.isWorkingThroughUpload()


@pytest.mark.asyncio
async def test_alternate_timezone(coord: Coordinator, time: FakeTime, model: Model, dest, source, simple_config: Config):
    time.setTimeZone("Europe/Stockholm")
    simple_config.override(Setting.BACKUP_TIME_OF_DAY, "12:00")
    simple_config.override(Setting.DAYS_BETWEEN_BACKUPS, 1)

    source.setMax(10)
    source.insert("Fri", time.toUtc(time.local(2020, 3, 16, 18, 5)))
    time.setNow(time.local(2020, 3, 16, 18, 6))
    model.reinitialize()
    coord.reset()
    await coord.sync()
    assert not coord.check()
    assert coord.nextBackupTime() == time.local(2020, 3, 17, 12)

    time.setNow(time.local(2020, 3, 17, 11, 59))
    await coord.sync()
    assert not coord.check()
    time.setNow(time.local(2020, 3, 17, 12))
    assert coord.check()


@pytest.mark.asyncio
async def test_disabled_at_install(coord: Coordinator, dest, time):
    """
    Verifies that at install time, if some backups are already present the
    addon doesn't try to sync over and over when drive is disabled.  This was
    a problem at one point.
    """
    dest.setEnabled(True)
    await coord.sync()
    assert len(coord.backups()) == 1

    dest.setEnabled(False)
    time.advance(days=5)
    assert coord.check()
    await coord.sync()
    assert not coord.check()


@pytest.mark.asyncio
async def test_only_source_configured(coord: Coordinator, dest: HelperTestSource, time, source: HelperTestSource):
    source.setEnabled(True)
    dest.setEnabled(False)
    dest.setNeedsConfiguration(False)
    await coord.sync()
    assert len(coord.backups()) == 1


@pytest.mark.asyncio
async def test_schedule_backup_next_sync_attempt(coord: Coordinator, model, source: HelperTestSource, dest: HelperTestSource, backup, time: FakeTime, simple_config: Config):
    """
    Next backup is before max sync interval is reached
    """
    simple_config.override(Setting.DAYS_BETWEEN_BACKUPS, 1)
    simple_config.override(Setting.MAX_SYNC_INTERVAL_SECONDS, 60 * 60)

    time.setTimeZone("Europe/Stockholm")
    simple_config.override(Setting.BACKUP_TIME_OF_DAY, "03:23")
    simple_config.override(Setting.DAYS_BETWEEN_BACKUPS, 1)

    source.setMax(10)
    source.insert("Fri", time.toUtc(time.local(2020, 3, 16, 3, 33)))

    time.setNow(time.local(2020, 3, 17, 2, 29))
    model.reinitialize()
    coord.reset()
    await coord.sync()
    assert coord.nextBackupTime() == time.local(2020, 3, 17, 3, 23)
    assert coord.nextBackupTime() == coord.nextSyncAttempt()


@pytest.mark.asyncio
async def test_max_sync_interval_next_sync_attempt(coord: Coordinator, model, source: HelperTestSource, dest: HelperTestSource, backup, time: FakeTime, simple_config: Config):
    """
    Next backup is after max sync interval is reached
    """
    simple_config.override(Setting.DAYS_BETWEEN_BACKUPS, 1)
    simple_config.override(Setting.MAX_SYNC_INTERVAL_SECONDS, 60 * 60)

    time.setTimeZone("Europe/Stockholm")
    simple_config.override(Setting.BACKUP_TIME_OF_DAY, "03:23")
    simple_config.override(Setting.DAYS_BETWEEN_BACKUPS, 1)

    source.setMax(10)
    source.insert("Fri", time.toUtc(time.local(2020, 3, 16, 3, 33)))
    time.setNow(time.local(2020, 3, 17, 1, 29))
    model.reinitialize()
    coord.reset()
    await coord.sync()
    assert coord.nextSyncAttempt() == time.local(2020, 3, 17, 2, 29)
    assert coord.nextBackupTime() > coord.nextSyncAttempt()
