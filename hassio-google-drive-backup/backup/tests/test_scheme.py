from ..time import Time
from ..backupscheme import GenerationalScheme, GenConfig
from ..snapshots import Snapshot, DummySnapshot
from datetime import datetime, timedelta, timezone
from dateutil.tz import gettz
from dateutil.tz import tzutc
from pytest import fail

base_date: datetime = datetime(1985, 12, 6, 1, 0, 0).astimezone(timezone.utc)
next_minute: datetime = datetime(1985, 12, 6, 1, 1, 0).astimezone(timezone.utc)
prev_minute: datetime = datetime(1985, 12, 6, 0, 59, 0).astimezone(timezone.utc)
next_day: datetime = datetime(1985, 12, 7, 1, 0, 0).astimezone(timezone.utc)
test_tz = gettz('America/Chicago')


def test_timezone() -> None:
    assert test_tz is not None


def test_trivial(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = GenConfig(days=1)

    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        makeSnapshot("single", datetime(1928, 12, 6).astimezone(test_tz))
    ]

    assert scheme.getOldest(snapshots).date() == datetime(1928, 12, 6).astimezone(test_tz)


def test_trivial_empty(mocker):
    time: Time = getMockTime(mocker, base_date)
    config = GenConfig(days=1)
    scheme = GenerationalScheme(time, config, count=0)
    assert scheme.getOldest([]) is None


def test_trivial_oldest(time: Time) -> None:
    config = GenConfig(days=1)
    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        makeSnapshot("test", time.local(1985, 12, 6, 10)),
        makeSnapshot("test", time.local(1985, 12, 6, 12)),
        makeSnapshot("test", time.local(1985, 12, 6, 13))
    ]
    assert assertRemovalOrder(scheme, snapshots, [
        time.local(1985, 12, 6, 10),
        time.local(1985, 12, 6, 12),
        time.local(1985, 12, 6, 13)
    ])


def test_duplicate_weeks(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = GenConfig(weeks=1, day_of_week='wed')

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


def test_duplicate_months(time) -> None:
    config = GenConfig(months=2, day_of_month=15)

    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        makeSnapshot("test", time.local(1985, 12, 6)),
        makeSnapshot("test", time.local(1985, 12, 15)),
        makeSnapshot("test", time.local(1985, 11, 20)),
        makeSnapshot("test", time.local(1985, 11, 15))
    ]
    assert assertRemovalOrder(scheme, snapshots, [
        time.local(1985, 11, 20),
        time.local(1985, 12, 6),
        time.local(1985, 11, 15),
        time.local(1985, 12, 15)
    ])


def test_duplicate_years(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = GenConfig(years=2, day_of_year=1)

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


def test_removal_order(time) -> None:
    config = GenConfig(days=5, weeks=2, months=2, years=2, day_of_week='mon', day_of_month=15, day_of_year=1)

    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        # 5 days, week 1
        makeSnapshot("test", time.local(1985, 12, 7)),  # day 1
        makeSnapshot("test", time.local(1985, 12, 6)),  # day 2
        makeSnapshot("test", time.local(1985, 12, 5)),  # day 3
        makeSnapshot("test", time.local(1985, 12, 4)),  # day 4
        makeSnapshot("test", time.local(1985, 12, 3)),  # day 5

        makeSnapshot("test", time.local(1985, 12, 1)),  # 1st week pref

        # week 2
        makeSnapshot("test", time.local(1985, 11, 25)),  # 1st month pref

        # month2
        makeSnapshot("test", time.local(1985, 11, 15)),  # 2nd month pref

        # year 1
        makeSnapshot("test", time.local(1985, 1, 1)),  # 1st year preference
        makeSnapshot("test", time.local(1985, 1, 2)),

        # year 2
        makeSnapshot("test", time.local(1984, 6, 1)),  # 2nd year pref
        makeSnapshot("test", time.local(1984, 7, 1)),

        # year 3
        makeSnapshot("test", time.local(1983, 1, 1)),
    ]
    assert assertRemovalOrder(scheme, snapshots, [
        time.local(1983, 1, 1),
        time.local(1984, 7, 1),
        time.local(1985, 1, 2),

        time.local(1984, 6, 1),
        time.local(1985, 1, 1),
        time.local(1985, 11, 15),
        time.local(1985, 11, 25),
        time.local(1985, 12, 1),
        time.local(1985, 12, 3),
        time.local(1985, 12, 4),
        time.local(1985, 12, 5),
        time.local(1985, 12, 6),
        time.local(1985, 12, 7)
    ])


def test_simulate_daily_backup_for_4_years(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = GenConfig(days=4, weeks=4, months=4, years=4, day_of_week='mon', day_of_month=1, day_of_year=1)

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


def test_simulate_agressive_daily_backup_for_4_years(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = GenConfig(days=4, weeks=4, months=4, years=4, day_of_week='mon', day_of_month=1, day_of_year=1, aggressive=True)

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
    config = GenConfig(years=2, day_of_year=1)

    scheme = GenerationalScheme(time, config, count=1)

    snapshots = [
        makeSnapshot("test", datetime(1985, 1, 1).astimezone(test_tz)),
        makeSnapshot("test", datetime(1984, 1, 1).astimezone(test_tz))
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1984, 1, 1).astimezone(test_tz)
    ]


def test_aggressive_removal_below_limit(mocker):
    time: Time = getMockTime(mocker, base_date)
    config = GenConfig(years=2, day_of_year=1, aggressive=True)

    scheme = GenerationalScheme(time, config, count=5)

    snapshots = [
        makeSnapshot("test", datetime(1985, 1, 1).astimezone(test_tz)),
        makeSnapshot("test", datetime(1985, 1, 2).astimezone(test_tz))
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1985, 1, 2).astimezone(test_tz)
    ]


def test_aggressive_removal_at_limit_ok(mocker):
    time: Time = getMockTime(mocker, base_date)
    config = GenConfig(years=2, day_of_year=1, aggressive=True)

    scheme = GenerationalScheme(time, config, count=2)

    snapshots = [
        makeSnapshot("test", datetime(1985, 1, 1).astimezone(test_tz)),
        makeSnapshot("test", datetime(1984, 1, 1).astimezone(test_tz))
    ]
    assert getRemovalOrder(scheme, snapshots) == []


def test_aggressive_removal_over_limit(time):
    config = GenConfig(years=2, day_of_year=1, aggressive=True)

    scheme = GenerationalScheme(time, config, count=2)

    snapshots = [
        makeSnapshot("test", time.local(1985, 1, 1)),
        makeSnapshot("test", time.local(1984, 1, 1)),
        makeSnapshot("test", time.local(1983, 1, 1)),
        makeSnapshot("test", time.local(1983, 1, 2))
    ]
    assert assertRemovalOrder(scheme, snapshots, [
        time.local(1983, 1, 1),
        time.local(1983, 1, 2)
    ])


def test_removal_order_week(time: Time):
    config = GenConfig(weeks=1, day_of_week='wed', aggressive=True)

    scheme = GenerationalScheme(time, config, count=1)

    snapshots = [
        makeSnapshot("test", time.local(2019, 10, 28)),
        makeSnapshot("test", time.local(2019, 10, 29)),
        makeSnapshot("test", time.local(2019, 10, 30, 1)),
        makeSnapshot("test", time.local(2019, 10, 30, 2)),
        makeSnapshot("test", time.local(2019, 10, 31)),
        makeSnapshot("test", time.local(2019, 11, 1)),
        makeSnapshot("test", time.local(2019, 11, 2)),
        makeSnapshot("test", time.local(2019, 11, 3)),
    ]
    assertRemovalOrder(scheme, snapshots, [
        time.local(2019, 10, 28),
        time.local(2019, 10, 29),
        time.local(2019, 10, 30, 1),
        time.local(2019, 10, 31),
        time.local(2019, 11, 1),
        time.local(2019, 11, 2),
        time.local(2019, 11, 3)
    ])


def test_removal_order_month(time):
    config = GenConfig(months=1, day_of_month=20, aggressive=True)

    scheme = GenerationalScheme(time, config, count=1)

    snapshots = [
        makeSnapshot("test", time.local(2019, 1, 1)),
        makeSnapshot("test", time.local(2019, 1, 2)),
        makeSnapshot("test", time.local(2019, 1, 20, 1)),
        makeSnapshot("test", time.local(2019, 1, 20, 2)),
        makeSnapshot("test", time.local(2019, 1, 21)),
        makeSnapshot("test", time.local(2019, 1, 25)),
        makeSnapshot("test", time.local(2019, 1, 26)),
        makeSnapshot("test", time.local(2019, 1, 27)),
    ]
    assert assertRemovalOrder(scheme, snapshots, [
        time.local(2019, 1, 1),
        time.local(2019, 1, 2),
        time.local(2019, 1, 20, 1),
        time.local(2019, 1, 21),
        time.local(2019, 1, 25),
        time.local(2019, 1, 26),
        time.local(2019, 1, 27)
    ])


def test_removal_order_many_months(time):
    config = GenConfig(months=70, day_of_month=20, aggressive=True)

    scheme = GenerationalScheme(time, config, count=10)

    snapshots = [
        makeSnapshot("test", time.local(2019, 7, 20)),  # preferred
        makeSnapshot("test", time.local(2018, 7, 18)),  # preferred
        makeSnapshot("test", time.local(2018, 7, 21)),
        makeSnapshot("test", time.local(2017, 1, 19)),
        makeSnapshot("test", time.local(2017, 1, 20)),  # preferred
        makeSnapshot("test", time.local(2017, 1, 31)),
        makeSnapshot("test", time.local(2016, 12, 1)),  # preferred
        makeSnapshot("test", time.local(2014, 1, 31)),
        makeSnapshot("test", time.local(2014, 1, 1)),  # preferred
    ]
    assert assertRemovalOrder(scheme, snapshots, [
        time.local(2014, 1, 31),
        time.local(2017, 1, 19),
        time.local(2017, 1, 31),
        time.local(2018, 7, 21),
    ])


def test_removal_order_years(time):
    config = GenConfig(years=2, day_of_year=15, aggressive=True)

    scheme = GenerationalScheme(time, config, count=10)

    snapshots = [
        makeSnapshot("test", time.local(2019, 2, 15)),
        makeSnapshot("test", time.local(2019, 1, 15)),  # keep
        makeSnapshot("test", time.local(2018, 1, 14)),
        makeSnapshot("test", time.local(2018, 1, 15)),  # keep
        makeSnapshot("test", time.local(2018, 1, 16)),
        makeSnapshot("test", time.local(2017, 1, 15)),
    ]
    assert assertRemovalOrder(scheme, snapshots, [
        time.local(2017, 1, 15),
        time.local(2018, 1, 14),
        time.local(2018, 1, 16),
        time.local(2019, 2, 15),
    ])


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


def assertRemovalOrder(scheme, toCheck, expected):
    snapshots = list(toCheck)
    removed = []
    index = 0
    time = scheme.time
    while True:
        oldest = scheme.getOldest(snapshots)
        if index >= len(expected):
            if oldest is not None:
                fail("at index {0}, expected 'None' but got {1}".format(index, time.toLocal(oldest.date())))
            break
        if oldest.date() != expected[index]:
            fail("at index {0}, expected {1} but got {2}".format(index, time.toLocal(expected[index]), time.toLocal(oldest.date())))
        removed.append(oldest.date().astimezone(test_tz))
        snapshots.remove(oldest)
        index += 1
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
