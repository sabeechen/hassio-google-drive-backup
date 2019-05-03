from ..model import Model, SnapshotSource
from ..time import Time
from ..config import Config
from datetime import datetime, timedelta, timezone
from dateutil.tz import gettz, tzutc
test_tz = gettz('EST')

default_source = SnapshotSource()

def test_timeOfDay(mocker) -> None:
    time: Time = Time(local_tz=test_tz)

    config: Config = Config([])
    model: Model = Model(config, time, default_source, default_source)
    assert model.getTimeOfDay() is None

    config = Config([], extra_config={'snapshot_time_of_day': '00:00'})
    model = Model(config, time, default_source, default_source)
    assert model.getTimeOfDay() == (0, 0)

    config = Config([], extra_config={'snapshot_time_of_day': '23:59'})
    model = Model(config, time, default_source, default_source)
    assert model.getTimeOfDay() == (23, 59)

    config = Config([], extra_config={'snapshot_time_of_day': '24:59'})
    model = Model(config, time, default_source, default_source)
    assert model.getTimeOfDay() is None

    config = Config([], extra_config={'snapshot_time_of_day': '24:60'})
    model = Model(config, time, default_source, default_source)
    assert model.getTimeOfDay() is None

    config = Config([], extra_config={'snapshot_time_of_day': '-1:60'})
    model = Model(config, time, default_source, default_source)
    assert model.getTimeOfDay() is None

    config = Config([], extra_config={'snapshot_time_of_day': '24:-1'})
    model = Model(config, time, default_source, default_source)
    assert model.getTimeOfDay() is None

    config = Config([], extra_config={'snapshot_time_of_day': 'boop:60'})
    model = Model(config, time, default_source, default_source)
    assert model.getTimeOfDay() is None

    config = Config([], extra_config={'snapshot_time_of_day': '24:boop'})
    model = Model(config, time, default_source, default_source)
    assert model.getTimeOfDay() is None

    config = Config([], extra_config={'snapshot_time_of_day': '24:10:22'})
    model = Model(config, time, default_source, default_source)
    assert model.getTimeOfDay() is None

    config = Config([], extra_config={'snapshot_time_of_day': '10'})
    model = Model(config, time, default_source, default_source)
    assert model.getTimeOfDay() is None


def test_next_time():
    time: Time = Time(local_tz=test_tz)
    now: datetime = datetime(1985, 12, 6, 1, 0, 0).astimezone(timezone.utc)

    config: Config = Config([], extra_config={'days_between_snapshots': 0})
    model: Model = Model(config, time, default_source, default_source)
    assert model.nextSnapshot(now=now, last_snapshot=None) is None
    assert model.nextSnapshot(now=now, last_snapshot=now) is None

    config: Config = Config([], extra_config={'days_between_snapshots': 1})
    model: Model = Model(config, time, default_source, default_source)
    assert model.nextSnapshot(now=now, last_snapshot=None) == now
    assert model.nextSnapshot(now=now, last_snapshot=now) == now + timedelta(days=1)
    assert model.nextSnapshot(now=now, last_snapshot=now - timedelta(days=1)) == now
    assert model.nextSnapshot(now=now, last_snapshot=now + timedelta(days=1)) == now + timedelta(days=2)


def test_next_time_of_day():
    time: Time = Time(local_tz=test_tz)
    now: datetime = datetime(1985, 12, 6, 1, 0, 0).astimezone(timezone.utc)
    assert now == datetime(1985, 12, 6, 3, 0, tzinfo=test_tz)

    config: Config = Config([], extra_config={'days_between_snapshots': 1, 'snapshot_time_of_day': '08:00'})
    model: Model = Model(config, time, default_source, default_source)

    assert model.nextSnapshot(now=now, last_snapshot=None) == now
    assert model.nextSnapshot(now=now, last_snapshot=now - timedelta(days=1)) == now
    assert model.nextSnapshot(now=now, last_snapshot=now) == datetime(1985, 12, 6, 8, 0, tzinfo=test_tz)
    assert model.nextSnapshot(now=now, last_snapshot=datetime(1985, 12, 6, 8, 0, tzinfo=test_tz)) == datetime(1985, 12, 7, 8, 0, tzinfo=test_tz)
    assert model.nextSnapshot(now=datetime(1985, 12, 6, 8, 0, tzinfo=test_tz), last_snapshot=datetime(1985, 12, 6, 8, 0, tzinfo=test_tz)) == datetime(1985, 12, 7, 8, 0, tzinfo=test_tz)
