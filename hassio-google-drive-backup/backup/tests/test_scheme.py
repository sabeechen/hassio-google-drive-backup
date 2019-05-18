from ..time import Time
from ..backupscheme import GenerationalScheme
from ..snapshots import Snapshot, DummySnapshot
from datetime import datetime, timedelta, timezone
from dateutil.tz import gettz
from dateutil.tz import tzutc

base_date: datetime = datetime(1985, 12, 6, 1, 0, 0).astimezone(timezone.utc)
next_minute: datetime = datetime(1985, 12, 6, 1, 1, 0).astimezone(timezone.utc)
prev_minute: datetime = datetime(1985, 12, 6, 0, 59, 0).astimezone(timezone.utc)
next_day: datetime = datetime(1985, 12, 7, 1, 0, 0).astimezone(timezone.utc)
test_tz = gettz('America/Chicago')


def test_timezone() -> None:
    assert test_tz is not None


def test_trivial(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = {
        'days': 1,
        'weeks': 0,
        'months': 0,
        'years': 0
    }

    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        makeSnapshot("single", datetime(1928, 12, 6).astimezone(test_tz))
    ]

    assert scheme.getOldest(snapshots).date() == datetime(1928, 12, 6).astimezone(test_tz)


def test_trivial_oldest(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = {
        'days': 1,
        'weeks': 0,
        'months': 0,
        'years': 0
    }
    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        makeSnapshot("test", datetime(1985, 12, 6, 10).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 12, 6, 12).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 12, 6, 13).astimezone(test_tz))
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1985, 12, 6, 10).astimezone(test_tz),
        datetime(1985, 12, 6, 13).astimezone(test_tz),
        datetime(1985, 12, 6, 12).astimezone(test_tz)
    ]


def test_duplicate_weeks(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = {
        'days': 0,
        'weeks': 1,
        'day_of_week': 'wed',
        'months': 0,
        'years': 0
    }

    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        makeSnapshot("test", datetime(1985, 12, 5).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 12, 4).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 12, 1).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 12, 2).astimezone(test_tz))
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1985, 12, 1).astimezone(test_tz),
        datetime(1985, 12, 2).astimezone(test_tz),
        datetime(1985, 12, 5).astimezone(test_tz),
        datetime(1985, 12, 4).astimezone(test_tz)
    ]


def test_duplicate_months(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = {
        'days': 0,
        'weeks': 0,
        'months': 2,
        'day_of_month': 15,
        'years': 0
    }

    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        makeSnapshot("test", datetime(1985, 12, 6).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 12, 2).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 11, 20).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 11, 1).astimezone(test_tz))
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1985, 11, 1).astimezone(test_tz),
        datetime(1985, 12, 2).astimezone(test_tz),
        datetime(1985, 11, 20).astimezone(test_tz),
        datetime(1985, 12, 6).astimezone(test_tz)
    ]


def test_duplicate_years(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = {
        'days': 0,
        'weeks': 0,
        'months': 0,
        'years': 2,
        'day_of_year': 1
    }

    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        makeSnapshot("test", datetime(1985, 12, 31).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 1, 1).astimezone(test_tz)),
        makeSnapshot("test", datetime(1984, 12, 31).astimezone(test_tz)),
        makeSnapshot("test", datetime(1984, 1, 1).astimezone(test_tz))
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1984, 12, 31).astimezone(test_tz),
        datetime(1985, 12, 31).astimezone(test_tz),
        datetime(1984, 1, 1).astimezone(test_tz),
        datetime(1985, 1, 1).astimezone(test_tz)
    ]


def test_removal_order(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = {
        'days': 5,

        'weeks': 2,
        'day_of_week': 'mon',

        'months': 2,
        'day_of_month': 15,

        'years': 2,
        'day_of_year': 1
    }

    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        # 5 days, week 1
        makeSnapshot("test", datetime(1985, 12, 7).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 12, 6).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 12, 5).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 12, 4).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 12, 3).astimezone(test_tz)),

        # week 2
        makeSnapshot("test", datetime(1985, 12, 1).astimezone(test_tz)),  # sun, first to go
        makeSnapshot("test", datetime(1985, 11, 25).astimezone(test_tz)),  # mon

        # month2
        makeSnapshot("test", datetime(1985, 11, 15).astimezone(test_tz)),

        # year 1
        makeSnapshot("test", datetime(1985, 1, 1).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 1, 2).astimezone(test_tz)),

        # year 2
        makeSnapshot("test", datetime(1984, 6, 1).astimezone(test_tz)),
        makeSnapshot("test", datetime(1984, 7, 1).astimezone(test_tz)),

        # year 3
        makeSnapshot("test", datetime(1983, 1, 1).astimezone(test_tz)),
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1983, 1, 1).astimezone(test_tz),
        datetime(1984, 7, 1).astimezone(test_tz),
        datetime(1985, 1, 2).astimezone(test_tz),
        datetime(1985, 12, 1).astimezone(test_tz),
        datetime(1984, 6, 1).astimezone(test_tz),
        datetime(1985, 1, 1).astimezone(test_tz),
        datetime(1985, 11, 15).astimezone(test_tz),
        datetime(1985, 11, 25).astimezone(test_tz),
        datetime(1985, 12, 3).astimezone(test_tz),
        datetime(1985, 12, 4).astimezone(test_tz),
        datetime(1985, 12, 5).astimezone(test_tz),
        datetime(1985, 12, 6).astimezone(test_tz),
        datetime(1985, 12, 7).astimezone(test_tz)
    ]


def test_simulate_daily_backup_for_4_years(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = {
        'days': 4,
        'weeks': 4,
        'day_of_week': 'mon',
        'months': 4,
        'day_of_month': 1,
        'years': 4,
        'day_of_year': 1
    }

    scheme = GenerationalScheme(time, config, count=0)
    num_snapshots = 16
    today = datetime(2019, 1, 1).astimezone(test_tz)
    snapshots = []
    while today < datetime(2023, 1, 1).astimezone(test_tz):
        snapshots.append(makeSnapshot("test", today))
        while len(snapshots) > num_snapshots:
            snapshots.remove(scheme.getOldest(snapshots))
        today = today + timedelta(days=1)
    order = getRemovalOrder(scheme, snapshots)
    assert order == [
        # 4 years
        datetime(2019, 1, 1).astimezone(test_tz),
        datetime(2020, 1, 1).astimezone(test_tz),
        datetime(2021, 1, 1).astimezone(test_tz),
        datetime(2022, 1, 1).astimezone(test_tz),

        # 4 months
        datetime(2022, 9, 1).astimezone(test_tz),
        datetime(2022, 10, 1).astimezone(test_tz),
        datetime(2022, 11, 1).astimezone(test_tz),
        datetime(2022, 12, 1).astimezone(test_tz),

        # 4 weeks
        datetime(2022, 12, 5).astimezone(test_tz),
        datetime(2022, 12, 12).astimezone(test_tz),
        datetime(2022, 12, 19).astimezone(test_tz),
        datetime(2022, 12, 26).astimezone(test_tz),

        # 4 days
        datetime(2022, 12, 28).astimezone(test_tz),
        datetime(2022, 12, 29).astimezone(test_tz),
        datetime(2022, 12, 30).astimezone(test_tz),
        datetime(2022, 12, 31).astimezone(test_tz),
    ]


def test_count_limit(mocker):
    time: Time = getMockTime(mocker, base_date)
    config = {
        'days': 0,
        'weeks': 0,
        'months': 0,
        'years': 2,
        'day_of_year': 1
    }

    scheme = GenerationalScheme(time, config, count=1)

    snapshots = [
        makeSnapshot("test", datetime(1985, 1, 1).astimezone(test_tz)),
        makeSnapshot("test", datetime(1984, 1, 1).astimezone(test_tz))
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1984, 1, 1).astimezone(test_tz)
    ]


def getRemovalOrder(scheme, toCheck):
    snapshots = list(toCheck)
    removed = []
    while True:
        oldest = scheme.getOldest(snapshots)
        if not oldest:
            break
        removed.append(oldest.date().astimezone(test_tz))
        snapshots.remove(oldest)
    return removed


def getMockTime(mocker, mock_time=datetime.now()):
    time: Time = Time(local_tz=test_tz)
    mocker.patch.object(time, 'now')
    time.now.return_value = mock_time

    mocker.patch.object(time, 'nowLocal')
    time.nowLocal.return_Value = time.toLocal(mock_time)
    return time


def makeSnapshot(slug, date, name=None) -> Snapshot:
    if not name:
        name = slug
    return DummySnapshot(name, date.astimezone(tzutc()), "src", slug)
