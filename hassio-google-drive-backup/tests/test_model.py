from datetime import datetime, timedelta, timezone

import pytest
from dateutil.tz import gettz

from backup.config import Config, Setting, CreateOptions
from backup.exceptions import DeleteMutlipleSnapshotsError
from backup.util import GlobalInfo
from backup.model import Model, SnapshotSource
from .faketime import FakeTime
from .helpers import HelperTestSource

test_tz = gettz('EST')

default_source = SnapshotSource()


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
def model(source, dest, time, simple_config, global_info, estimator):
    return Model(simple_config, time, source, dest, global_info, estimator)


def test_timeOfDay(estimator) -> None:
    time: FakeTime = FakeTime()
    info = GlobalInfo(time)

    config: Config = Config()
    model: Model = Model(config, time, default_source,
                         default_source, info, estimator)
    assert model.getTimeOfDay() is None

    config = Config().override(Setting.SNAPSHOT_TIME_OF_DAY, '00:00')
    model = Model(config, time, default_source,
                  default_source, info, estimator)
    assert model.getTimeOfDay() == (0, 0)

    config.override(Setting.SNAPSHOT_TIME_OF_DAY, '23:59')
    model = Model(config, time, default_source,
                  default_source, info, estimator)
    assert model.getTimeOfDay() == (23, 59)

    config.override(Setting.SNAPSHOT_TIME_OF_DAY, '24:59')
    model = Model(config, time, default_source,
                  default_source, info, estimator)
    assert model.getTimeOfDay() is None

    config.override(Setting.SNAPSHOT_TIME_OF_DAY, '24:60')
    model = Model(config, time, default_source,
                  default_source, info, estimator)
    assert model.getTimeOfDay() is None

    config.override(Setting.SNAPSHOT_TIME_OF_DAY, '-1:60')
    model = Model(config, time, default_source,
                  default_source, info, estimator)
    assert model.getTimeOfDay() is None

    config.override(Setting.SNAPSHOT_TIME_OF_DAY, '24:-1')
    model = Model(config, time, default_source,
                  default_source, info, estimator)
    assert model.getTimeOfDay() is None

    config.override(Setting.SNAPSHOT_TIME_OF_DAY, 'boop:60')
    model = Model(config, time, default_source,
                  default_source, info, estimator)
    assert model.getTimeOfDay() is None

    config.override(Setting.SNAPSHOT_TIME_OF_DAY, '24:boop')
    model = Model(config, time, default_source,
                  default_source, info, estimator)
    assert model.getTimeOfDay() is None

    config.override(Setting.SNAPSHOT_TIME_OF_DAY, '24:10:22')
    model = Model(config, time, default_source,
                  default_source, info, estimator)
    assert model.getTimeOfDay() is None

    config.override(Setting.SNAPSHOT_TIME_OF_DAY, '10')
    model = Model(config, time, default_source,
                  default_source, info, estimator)
    assert model.getTimeOfDay() is None


def test_next_time(estimator):
    time: FakeTime = FakeTime()
    info = GlobalInfo(time)
    now: datetime = datetime(1985, 12, 6, 1, 0, 0).astimezone(timezone.utc)

    config: Config = Config().override(Setting.DAYS_BETWEEN_SNAPSHOTS, 0)
    model: Model = Model(config, time, default_source,
                         default_source, info, estimator)
    assert model._nextSnapshot(now=now, last_snapshot=None) is None
    assert model._nextSnapshot(now=now, last_snapshot=now) is None

    config: Config = Config().override(Setting.DAYS_BETWEEN_SNAPSHOTS, 1)
    model: Model = Model(config, time, default_source,
                         default_source, info, estimator)
    assert model._nextSnapshot(
        now=now, last_snapshot=None) == now - timedelta(minutes=1)
    assert model._nextSnapshot(
        now=now, last_snapshot=now) == now + timedelta(days=1)
    assert model._nextSnapshot(
        now=now, last_snapshot=now - timedelta(days=1)) == now
    assert model._nextSnapshot(
        now=now, last_snapshot=now + timedelta(days=1)) == now + timedelta(days=2)


def test_next_time_of_day(estimator):
    time: FakeTime = FakeTime()
    info = GlobalInfo(time)
    now: datetime = datetime(1985, 12, 6, 1, 0, 0).astimezone(timezone.utc)

    config: Config = Config().override(Setting.DAYS_BETWEEN_SNAPSHOTS, 1).override(
        Setting.SNAPSHOT_TIME_OF_DAY, '08:00')
    model: Model = Model(config, time, default_source,
                         default_source, info, estimator)

    assert model._nextSnapshot(
        now=now, last_snapshot=None) == now - timedelta(minutes=1)
    assert model._nextSnapshot(
        now=now, last_snapshot=now - timedelta(days=1)) == now
    assert model._nextSnapshot(now=now, last_snapshot=now) == datetime(
        1985, 12, 6, 8, 0, tzinfo=test_tz)
    assert model._nextSnapshot(now=now, last_snapshot=datetime(
        1985, 12, 6, 8, 0, tzinfo=test_tz)) == datetime(1985, 12, 7, 8, 0, tzinfo=test_tz)
    assert model._nextSnapshot(now=datetime(1985, 12, 6, 8, 0, tzinfo=test_tz), last_snapshot=datetime(
        1985, 12, 6, 8, 0, tzinfo=test_tz)) == datetime(1985, 12, 7, 8, 0, tzinfo=test_tz)


def test_next_time_of_day_dest_disabled(model, time, source, dest):
    dest.setEnabled(True)
    assert model._nextSnapshot(
        now=time.now(), last_snapshot=None) == time.now() - timedelta(minutes=1)
    dest.setEnabled(False)
    assert model._nextSnapshot(now=time.now(), last_snapshot=None) is None


@pytest.mark.asyncio
async def test_sync_empty(model, time, source, dest):
    source.setEnabled(False)
    dest.setEnabled(False)
    await model.sync(time.now())
    assert len(model.snapshots) == 0


@pytest.mark.asyncio
async def test_sync_single_source(model, source, dest, time):
    snapshot = await source.create(CreateOptions(time.now(), "name"))
    dest.setEnabled(False)
    await model.sync(time.now())
    assert len(model.snapshots) == 1
    assert snapshot.slug() in model.snapshots
    assert model.snapshots[snapshot.slug()].getSource(
        source.name()) is snapshot
    assert model.snapshots[snapshot.slug()].getSource(dest.name()) is None


@pytest.mark.asyncio
async def test_sync_source_and_dest(model, time, source, dest):
    snapshot_source = await source.create(CreateOptions(time.now(), "name"))
    await model._syncSnapshots([source, dest])
    assert len(model.snapshots) == 1

    snapshot_dest = await dest.save(model.snapshots[snapshot_source.slug()])
    await model._syncSnapshots([source, dest])
    assert len(model.snapshots) == 1
    assert model.snapshots[snapshot_source.slug()].getSource(
        source.name()) is snapshot_source
    assert model.snapshots[snapshot_source.slug()].getSource(
        dest.name()) is snapshot_dest


@pytest.mark.asyncio
async def test_sync_different_sources(model, time, source, dest):
    snapshot_source = await source.create(CreateOptions(time.now(), "name"))
    snapshot_dest = await dest.create(CreateOptions(time.now(), "name"))

    await model._syncSnapshots([source, dest])
    assert len(model.snapshots) == 2
    assert model.snapshots[snapshot_source.slug()].getSource(
        source.name()) is snapshot_source
    assert model.snapshots[snapshot_dest.slug()].getSource(
        dest.name()) is snapshot_dest


@pytest.mark.asyncio
async def test_removal(model, time, source, dest):
    await source.create(CreateOptions(time.now(), "name"))
    await model._syncSnapshots([source, dest])
    assert len(model.snapshots) == 1
    source.current = {}
    await model._syncSnapshots([source, dest])
    assert len(model.snapshots) == 0


@pytest.mark.asyncio
async def test_new_snapshot(model, source, dest, time):
    await model.sync(time.now())
    assert len(model.snapshots) == 1
    assert len(source.created) == 1
    assert source.created[0].date() == time.now()
    assert len(source.current) == 1
    assert len(dest.current) == 1


@pytest.mark.asyncio
async def test_upload_snapshot(time, model, dest, source):
    dest.setEnabled(True)
    await model.sync(time.now())
    assert len(model.snapshots) == 1
    source.assertThat(created=1, current=1)
    assert len(source.created) == 1
    assert source.created[0].date() == time.now()
    assert len(source.current) == 1
    assert len(dest.current) == 1
    assert len(dest.saved) == 1


@pytest.mark.asyncio
async def test_disabled(time, model, source, dest):
    # create two disabled sources
    source.setEnabled(False)
    source.insert("newer", time.now(), "slug1")
    dest.setEnabled(False)
    dest.insert("s2", time.now(), "slug2")
    await model.sync(time.now())
    source.assertUnchanged()
    dest.assertUnchanged()
    assert len(model.snapshots) == 0


@pytest.mark.asyncio
async def test_delete_source(time, model, source, dest):
    time = FakeTime()
    now = time.now()

    # create two source snapshots
    source.setMax(1)
    older = source.insert("older", now - timedelta(minutes=1), "older")
    newer = source.insert("newer", now, "newer")

    # configure only one to be kept
    await model.sync(now)
    assert len(model.snapshots) == 1
    assert len(source.saved) == 0
    assert source.deleted == [older]
    assert len(source.saved) == 0
    assert newer.slug() in model.snapshots
    assert model.snapshots[newer.slug()].getSource(source.name()) == newer


@pytest.mark.asyncio
async def test_delete_dest(time, model, source, dest):
    now = time.now()

    # create two source snapshots
    dest.setMax(1)
    older = dest.insert("older", now - timedelta(minutes=1), "older")
    newer = dest.insert("newer", now, "newer")

    # configure only one to be kept
    await model.sync(now)
    assert len(model.snapshots) == 1
    assert len(dest.saved) == 0
    assert dest.deleted == [older]
    assert len(source.saved) == 0
    assert newer.slug() in model.snapshots
    assert model.snapshots[newer.slug()].getSource(dest.name()) == newer
    source.assertUnchanged()


@pytest.mark.asyncio
async def test_new_upload_with_delete(time, model, source, dest, simple_config):
    now = time.now()

    # create a single old snapshot
    source.setMax(1)
    dest.setMax(1)
    snapshot_dest = dest.insert("older", now - timedelta(days=1), "older")
    snapshot_source = source.insert("older", now - timedelta(days=1), "older")

    # configure only one to be kept in both places
    simple_config.config.update({
        "days_between_snapshots": 1
    })
    model.reinitialize()
    await model.sync(now)

    # Old snapshto shoudl be deleted, new one shoudl be created and uploaded.
    source.assertThat(current=1, created=1, deleted=1)
    dest.assertThat(current=1, saved=1, deleted=1)
    assert dest.deleted == [snapshot_dest]
    assert source.deleted == [snapshot_source]

    assert len(model.snapshots) == 1
    assertSnapshot(model, [source.created[0], dest.saved[0]])


@pytest.mark.asyncio
async def test_new_upload_no_delete(time, model, source, dest, simple_config):
    now = time.now()

    # create a single old snapshot
    source.setMax(2)
    dest.setMax(2)
    snapshot_dest = dest.insert("older", now - timedelta(days=1), "older")
    snapshot_source = source.insert("older", now - timedelta(days=1), "older")

    # configure keeping two in both places
    simple_config.config.update({
        "days_between_snapshots": 1
    })
    model.reinitialize()
    await model.sync(now)

    # Another snapshot should have been created and saved
    source.assertThat(current=2, created=1)
    dest.assertThat(current=2, saved=1)
    assert len(model.snapshots) == 2
    assertSnapshot(model, [source.created[0], dest.saved[0]])
    assertSnapshot(model, [snapshot_dest, snapshot_source])


@pytest.mark.asyncio
async def test_multiple_deletes_allowed(time, model, source, dest, simple_config):
    now = time.now()
    simple_config.config.update({"confirm_multiple_deletes": False})
    # create 4 snapshots in dest
    dest.setMax(1)

    current = dest.insert("current", now, "current")
    old = dest.insert("old", now - timedelta(days=1), "old")
    older = dest.insert("older", now - timedelta(days=2), "older")
    oldest = dest.insert("oldest", now - timedelta(days=3), "oldest")

    # configure keeping 1
    simple_config.config.update({
        "max_snapshots_in_google_drive": 1,
    })
    model.reinitialize()
    await model.sync(now)

    source.assertUnchanged()
    dest.assertThat(current=1, deleted=3)
    assert dest.deleted == [oldest, older, old]
    assert len(model.snapshots) == 1
    assertSnapshot(model, [current])


@pytest.mark.asyncio
async def test_confirm_multiple_deletes(time, model, source, dest, simple_config):
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

    with pytest.raises(DeleteMutlipleSnapshotsError) as thrown:
        await model.sync(now)

    thrown.value.data() == {
        source.name(): 2,
        dest.name(): 3
    }

    source.assertUnchanged()
    dest.assertUnchanged()


@pytest.mark.asyncio
async def test_dont_upload_deletable(time, model, source, dest):
    now = time.now()

    # a new snapshot in Drive and an old snapshot in HA
    dest.setMax(1)
    current = dest.insert("current", now, "current")
    old = source.insert("old", now - timedelta(days=1), "old")

    # configure keeping 1
    await model.sync(now)

    # Nothing should happen, because the upload from hassio would have to be deleted right after it's uploaded.
    source.assertUnchanged()
    dest.assertUnchanged()
    assert len(model.snapshots) == 2
    assertSnapshot(model, [current])
    assertSnapshot(model, [old])


@pytest.mark.asyncio
async def test_dont_upload_when_disabled(time, model, source, dest):
    now = time.now()

    # Make an enabled destination but with upload diabled.
    dest.setMax(1)
    dest.setUpload(False)

    await model.sync(now)

    # Verify the snapshot was created at the source but not uploaded.
    source.assertThat(current=1, created=1)
    dest.assertUnchanged()
    assert len(model.snapshots) == 1


@pytest.mark.asyncio
async def test_dont_delete_purgable(time, model, source, dest, simple_config):
    now = time.now()

    # create a single old snapshot, retained
    source.setMax(1)
    dest.setMax(1)
    snapshot_dest = dest.insert("older", now - timedelta(days=1), "older")
    snapshot_dest.setRetained(True)
    snapshot_source = source.insert("older", now - timedelta(days=1), "older")
    snapshot_source.setRetained(True)

    # configure only one to be kept in both places
    simple_config.config.update({
        "days_between_snapshots": 1
    })
    model.reinitialize()
    await model.sync(now)

    # Old snapshto shoudl be kept, new one should be created and uploaded.
    source.assertThat(current=2, created=1)
    dest.assertThat(current=2, saved=1)

    assert len(model.snapshots) == 2
    assertSnapshot(model, [snapshot_dest, snapshot_source])
    assertSnapshot(model, [source.created[0], dest.saved[0]])


@pytest.mark.asyncio
async def test_generational_delete(time, model, dest, source, simple_config):
    time.setNow(time.local(2019, 5, 10))
    now = time.now()

    # Create 4 snapshots, configured to keep 3
    source.setMax(3)
    source.insert("Fri", time.local(2019, 5, 10, 1))
    source.insert("Thu", time.local(2019, 5, 9, 1))
    wed = source.insert("Wed", time.local(2019, 5, 8, 1))
    source.insert("Mon", time.local(2019, 5, 6, 1))

    # configure only one to be kept in both places
    simple_config.config.update({
        "days_between_snapshots": 1,
        "generational_weeks": 1,
        "generational_days": 2
    })
    model.reinitialize()
    await model.sync(now)

    # Shoud only delete wed, since it isn't kept in the generational backup config
    source.assertThat(current=3, deleted=1)
    assert source.deleted == [wed]
    assert len(model.snapshots) == 3
    dest.assertThat(current=3, saved=3)


def assertSnapshot(model, sources):
    matches = {}
    for source in sources:
        matches[source.source()] = source
        slug = source.slug()
    assert slug in model.snapshots
    assert model.snapshots[slug].sources == matches
