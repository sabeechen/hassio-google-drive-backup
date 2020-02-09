from datetime import datetime, timedelta

import pytest
from dateutil.tz import tzutc
from pytest import fail

from ..backupscheme import GenConfig, GenerationalScheme
from ..snapshots import DummySnapshot, Snapshot
from ..time import Time


def test_timezone(time) -> None:
    assert time.local_tz is not None


def test_trivial(time) -> None:
    config = GenConfig(days=1)

    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        makeSnapshot("single", time.local(1928, 12, 6))
    ]

    assert scheme.getOldest(snapshots).date() == time.local(1928, 12, 6)


def test_trivial_empty(time):
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
    assertRemovalOrder(scheme, snapshots, [
        time.local(1985, 12, 6, 10),
        time.local(1985, 12, 6, 12),
        time.local(1985, 12, 6, 13)
    ])


def test_duplicate_weeks(time):
    config = GenConfig(weeks=1, day_of_week='wed')

    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        makeSnapshot("test", time.local(1985, 12, 5)),
        makeSnapshot("test", time.local(1985, 12, 4)),
        makeSnapshot("test", time.local(1985, 12, 1)),
        makeSnapshot("test", time.local(1985, 12, 2))
    ]
    assertRemovalOrder(scheme, snapshots, [
        time.local(1985, 12, 1),
        time.local(1985, 12, 2),
        time.local(1985, 12, 5),
        time.local(1985, 12, 4)
    ])


def test_duplicate_months(time) -> None:
    config = GenConfig(months=2, day_of_month=15)

    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        makeSnapshot("test", time.local(1985, 12, 6)),
        makeSnapshot("test", time.local(1985, 12, 15)),
        makeSnapshot("test", time.local(1985, 11, 20)),
        makeSnapshot("test", time.local(1985, 11, 15))
    ]
    assertRemovalOrder(scheme, snapshots, [
        time.local(1985, 11, 20),
        time.local(1985, 12, 6),
        time.local(1985, 11, 15),
        time.local(1985, 12, 15)
    ])


def test_duplicate_years(time):
    config = GenConfig(years=2, day_of_year=1)

    scheme = GenerationalScheme(time, config, count=0)

    snapshots = [
        makeSnapshot("test", time.local(1985, 12, 31)),
        makeSnapshot("test", time.local(1985, 1, 1)),
        makeSnapshot("test", time.local(1984, 12, 31)),
        makeSnapshot("test", time.local(1984, 1, 1))
    ]
    assertRemovalOrder(scheme, snapshots, [
        time.local(1984, 12, 31),
        time.local(1985, 12, 31),
        time.local(1984, 1, 1),
        time.local(1985, 1, 1)
    ])


def test_removal_order(time) -> None:
    config = GenConfig(days=5, weeks=2, months=2, years=2,
                       day_of_week='mon', day_of_month=15, day_of_year=1)

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
    assertRemovalOrder(scheme, snapshots, [
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


@pytest.mark.timeout(60)
def test_simulate_daily_backup_for_4_years(time):
    config = GenConfig(days=4, weeks=4, months=4, years=4,
                       day_of_week='mon', day_of_month=1, day_of_year=1)
    scheme = GenerationalScheme(time, config, count=16)
    snapshots = simulate(time.local(2019, 1, 1),
                         time.local(2022, 12, 31), scheme)
    assertRemovalOrder(GenerationalScheme(time, config, count=0), snapshots, [
        # 4 years
        time.local(2019, 1, 1),
        time.local(2020, 1, 1),
        time.local(2021, 1, 1),
        time.local(2022, 1, 1),

        # 4 months
        time.local(2022, 9, 1),
        time.local(2022, 10, 1),
        time.local(2022, 11, 1),
        time.local(2022, 12, 1),

        # 4 weeks
        time.local(2022, 12, 5),
        time.local(2022, 12, 12),
        time.local(2022, 12, 19),
        time.local(2022, 12, 26),

        # 4 days
        time.local(2022, 12, 28),
        time.local(2022, 12, 29),
        time.local(2022, 12, 30),
        time.local(2022, 12, 31)
    ])


@pytest.mark.timeout(60)
def test_simulate_agressive_daily_backup_for_4_years(time):
    config = GenConfig(days=4, weeks=4, months=4, years=4,
                       day_of_week='mon', day_of_month=1, day_of_year=1, aggressive=True)
    scheme = GenerationalScheme(time, config, count=16)
    snapshots = simulate(time.local(2019, 1, 1),
                         time.local(2022, 12, 31), scheme)

    assertRemovalOrder(GenerationalScheme(time, config, count=0), snapshots, [
        # 4 years
        time.local(2019, 1, 1),
        time.local(2020, 1, 1),
        time.local(2021, 1, 1),
        time.local(2022, 1, 1),

        # 4 months
        time.local(2022, 9, 1),
        time.local(2022, 10, 1),
        time.local(2022, 11, 1),
        time.local(2022, 12, 1),

        # 4 weeks
        time.local(2022, 12, 5),
        time.local(2022, 12, 12),
        time.local(2022, 12, 19),
        time.local(2022, 12, 26),

        # 4 days
        time.local(2022, 12, 28),
        time.local(2022, 12, 29),
        time.local(2022, 12, 30),
        time.local(2022, 12, 31),
    ])


def test_count_limit(time):
    config = GenConfig(years=2, day_of_year=1)
    scheme = GenerationalScheme(time, config, count=1)
    snapshots = [
        makeSnapshot("test", time.local(1985, 1, 1)),
        makeSnapshot("test", time.local(1984, 1, 1))
    ]
    assertRemovalOrder(scheme, snapshots, [
        time.local(1984, 1, 1)
    ])


def test_aggressive_removal_below_limit(time):
    config = GenConfig(years=2, day_of_year=1, aggressive=True)
    scheme = GenerationalScheme(time, config, count=5)
    snapshots = [
        makeSnapshot("test", time.local(1985, 1, 1)),
        makeSnapshot("test", time.local(1985, 1, 2))
    ]
    assertRemovalOrder(scheme, snapshots, [
        time.local(1985, 1, 2)
    ])


def test_aggressive_removal_at_limit_ok(time):
    config = GenConfig(years=2, day_of_year=1, aggressive=True)
    scheme = GenerationalScheme(time, config, count=2)
    snapshots = [
        makeSnapshot("test", time.local(1985, 1, 1)),
        makeSnapshot("test", time.local(1984, 1, 1))
    ]
    assertRemovalOrder(scheme, snapshots, [])


def test_aggressive_removal_over_limit(time):
    config = GenConfig(years=2, day_of_year=1, aggressive=True)
    scheme = GenerationalScheme(time, config, count=2)
    snapshots = [
        makeSnapshot("test", time.local(1985, 1, 1)),
        makeSnapshot("test", time.local(1984, 1, 1)),
        makeSnapshot("test", time.local(1983, 1, 1)),
        makeSnapshot("test", time.local(1983, 1, 2))
    ]
    assertRemovalOrder(scheme, snapshots, [
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
    assertRemovalOrder(scheme, snapshots, [
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
    assertRemovalOrder(scheme, snapshots, [
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
    assertRemovalOrder(scheme, snapshots, [
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
        removed.append(oldest.date())
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
                fail("at index {0}, expected 'None' but got {1}".format(
                    index, time.toLocal(oldest.date())))
            break
        if oldest.date() != expected[index]:
            fail("at index {0}, expected {1} but got {2}".format(
                index, time.toLocal(expected[index]), time.toLocal(oldest.date())))
        removed.append(oldest.date())
        snapshots.remove(oldest)
        index += 1
    return removed


def makeSnapshot(slug, date, name=None) -> Snapshot:
    if not name:
        name = slug
    return DummySnapshot(name, date.astimezone(tzutc()), "src", slug)


def simulate(start: datetime, end: datetime, scheme: GenerationalScheme, snapshots=[]):
    today = start
    while today <= end:
        snapshots.append(makeSnapshot("test", today))
        oldest = scheme.getOldest(snapshots)
        while oldest is not None:
            snapshots.remove(oldest)
            oldest = scheme.getOldest(snapshots)
        today = today + timedelta(hours=27)
        today = scheme.time.local(today.year, today.month, today.day)
    return snapshots
