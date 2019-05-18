import pytest

from ..model import Model, SnapshotSource, CreateOptions
from ..snapshots import Snapshot, DummySnapshotSource
from ..exceptions import DeleteMutlipleSnapshotsError
from ..config import Config
from ..globalinfo import GlobalInfo
from .faketime import FakeTime
from datetime import datetime, timedelta, timezone
from dateutil.tz import gettz
from io import IOBase
from typing import Dict
test_tz = gettz('EST')

default_source = SnapshotSource()


def test_timeOfDay(mocker) -> None:
    time: FakeTime = FakeTime()
    info = GlobalInfo(time)

    config: Config = Config([])
    model: Model = Model(config, time, default_source, default_source, info)
    assert model.getTimeOfDay() is None

    config = Config({'snapshot_time_of_day': '00:00'})
    model = Model(config, time, default_source, default_source, info)
    assert model.getTimeOfDay() == (0, 0)

    config = Config({'snapshot_time_of_day': '23:59'})
    model = Model(config, time, default_source, default_source, info)
    assert model.getTimeOfDay() == (23, 59)

    config = Config({'snapshot_time_of_day': '24:59'})
    model = Model(config, time, default_source, default_source, info)
    assert model.getTimeOfDay() is None

    config = Config({'snapshot_time_of_day': '24:60'})
    model = Model(config, time, default_source, default_source, info)
    assert model.getTimeOfDay() is None

    config = Config({'snapshot_time_of_day': '-1:60'})
    model = Model(config, time, default_source, default_source, info)
    assert model.getTimeOfDay() is None

    config = Config({'snapshot_time_of_day': '24:-1'})
    model = Model(config, time, default_source, default_source, info)
    assert model.getTimeOfDay() is None

    config = Config({'snapshot_time_of_day': 'boop:60'})
    model = Model(config, time, default_source, default_source, info)
    assert model.getTimeOfDay() is None

    config = Config({'snapshot_time_of_day': '24:boop'})
    model = Model(config, time, default_source, default_source, info)
    assert model.getTimeOfDay() is None

    config = Config({'snapshot_time_of_day': '24:10:22'})
    model = Model(config, time, default_source, default_source, info)
    assert model.getTimeOfDay() is None

    config = Config({'snapshot_time_of_day': '10'})
    model = Model(config, time, default_source, default_source, info)
    assert model.getTimeOfDay() is None


def test_next_time():
    time: FakeTime = FakeTime()
    info = GlobalInfo(time)
    now: datetime = datetime(1985, 12, 6, 1, 0, 0).astimezone(timezone.utc)

    config: Config = Config({'days_between_snapshots': 0})
    model: Model = Model(config, time, default_source, default_source, info)
    assert model._nextSnapshot(now=now, last_snapshot=None) is None
    assert model._nextSnapshot(now=now, last_snapshot=now) is None

    config: Config = Config({'days_between_snapshots': 1})
    model: Model = Model(config, time, default_source, default_source, info)
    assert model._nextSnapshot(now=now, last_snapshot=None) == now - timedelta(minutes=1)
    assert model._nextSnapshot(now=now, last_snapshot=now) == now + timedelta(days=1)
    assert model._nextSnapshot(now=now, last_snapshot=now - timedelta(days=1)) == now
    assert model._nextSnapshot(now=now, last_snapshot=now + timedelta(days=1)) == now + timedelta(days=2)


def test_next_time_of_day():
    time: FakeTime = FakeTime()
    info = GlobalInfo(time)
    now: datetime = datetime(1985, 12, 6, 1, 0, 0).astimezone(timezone.utc)
    assert now == datetime(1985, 12, 6, 3, 0, tzinfo=test_tz)

    config: Config = Config({'days_between_snapshots': 1, 'snapshot_time_of_day': '08:00'})
    model: Model = Model(config, time, default_source, default_source, info)

    assert model._nextSnapshot(now=now, last_snapshot=None) == now - timedelta(minutes=1)
    assert model._nextSnapshot(now=now, last_snapshot=now - timedelta(days=1)) == now
    assert model._nextSnapshot(now=now, last_snapshot=now) == datetime(1985, 12, 6, 8, 0, tzinfo=test_tz)
    assert model._nextSnapshot(now=now, last_snapshot=datetime(1985, 12, 6, 8, 0, tzinfo=test_tz)) == datetime(1985, 12, 7, 8, 0, tzinfo=test_tz)
    assert model._nextSnapshot(now=datetime(1985, 12, 6, 8, 0, tzinfo=test_tz), last_snapshot=datetime(1985, 12, 6, 8, 0, tzinfo=test_tz)) == datetime(1985, 12, 7, 8, 0, tzinfo=test_tz)


def test_next_time_of_day_dest_disabled(model, time, source, dest):
    dest.setEnabled(True)
    assert model._nextSnapshot(now=time.now(), last_snapshot=None) == time.now() - timedelta(minutes=1)
    dest.setEnabled(False)
    assert model._nextSnapshot(now=time.now(), last_snapshot=None) is None


def test_sync_empty(model, time, source, dest):
    source.setEnabled(False)
    dest.setEnabled(False)
    model.sync(time.now())
    assert len(model.snapshots) == 0


def test_sync_single_source(model, source, dest, time):
    snapshot = source.create(CreateOptions(time.now(), "name"))
    dest.setEnabled(False)
    model.sync(time.now())
    assert len(model.snapshots) == 1
    assert snapshot.slug() in model.snapshots
    assert model.snapshots[snapshot.slug()].getSource(source.name()) is snapshot
    assert model.snapshots[snapshot.slug()].getSource(dest.name()) is None


def test_sync_source_and_dest(model, time, source, dest):
    snapshot_source = source.create(CreateOptions(time.now(), "name"))
    model._syncSnapshots([source, dest])
    assert len(model.snapshots) == 1

    snapshot_dest = dest.save(model.snapshots[snapshot_source.slug()])
    model._syncSnapshots([source, dest])
    assert len(model.snapshots) == 1
    assert model.snapshots[snapshot_source.slug()].getSource(source.name()) is snapshot_source
    assert model.snapshots[snapshot_source.slug()].getSource(dest.name()) is snapshot_dest


def test_sync_different_sources(model, time, source, dest):
    snapshot_source = source.create(CreateOptions(time.now(), "name"))
    snapshot_dest = dest.create(CreateOptions(time.now(), "name"))

    model._syncSnapshots([source, dest])
    assert len(model.snapshots) == 2
    assert model.snapshots[snapshot_source.slug()].getSource(source.name()) is snapshot_source
    assert model.snapshots[snapshot_dest.slug()].getSource(dest.name()) is snapshot_dest


def test_removal(model, time, source, dest):
    source.create(CreateOptions(time.now(), "name"))
    model._syncSnapshots([source, dest])
    assert len(model.snapshots) == 1
    source.current = {}
    model._syncSnapshots([source, dest])
    assert len(model.snapshots) == 0


def test_new_snapshot(model, source, dest, time):
    model.sync(time.now())
    assert len(model.snapshots) == 1
    assert len(source.created) == 1
    assert source.created[0].date() == time.now()
    assert len(source.current) == 1
    assert len(dest.current) == 1


def test_upload_snapshot(time, model, dest, source):
    dest.setEnabled(True)
    model.sync(time.now())
    assert len(model.snapshots) == 1
    source.assertThat(created=1, current=1)
    assert len(source.created) == 1
    assert source.created[0].date() == time.now()
    assert len(source.current) == 1
    assert len(dest.current) == 1
    assert len(dest.saved) == 1


def test_disabled(time, model, source, dest):
    # create two disabled sources
    source.setEnabled(False)
    source.insert("newer", time.now(), "slug1")
    dest.setEnabled(False)
    dest.insert("s2", time.now(), "slug2")
    model.sync(time.now())
    source.assertUnchanged()
    dest.assertUnchanged()
    assert len(model.snapshots) == 0


def test_delete_source(time, model, source, dest):
    time = FakeTime()
    now = time.now()

    # create two source snapshots
    source.setMax(1)
    older = source.insert("older", now - timedelta(minutes=1), "older")
    newer = source.insert("newer", now, "newer")

    # configure only one to be kept
    model.sync(now)
    assert len(model.snapshots) == 1
    assert len(source.saved) == 0
    assert source.deleted == [older]
    assert len(source.saved) == 0
    assert newer.slug() in model.snapshots
    assert model.snapshots[newer.slug()].getSource(source.name()) == newer


def test_delete_dest(time, model, source, dest):
    now = time.now()

    # create two source snapshots
    dest.setMax(1)
    older = dest.insert("older", now - timedelta(minutes=1), "older")
    newer = dest.insert("newer", now, "newer")

    # configure only one to be kept
    model.sync(now)
    assert len(model.snapshots) == 1
    assert len(dest.saved) == 0
    assert dest.deleted == [older]
    assert len(source.saved) == 0
    assert newer.slug() in model.snapshots
    assert model.snapshots[newer.slug()].getSource(dest.name()) == newer
    source.assertUnchanged()


def test_new_upload_with_delete(time, model, source, dest, simple_config):
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
    model.sync(now)

    # Old snapshto shoudl be deleted, new one shoudl be created and uploaded.
    source.assertThat(current=1, created=1, deleted=1)
    dest.assertThat(current=1, saved=1, deleted=1)
    assert dest.deleted == [snapshot_dest]
    assert source.deleted == [snapshot_source]

    assert len(model.snapshots) == 1
    assertSnapshot(model, [source.created[0], dest.saved[0]])


def test_new_upload_no_delete(time, model, source, dest, simple_config):
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
    model.sync(now)

    # Another snapshot should have been created and saved
    source.assertThat(current=2, created=1)
    dest.assertThat(current=2, saved=1)
    assert len(model.snapshots) == 2
    assertSnapshot(model, [source.created[0], dest.saved[0]])
    assertSnapshot(model, [snapshot_dest, snapshot_source])


def test_multiple_deletes_allowed(time, model, source, dest, simple_config):
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
    model.sync(now)

    source.assertUnchanged()
    dest.assertThat(current=1, deleted=3)
    assert dest.deleted == [oldest, older, old]
    assert len(model.snapshots) == 1
    assertSnapshot(model, [current])


def test_confirm_multiple_deletes(time, model, source, dest, simple_config):
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
        model.sync(now)

    thrown.value.data() == {
        source.name(): 2,
        dest.name(): 3
    }

    source.assertUnchanged()
    dest.assertUnchanged()


def test_dont_upload_deletable(time, model, source, dest):
    now = time.now()

    # a new snapshot in Drive and an old snapshot in HA
    dest.setMax(1)
    current = dest.insert("current", now, "current")
    old = source.insert("old", now - timedelta(days=1), "old")

    # configure keeping 1
    model.sync(now)

    # Nothing should happen, because the upload from hassio would have to be deleted right after it's uploaded.
    source.assertUnchanged()
    dest.assertUnchanged()
    assert len(model.snapshots) == 2
    assertSnapshot(model, [current])
    assertSnapshot(model, [old])


def test_dont_delete_purgable(time, model, source, dest, simple_config):
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
    model.sync(now)

    # Old snapshto shoudl be kept, new one should be created and uploaded.
    source.assertThat(current=2, created=1)
    dest.assertThat(current=2, saved=1)

    assert len(model.snapshots) == 2
    assertSnapshot(model, [snapshot_dest, snapshot_source])
    assertSnapshot(model, [source.created[0], dest.saved[0]])


def test_generational_delete(time, model, dest, source, simple_config):
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
    model.sync(now)

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


class TestSource(SnapshotSource[DummySnapshotSource]):
    def __init__(self, name):
        self._name = name
        self.current: Dict[str, DummySnapshotSource] = {}
        self.saved = []
        self.deleted = []
        self.created = []
        self._enabled = True
        self.index = 0
        self.max = 0

    def setEnabled(self, value):
        self._enabled = value
        return self

    def setMax(self, count):
        self.max = count
        return self

    def maxCount(self) -> None:
        return self.max

    def insert(self, name, date, slug=None):
        if slug is None:
            slug = name
        new_snapshot = DummySnapshotSource(
            name,
            date,
            self._name,
            slug)
        self.current[new_snapshot.slug()] = new_snapshot
        return new_snapshot

    def reset(self):
        self.saved = []
        self.deleted = []
        self.created = []

    def assertThat(self, created=0, deleted=0, saved=0, current=0):
        assert len(self.saved) == saved
        assert len(self.deleted) == deleted
        assert len(self.created) == created
        assert len(self.current) == current
        return self

    def assertUnchanged(self):
        self.assertThat(current=len(self.current))
        return self

    def name(self) -> str:
        return self._name

    def enabled(self) -> bool:
        return self._enabled

    def create(self, options: CreateOptions) -> DummySnapshotSource:
        assert self.enabled
        new_snapshot = DummySnapshotSource(
            "{0} snapshot {1}".format(self._name, self.index),
            options.when,
            self._name,
            "{0}slug{1}".format(self._name, self.index))
        self.index += 1
        self.current[new_snapshot.slug()] = new_snapshot
        self.created.append(new_snapshot)
        return new_snapshot

    def get(self) -> Dict[str, DummySnapshotSource]:
        assert self.enabled
        return self.current

    def delete(self, snapshot: Snapshot):
        assert self.enabled
        assert snapshot.getSource(self._name) is not None
        assert snapshot.getSource(self._name).source() is self._name
        assert snapshot.slug() in self.current
        self.deleted.append(snapshot.getSource(self._name))
        del self.current[snapshot.slug()]

    def save(self, snapshot: Snapshot, bytes: IOBase = None) -> DummySnapshotSource:
        assert self.enabled
        assert snapshot.slug() not in self.current
        new_snapshot = DummySnapshotSource(snapshot.name(), snapshot.date, self._name, snapshot.slug())
        snapshot.addSource(new_snapshot)
        self.current[new_snapshot.slug()] = new_snapshot
        self.saved.append(new_snapshot)
        return new_snapshot

    def read(self, snapshot: DummySnapshotSource) -> IOBase:
        assert self.enabled
        return None

    def retain(self, snapshot: DummySnapshotSource, retain: bool) -> None:
        assert self.enabled
        pass
