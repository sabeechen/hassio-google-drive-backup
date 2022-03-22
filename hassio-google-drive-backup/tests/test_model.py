from datetime import datetime, timedelta, timezone

import pytest
from dateutil.tz import gettz

from backup.config import Config, Setting, CreateOptions
from backup.exceptions import DeleteMutlipleBackupsError
from backup.util import GlobalInfo, DataCache
from backup.model import Model, BackupSource
from .faketime import FakeTime
from .helpers import HelperTestSource, IntentionalFailure

test_tz = gettz('EST')

default_source = BackupSource()


@pytest.fixture
def source():
    return HelperTestSource("Source")


@pytest.fixture
def dest():
    return HelperTestSource("Dest")


@pytest.fixture
def simple_config():
    config = createConfig()
    return config


@pytest.fixture
def model(source, dest, time, simple_config, global_info, estimator, data_cache):
    return Model(simple_config, time, source, dest, global_info, estimator, data_cache)


def createConfig() -> Config:
    return Config().override(Setting.BACKUP_STARTUP_DELAY_MINUTES, 0)


def test_timeOfDay(estimator, model: Model) -> None:
    assert model.getTimeOfDay() is None

    model.config.override(Setting.BACKUP_TIME_OF_DAY, '00:00')
    model.reinitialize()
    assert model.getTimeOfDay() == (0, 0)

    model.config.override(Setting.BACKUP_TIME_OF_DAY, '23:59')
    model.reinitialize()
    assert model.getTimeOfDay() == (23, 59)

    model.config.override(Setting.BACKUP_TIME_OF_DAY, '24:59')
    model.reinitialize()
    assert model.getTimeOfDay() is None

    model.config.override(Setting.BACKUP_TIME_OF_DAY, '24:60')
    model.reinitialize()
    assert model.getTimeOfDay() is None

    model.config.override(Setting.BACKUP_TIME_OF_DAY, '-1:60')
    model.reinitialize()
    assert model.getTimeOfDay() is None

    model.config.override(Setting.BACKUP_TIME_OF_DAY, '24:-1')
    model.reinitialize()
    assert model.getTimeOfDay() is None

    model.config.override(Setting.BACKUP_TIME_OF_DAY, 'boop:60')
    model.reinitialize()
    assert model.getTimeOfDay() is None

    model.config.override(Setting.BACKUP_TIME_OF_DAY, '24:boop')
    model.reinitialize()
    assert model.getTimeOfDay() is None

    model.config.override(Setting.BACKUP_TIME_OF_DAY, '24:10:22')
    model.reinitialize()
    assert model.getTimeOfDay() is None

    model.config.override(Setting.BACKUP_TIME_OF_DAY, '10')
    model.reinitialize()
    assert model.getTimeOfDay() is None


def test_next_time(estimator, data_cache):
    time: FakeTime = FakeTime()
    now: datetime = datetime(1985, 12, 6, 1, 0, 0).astimezone(timezone.utc)
    time.setNow(now)
    info = GlobalInfo(time)
    config: Config = createConfig().override(Setting.DAYS_BETWEEN_BACKUPS, 0)
    model: Model = Model(config, time, default_source,
                         default_source, info, estimator, data_cache)
    assert model._nextBackup(now=now, last_backup=None) is None
    assert model._nextBackup(now=now, last_backup=now) is None

    config: Config = createConfig().override(Setting.DAYS_BETWEEN_BACKUPS, 1)
    model: Model = Model(config, time, default_source,
                         default_source, info, estimator, data_cache)
    assert model._nextBackup(
        now=now, last_backup=None) == now - timedelta(minutes=1)
    assert model._nextBackup(
        now=now, last_backup=now) == now + timedelta(days=1)
    assert model._nextBackup(
        now=now, last_backup=now - timedelta(days=1)) == now
    assert model._nextBackup(
        now=now, last_backup=now + timedelta(days=1)) == now + timedelta(days=2)


def test_next_time_of_day(estimator, data_cache):
    time: FakeTime = FakeTime()
    now: datetime = datetime(1985, 12, 6, 1, 0, 0).astimezone(timezone.utc)
    time.setNow(now)
    info = GlobalInfo(time)
    config: Config = createConfig().override(Setting.DAYS_BETWEEN_BACKUPS, 1).override(
        Setting.BACKUP_TIME_OF_DAY, '08:00')
    model: Model = Model(config, time, default_source,
                         default_source, info, estimator, data_cache)

    assert model._nextBackup(
        now=now, last_backup=None) == now - timedelta(minutes=1)
    assert model._nextBackup(
        now=now, last_backup=now - timedelta(days=1)) == datetime(
        1985, 12, 5, 8, 0, tzinfo=test_tz)
    assert model._nextBackup(now=now, last_backup=now) == datetime(
        1985, 12, 6, 8, 0, tzinfo=test_tz)
    assert model._nextBackup(now=now, last_backup=datetime(
        1985, 12, 6, 8, 0, tzinfo=test_tz)) == datetime(1985, 12, 7, 8, 0, tzinfo=test_tz)
    assert model._nextBackup(now=datetime(1985, 12, 6, 8, 0, tzinfo=test_tz), last_backup=datetime(
        1985, 12, 6, 8, 0, tzinfo=test_tz)) == datetime(1985, 12, 7, 8, 0, tzinfo=test_tz)


def test_next_time_of_day_drift(estimator, data_cache):
    time: FakeTime = FakeTime()
    now: datetime = datetime(1985, 12, 6, 1, 0, 0).astimezone(timezone.utc)
    time.setNow(now)
    info = GlobalInfo(time)

    config: Config = createConfig().override(Setting.DAYS_BETWEEN_BACKUPS, 1).override(
        Setting.BACKUP_TIME_OF_DAY, '08:00')
    model: Model = Model(config, time, default_source,
                         default_source, info, estimator, data_cache)

    assert model._nextBackup(
        now=now, last_backup=None) == now - timedelta(minutes=1)
    assert model._nextBackup(
        now=now, last_backup=now - timedelta(days=1) + timedelta(minutes=1)) == datetime(1985, 12, 5, 8, 0, tzinfo=test_tz)


def test_next_time_of_day_dest_disabled(model, time, source, dest):
    dest.setEnabled(True)
    assert model._nextBackup(
        now=time.now(), last_backup=None) == time.now() - timedelta(minutes=1)
    dest.setEnabled(False)
    assert model._nextBackup(now=time.now(), last_backup=None) is None


@pytest.mark.asyncio
async def test_sync_empty(model, time, source, dest):
    source.setEnabled(False)
    dest.setEnabled(False)
    await model.sync(time.now())
    assert len(model.backups) == 0


@pytest.mark.asyncio
async def test_sync_single_source(model: Model, source, dest, time):
    backup = await source.create(CreateOptions(time.now(), "name"))
    dest.setEnabled(False)
    await model.sync(time.now())
    assert len(model.backups) == 1
    assert backup.slug() in model.backups
    assert model.backups[backup.slug()].getSource(
        source.name()) is backup
    assert model.backups[backup.slug()].getSource(dest.name()) is None


@pytest.mark.asyncio
async def test_sync_source_and_dest(model: Model, time, source, dest: HelperTestSource):
    backup_source = await source.create(CreateOptions(time.now(), "name"))
    await model._syncBackups([source, dest])
    assert len(model.backups) == 1

    backup_dest = await dest.save(model.backups[backup_source.slug()])
    await model._syncBackups([source, dest])
    assert len(model.backups) == 1
    assert model.backups[backup_source.slug()].getSource(
        source.name()) is backup_source
    assert model.backups[backup_source.slug()].getSource(
        dest.name()) is backup_dest


@pytest.mark.asyncio
async def test_sync_different_sources(model: Model, time, source, dest):
    backup_source = await source.create(CreateOptions(time.now(), "name"))
    backup_dest = await dest.create(CreateOptions(time.now(), "name"))

    await model._syncBackups([source, dest])
    assert len(model.backups) == 2
    assert model.backups[backup_source.slug()].getSource(
        source.name()) is backup_source
    assert model.backups[backup_dest.slug()].getSource(
        dest.name()) is backup_dest


@pytest.mark.asyncio
async def test_removal(model: Model, time, source, dest):
    await source.create(CreateOptions(time.now(), "name"))
    await model._syncBackups([source, dest])
    assert len(model.backups) == 1
    source.current = {}
    await model._syncBackups([source, dest])
    assert len(model.backups) == 0


@pytest.mark.asyncio
async def test_new_backup(model: Model, source, dest, time):
    await model.sync(time.now())
    assert len(model.backups) == 1
    assert len(source.created) == 1
    assert source.created[0].date() == time.now()
    assert len(source.current) == 1
    assert len(dest.current) == 1


@pytest.mark.asyncio
async def test_upload_backup(time, model: Model, dest, source):
    dest.setEnabled(True)
    await model.sync(time.now())
    assert len(model.backups) == 1
    source.assertThat(created=1, current=1)
    assert len(source.created) == 1
    assert source.created[0].date() == time.now()
    assert len(source.current) == 1
    assert len(dest.current) == 1
    assert len(dest.saved) == 1


@pytest.mark.asyncio
async def test_disabled(time, model: Model, source, dest):
    # create two disabled sources
    source.setEnabled(False)
    source.insert("newer", time.now(), "slug1")
    dest.setEnabled(False)
    dest.insert("s2", time.now(), "slug2")
    await model.sync(time.now())
    source.assertUnchanged()
    dest.assertUnchanged()
    assert len(model.backups) == 0


@pytest.mark.asyncio
async def test_delete_source(time, model: Model, source, dest):
    time = FakeTime()
    now = time.now()

    # create two source backups
    source.setMax(1)
    older = source.insert("older", now - timedelta(minutes=1), "older")
    newer = source.insert("newer", now, "newer")

    # configure only one to be kept
    await model.sync(now)
    assert len(model.backups) == 1
    assert len(source.saved) == 0
    assert source.deleted == [older]
    assert len(source.saved) == 0
    assert newer.slug() in model.backups
    assert model.backups[newer.slug()].getSource(source.name()) == newer


@pytest.mark.asyncio
async def test_delete_dest(time, model: Model, source, dest):
    now = time.now()

    # create two source backups
    dest.setMax(1)
    older = dest.insert("older", now - timedelta(minutes=1), "older")
    newer = dest.insert("newer", now, "newer")

    # configure only one to be kept
    await model.sync(now)
    assert len(model.backups) == 1
    assert len(dest.saved) == 0
    assert dest.deleted == [older]
    assert len(source.saved) == 0
    assert newer.slug() in model.backups
    assert model.backups[newer.slug()].getSource(dest.name()) == newer
    source.assertUnchanged()


@pytest.mark.asyncio
async def test_new_upload_with_delete(time, model: Model, source, dest, simple_config):
    now = time.now()

    # create a single old backups
    source.setMax(1)
    dest.setMax(1)
    backup_dest = dest.insert("older", now - timedelta(days=1), "older")
    backup_source = source.insert("older", now - timedelta(days=1), "older")

    # configure only one to be kept in both places
    simple_config.config.update({
        "days_between_backups": 1
    })
    model.reinitialize()
    await model.sync(now)

    # Old snapshto shoudl be deleted, new one shoudl be created and uploaded.
    source.assertThat(current=1, created=1, deleted=1)
    dest.assertThat(current=1, saved=1, deleted=1)
    assert dest.deleted == [backup_dest]
    assert source.deleted == [backup_source]

    assert len(model.backups) == 1
    assertBackup(model, [source.created[0], dest.saved[0]])


@pytest.mark.asyncio
async def test_new_upload_no_delete(time, model: Model, source, dest, simple_config):
    now = time.now()

    # create a single old backup
    source.setMax(2)
    dest.setMax(2)
    backup_dest = dest.insert("older", now - timedelta(days=1), "older")
    backup_source = source.insert("older", now - timedelta(days=1), "older")

    # configure keeping two in both places
    simple_config.config.update({
        "days_between_backups": 1
    })
    model.reinitialize()
    await model.sync(now)

    # Another backup should have been created and saved
    source.assertThat(current=2, created=1)
    dest.assertThat(current=2, saved=1)
    assert len(model.backups) == 2
    assertBackup(model, [source.created[0], dest.saved[0]])
    assertBackup(model, [backup_dest, backup_source])


@pytest.mark.asyncio
async def test_multiple_deletes_allowed(time, model: Model, source, dest, simple_config):
    now = time.now()
    simple_config.config.update({"confirm_multiple_deletes": False})
    # create 4 backups in dest
    dest.setMax(1)

    current = dest.insert("current", now, "current")
    old = dest.insert("old", now - timedelta(days=1), "old")
    older = dest.insert("older", now - timedelta(days=2), "older")
    oldest = dest.insert("oldest", now - timedelta(days=3), "oldest")

    # configure keeping 1
    simple_config.config.update({
        "max_backups_in_google_drive": 1,
    })
    model.reinitialize()
    await model.sync(now)

    source.assertUnchanged()
    dest.assertThat(current=1, deleted=3)
    assert dest.deleted == [oldest, older, old]
    assert len(model.backups) == 1
    assertBackup(model, [current])


@pytest.mark.asyncio
async def test_confirm_multiple_deletes(time, model: Model, source, dest, simple_config):
    now = time.now()
    dest.setMax(1)
    source.setMax(1)

    dest.insert("current", now, "current")
    dest.insert("old", now - timedelta(days=1), "old")
    dest.insert("older", now - timedelta(days=2), "older")
    dest.insert("oldest", now - timedelta(days=2), "olderest")

    source.insert("current", now, "current")
    source.insert("old", now - timedelta(days=1), "old")
    source.insert("older", now - timedelta(days=2), "older")

    with pytest.raises(DeleteMutlipleBackupsError) as thrown:
        await model.sync(now)

    thrown.value.data() == {
        source.name(): 2,
        dest.name(): 3
    }

    source.assertUnchanged()
    dest.assertUnchanged()


@pytest.mark.asyncio
async def test_dont_upload_deletable(time, model: Model, source, dest):
    now = time.now()

    # a new backup in Drive and an old backup in HA
    dest.setMax(1)
    current = dest.insert("current", now, "current")
    old = source.insert("old", now - timedelta(days=1), "old")

    # configure keeping 1
    await model.sync(now)

    # Nothing should happen, because the upload from hassio would have to be deleted right after it's uploaded.
    source.assertUnchanged()
    dest.assertUnchanged()
    assert len(model.backups) == 2
    assertBackup(model, [current])
    assertBackup(model, [old])


@pytest.mark.asyncio
async def test_dont_upload_when_disabled(time, model: Model, source, dest):
    now = time.now()

    # Make an enabled destination but with upload diabled.
    dest.setMax(1)
    dest.setUpload(False)

    await model.sync(now)

    # Verify the backup was created at the source but not uploaded.
    source.assertThat(current=1, created=1)
    dest.assertUnchanged()
    assert len(model.backups) == 1


@pytest.mark.asyncio
async def test_dont_delete_purgable(time, model: Model, source, dest, simple_config):
    now = time.now()

    # create a single old backup, retained
    source.setMax(1)
    dest.setMax(1)
    backup_dest = dest.insert("older", now - timedelta(days=1), "older")
    backup_dest.setRetained(True)
    backup_source = source.insert("older", now - timedelta(days=1), "older")
    backup_source.setRetained(True)

    # configure only one to be kept in both places
    simple_config.config.update({
        "days_between_backups": 1
    })
    model.reinitialize()
    await model.sync(now)

    # Old snapshto shoudl be kept, new one should be created and uploaded.
    source.assertThat(current=2, created=1)
    dest.assertThat(current=2, saved=1)

    assert len(model.backups) == 2
    assertBackup(model, [backup_dest, backup_source])
    assertBackup(model, [source.created[0], dest.saved[0]])


@pytest.mark.asyncio
async def test_generational_delete(time, model: Model, dest, source, simple_config):
    time.setNow(time.local(2019, 5, 10))
    now = time.now()

    # Create 4 backups, configured to keep 3
    source.setMax(3)
    source.insert("Fri", time.local(2019, 5, 10, 1))
    source.insert("Thu", time.local(2019, 5, 9, 1))
    wed = source.insert("Wed", time.local(2019, 5, 8, 1))
    source.insert("Mon", time.local(2019, 5, 6, 1))

    # configure only one to be kept in both places
    simple_config.config.update({
        "days_between_backups": 1,
        "generational_weeks": 1,
        "generational_days": 2
    })
    model.reinitialize()
    await model.sync(now)

    # Shoud only delete wed, since it isn't kept in the generational backup config
    source.assertThat(current=3, deleted=1)
    assert source.deleted == [wed]
    assert len(model.backups) == 3
    dest.assertThat(current=3, saved=3)


@pytest.mark.asyncio
async def test_delete_when_drive_disabled(time, model: Model, dest: HelperTestSource, source: HelperTestSource, simple_config):
    time.setNow(time.local(2019, 5, 10))
    now = time.now()
    dest.setEnabled(False)
    dest.setNeedsConfiguration(False)

    # Create 4 backups, configured to keep 3
    source.setMax(3)
    source.insert("Fri", time.local(2019, 5, 10, 1))
    source.insert("Thu", time.local(2019, 5, 9, 1))
    source.insert("Wed", time.local(2019, 5, 8, 1))
    mon = source.insert("Mon", time.local(2019, 5, 7, 1))

    await model.sync(now)

    # Shoud only delete mon, the oldest one
    source.assertThat(current=3, deleted=1)
    assert source.deleted == [mon]
    assert len(model.backups) == 3
    dest.assertThat(current=0)


@pytest.mark.asyncio
async def test_wait_for_startup_no_backup(time: FakeTime, model: Model, dest: HelperTestSource, source: HelperTestSource, global_info: GlobalInfo):
    time.setNow(time.local(2019, 5, 10))
    global_info.triggerBackupCooldown(timedelta(minutes=10))
    assert model.nextBackup(time.now()) == time.now() + timedelta(minutes=10)
    assert model.nextBackup(time.now()) == global_info.backupCooldownTime()
    assert model.waiting_for_startup

    time.advance(minutes=10)
    assert model.nextBackup(time.now()) == time.now() - timedelta(minutes=1)
    assert not model.waiting_for_startup


@pytest.mark.asyncio
async def test_wait_for_startup_with_backup(time: FakeTime, model: Model, dest: HelperTestSource, source: HelperTestSource, global_info: GlobalInfo):
    time.setNow(time.local(2019, 5, 10))
    global_info.triggerBackupCooldown(timedelta(minutes=10))

    source.setMax(3)
    source.insert("old", time.now() - timedelta(days=7))

    assert model.nextBackup(time.now()) == time.now() + timedelta(minutes=10)
    assert model.nextBackup(time.now()) == global_info.backupCooldownTime()
    assert model.waiting_for_startup

    time.advance(minutes=10)
    assert model.nextBackup(time.now()) == time.now() - timedelta(minutes=1)
    assert not model.waiting_for_startup


@pytest.mark.asyncio
async def test_ignore_startup_delay(time: FakeTime, model: Model, dest: HelperTestSource, source: HelperTestSource, global_info: GlobalInfo):
    time.setNow(time.local(2019, 5, 10))
    global_info.triggerBackupCooldown(timedelta(minutes=10))
    model.ignore_startup_delay = True
    assert model.nextBackup(time.now()) == time.now() - timedelta(minutes=1)
    assert not model.waiting_for_startup


def assertBackup(model, sources):
    matches = {}
    for source in sources:
        matches[source.source()] = source
        slug = source.slug()
    assert slug in model.backups
    assert model.backups[slug].sources == matches


@pytest.mark.asyncio
async def test_delete_after_upload(time: FakeTime, model: Model, dest: HelperTestSource, source: HelperTestSource, global_info: GlobalInfo):
    model.config.override(Setting.DELETE_AFTER_UPLOAD, True)
    source.setMax(100)
    dest.setMax(100)
    dest.insert("Destination 1", time.now())
    dest.reset()

    # Nothing should happen on a sync, the backup is already backed up.
    await model.sync(time.now())
    dest.assertThat(current=1)
    source.assertThat()

    time.advance(days=7)
    source.insert("Source 1", time.now())
    source.reset()

    # Source backup should get backed up and the deleted
    await model.sync(time.now())
    source.assertThat(deleted=1, current=0)
    dest.assertThat(saved=1, current=2)


@pytest.mark.asyncio
async def test_delete_after_upload_multiple_deletes(time: FakeTime, model: Model, dest: HelperTestSource, source: HelperTestSource, global_info: GlobalInfo):
    model.config.override(Setting.DELETE_AFTER_UPLOAD, True)
    source.setMax(100)
    dest.setMax(100)
    source.insert("Src 1", time.now())
    time.advance(days=1)
    source.insert("Src 2", time.now())
    source.reset()

    # Deleteing multiple backups should still fail with DELETE_AFTER_UPLOAD:True
    with pytest.raises(DeleteMutlipleBackupsError):
        await model.sync(time.now())

    # But the backup should still get backed up
    source.assertThat(current=2)
    dest.assertThat(saved=2, current=2)


@pytest.mark.asyncio
async def test_delete_after_upload_simple_sync(time: FakeTime, model: Model, dest: HelperTestSource, source: HelperTestSource, global_info: GlobalInfo):
    model.config.override(Setting.DELETE_AFTER_UPLOAD, True)
    source.setMax(100)
    dest.setMax(100)

    # A sync should create a backup, back it up to dest, and then delete it from source.
    await model.sync(time.now())
    source.assertThat(created=1, deleted=1, current=0)
    dest.assertThat(saved=1, current=1)

    time.advance(hours=1)
    source.reset()
    dest.reset()

    # Next sync should do nothing
    await model.sync(time.now())
    source.assertThat()
    dest.assertThat(current=1)


@pytest.mark.asyncio
async def test_never_delete_ignored_backups(time: FakeTime, model: Model, dest: HelperTestSource, source: HelperTestSource):
    source.setMax(1)
    dest.setMax(1)

    # A sync should create a backup and back it up to dest.
    await model.sync(time.now())
    source.assertThat(created=1, current=1)
    dest.assertThat(saved=1, current=1)

    source.reset()
    dest.reset()

    # Another sync shoudl delete a backup, which is just a sanity check.
    time.advance(days=5)
    await model.sync(time.now())
    source.assertThat(created=1, current=1, deleted=1)
    dest.assertThat(saved=1, current=1, deleted=1)
    assert model.nextBackup(time.now()) == time.now() + timedelta(days=3)
    source.reset()
    dest.reset()

    # Make the backup ignored, which should cause a new backup to be created
    # and synced without the ignored one getting deleted.
    next(iter((await dest.get()).values())).setIgnore(True)
    next(iter((await source.get()).values())).setIgnore(True)
    assert model.nextBackup(time.now()) < time.now()
    await model.sync(time.now())
    source.assertThat(created=1, current=2)
    dest.assertThat(saved=1, current=2)


@pytest.mark.asyncio
async def test_ignored_backups_dont_upload(time: FakeTime, model: Model, dest: HelperTestSource, source: HelperTestSource):
    source.setMax(2)
    dest.setMax(2)

    older = source.insert("older", time.now() - timedelta(days=1), slug="older")
    older.setIgnore(True)
    source.insert("newer", time.now(), slug="newer")
    source.reset()

    # A sync should backup the last backup and ignore the older one
    await model.sync(time.now())
    source.assertThat(created=0, current=2)
    dest.assertThat(saved=1, current=1)

    uploaded = await dest.get()
    assert len(uploaded) == 1
    assert next(iter(uploaded.values())).name() == "newer"


@pytest.mark.asyncio
async def test_dirty_cache_gets_saved(time: FakeTime, model: Model, data_cache: DataCache):
    data_cache.makeDirty()
    await model.sync(time.now())
    assert not data_cache.dirty


@pytest.mark.asyncio
async def test_delete_after_upload_with_no_backups(source: HelperTestSource, dest: HelperTestSource, time: FakeTime, model: Model, data_cache: DataCache, simple_config: Config):
    source.setMax(0)
    dest.setMax(2)
    simple_config.override(Setting.DELETE_AFTER_UPLOAD, True)

    source.insert("older", time.now() - timedelta(days=1), slug="older")
    source.insert("newer", time.now(), slug="newer")
    source.reset()

    with pytest.raises(DeleteMutlipleBackupsError):
        await model.sync(time.now())

    simple_config.override(Setting.CONFIRM_MULTIPLE_DELETES, False)
    await model.sync(time.now())

    dest.assertThat(saved=2, current=2)
    source.assertThat(deleted=2, current=0)


@pytest.mark.asyncio
async def test_purge_before_upload(source: HelperTestSource, dest: HelperTestSource, time: FakeTime, model: Model, data_cache: DataCache, simple_config: Config):
    source.setMax(2)
    dest.setMax(2)
    older = source.insert("older", time.now() - timedelta(days=7), slug="older")
    oldest = source.insert("oldest", time.now() - timedelta(days=14), slug="oldest")
    await model.sync(time.now() - timedelta(days=7))

    source.allow_create = False
    dest.allow_save = False

    dest.reset()
    source.reset()

    # trying to sync now should do nothing.
    with pytest.raises(IntentionalFailure):
        await model.sync(time.now())
    source.assertThat(current=2)
    dest.assertThat(current=2)

    simple_config.override(Setting.DELETE_BEFORE_NEW_BACKUP, True)
    # Trying to sync should delete the backup before syncing and then fail to create a new one.
    with pytest.raises(IntentionalFailure):
        await model.sync(time.now())
    source.assertThat(deleted=1, current=1)
    assert oldest.slug() not in (await source.get()).keys()
    dest.assertThat(current=2)

    # Trying to do it again should do nothing (eg not delete another backup)
    with pytest.raises(IntentionalFailure):
        await model.sync(time.now())
    source.assertThat(deleted=1, current=1)
    dest.assertThat(current=2)

    # let the new source backup get created, which then deletes the destination but fails to save
    source.allow_create = True
    with pytest.raises(IntentionalFailure):
        await model.sync(time.now())
    source.assertThat(deleted=1, current=2, created=1)
    dest.assertThat(current=1, deleted=1)
    assert oldest.slug() not in (await dest.get()).keys()

    # now let the new backup get saved.
    dest.allow_save = True
    await model.sync(time.now())
    source.assertThat(deleted=1, current=2, created=1)
    dest.assertThat(current=2, deleted=1, saved=1)

    assert oldest.slug() not in (await source.get()).keys()
    assert older.slug() in (await source.get()).keys()
    assert oldest.slug() not in (await dest.get()).keys()
    assert older.slug() in (await dest.get()).keys()


@pytest.mark.asyncio
async def test_generational_empty(time, model: Model, dest, source, simple_config: Config):
    time.setNow(time.local(2019, 5, 10))
    now = time.now()

    simple_config.config.update({
        "days_between_backups": 1,
        "generational_weeks": 1,
        "generational_days": 2
    })

    simple_config.override(Setting.DAYS_BETWEEN_BACKUPS, 1)

    model.reinitialize()
    assert len(model.backups) == 0
    await model.sync(now)
    assert len(model.backups) == 1


@pytest.mark.asyncio
async def test_delete_ignored_other_backup_after_some_time(time: FakeTime, model: Model, dest: HelperTestSource, source: HelperTestSource, simple_config: Config):
    # Create a few backups, one ignored
    source.setMax(2)
    dest.setMax(2)
    simple_config.override(Setting.DAYS_BETWEEN_BACKUPS, 0)
    simple_config.override(Setting.IGNORE_OTHER_BACKUPS, True)
    simple_config.override(Setting.DELETE_IGNORED_AFTER_DAYS, 1)
    ignored = source.insert("Ignored", time.now())
    source.insert("Existing", time.now())
    ignored.setIgnore(True)
    await model.sync(time.now())
    source.assertThat(current=2)
    dest.assertThat(saved=1, current=1)
    source.reset()
    dest.reset()

    time.advance(hours=23)
    await model.sync(time.now())

    source.assertThat(current=2)
    dest.assertThat(current=1)

    time.advance(hours=2)
    await model.sync(time.now())
    source.assertThat(current=1, deleted=1)
    dest.assertThat(current=1)


@pytest.mark.asyncio
async def test_delete_ignored_upgrade_backup_after_some_time(time: FakeTime, model: Model, dest: HelperTestSource, source: HelperTestSource, simple_config: Config):
    # Create a few backups, one ignored
    source.setMax(2)
    dest.setMax(2)
    simple_config.override(Setting.DAYS_BETWEEN_BACKUPS, 0)
    simple_config.override(Setting.IGNORE_UPGRADE_BACKUPS, True)
    simple_config.override(Setting.DELETE_IGNORED_AFTER_DAYS, 1)
    ignored = source.insert("Ignored", time.now())
    source.insert("Existing", time.now())
    ignored.setIgnore(True)
    await model.sync(time.now())
    source.assertThat(current=2)
    dest.assertThat(saved=1, current=1)
    source.reset()
    dest.reset()

    time.advance(hours=23)
    await model.sync(time.now())

    source.assertThat(current=2)
    dest.assertThat(current=1)

    time.advance(hours=2)
    await model.sync(time.now())
    source.assertThat(current=1, deleted=1)
    dest.assertThat(current=1)
