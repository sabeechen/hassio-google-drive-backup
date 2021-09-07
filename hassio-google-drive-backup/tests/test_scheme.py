from datetime import datetime, timedelta

import pytest
from dateutil.tz import tzutc
from pytest import fail

from backup.model import GenConfig, GenerationalScheme, DummyBackup, Backup
from backup.time import Time


def test_timezone(time) -> None:
    assert time.local_tz is not None


def test_trivial(time) -> None:
    config = GenConfig(days=1)

    scheme = GenerationalScheme(time, config, count=0)

    backups = [
        makeBackup("single", time.local(1928, 12, 6))
    ]

    assert scheme.getOldest(backups).date() == time.local(1928, 12, 6)


def test_trivial_empty(time):
    config = GenConfig(days=1)
    scheme = GenerationalScheme(time, config, count=0)
    assert scheme.getOldest([]) is None


def test_trivial_oldest(time: Time) -> None:
    config = GenConfig(days=1)
    scheme = GenerationalScheme(time, config, count=0)

    backups = [
        makeBackup("test", time.local(1985, 12, 6, 10)),
        makeBackup("test", time.local(1985, 12, 6, 12)),
        makeBackup("test", time.local(1985, 12, 6, 13))
    ]
    assertRemovalOrder(scheme, backups, [
        time.local(1985, 12, 6, 10),
        time.local(1985, 12, 6, 12),
        time.local(1985, 12, 6, 13)
    ])


def test_duplicate_weeks(time):
    config = GenConfig(weeks=1, day_of_week='wed')

    scheme = GenerationalScheme(time, config, count=0)

    backups = [
        makeBackup("test", time.local(1985, 12, 5)),
        makeBackup("test", time.local(1985, 12, 4)),
        makeBackup("test", time.local(1985, 12, 1)),
        makeBackup("test", time.local(1985, 12, 2))
    ]
    assertRemovalOrder(scheme, backups, [
        time.local(1985, 12, 1),
        time.local(1985, 12, 2),
        time.local(1985, 12, 5),
        time.local(1985, 12, 4)
    ])


def test_duplicate_months(time) -> None:
    config = GenConfig(months=2, day_of_month=15)

    scheme = GenerationalScheme(time, config, count=0)

    backups = [
        makeBackup("test", time.local(1985, 12, 6)),
        makeBackup("test", time.local(1985, 12, 15)),
        makeBackup("test", time.local(1985, 11, 20)),
        makeBackup("test", time.local(1985, 11, 15))
    ]
    assertRemovalOrder(scheme, backups, [
        time.local(1985, 11, 20),
        time.local(1985, 12, 6),
        time.local(1985, 11, 15),
        time.local(1985, 12, 15)
    ])


def test_duplicate_years(time):
    config = GenConfig(years=2, day_of_year=1)

    scheme = GenerationalScheme(time, config, count=0)

    backups = [
        makeBackup("test", time.local(1985, 12, 31)),
        makeBackup("test", time.local(1985, 1, 1)),
        makeBackup("test", time.local(1984, 12, 31)),
        makeBackup("test", time.local(1984, 1, 1))
    ]
    assertRemovalOrder(scheme, backups, [
        time.local(1984, 12, 31),
        time.local(1985, 12, 31),
        time.local(1984, 1, 1),
        time.local(1985, 1, 1)
    ])


def test_removal_order(time) -> None:
    config = GenConfig(days=5, weeks=2, months=2, years=2,
                       day_of_week='mon', day_of_month=15, day_of_year=1)

    scheme = GenerationalScheme(time, config, count=0)

    backups = [
        # 5 days, week 1
        makeBackup("test", time.local(1985, 12, 7)),  # day 1
        makeBackup("test", time.local(1985, 12, 6)),  # day 2
        makeBackup("test", time.local(1985, 12, 5)),  # day 3
        makeBackup("test", time.local(1985, 12, 4)),  # day 4
        makeBackup("test", time.local(1985, 12, 3)),  # day 5

        makeBackup("test", time.local(1985, 12, 1)),  # 1st week pref

        # week 2
        makeBackup("test", time.local(1985, 11, 25)),  # 1st month pref

        # month2
        makeBackup("test", time.local(1985, 11, 15)),  # 2nd month pref

        # year 1
        makeBackup("test", time.local(1985, 1, 1)),  # 1st year preference
        makeBackup("test", time.local(1985, 1, 2)),

        # year 2
        makeBackup("test", time.local(1984, 6, 1)),  # 2nd year pref
        makeBackup("test", time.local(1984, 7, 1)),

        # year 3
        makeBackup("test", time.local(1983, 1, 1)),
    ]
    assertRemovalOrder(scheme, backups, [
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
    backups = simulate(time.local(2019, 1, 1),
                         time.local(2022, 12, 31), scheme)
    assertRemovalOrder(GenerationalScheme(time, config, count=0), backups, [
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
    backups = simulate(time.local(2019, 1, 1),
                         time.local(2022, 12, 31), scheme)

    assertRemovalOrder(GenerationalScheme(time, config, count=0), backups, [
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
    backups = [
        makeBackup("test", time.local(1985, 1, 1)),
        makeBackup("test", time.local(1984, 1, 1))
    ]
    assertRemovalOrder(scheme, backups, [
        time.local(1984, 1, 1)
    ])


def test_aggressive_removal_below_limit(time):
    config = GenConfig(years=2, day_of_year=1, aggressive=True)
    scheme = GenerationalScheme(time, config, count=5)
    backups = [
        makeBackup("test", time.local(1985, 1, 1)),
        makeBackup("test", time.local(1985, 1, 2))
    ]
    assertRemovalOrder(scheme, backups, [
        time.local(1985, 1, 2)
    ])


def test_aggressive_removal_at_limit_ok(time):
    config = GenConfig(years=2, day_of_year=1, aggressive=True)
    scheme = GenerationalScheme(time, config, count=2)
    backups = [
        makeBackup("test", time.local(1985, 1, 1)),
        makeBackup("test", time.local(1984, 1, 1))
    ]
    assertRemovalOrder(scheme, backups, [])


def test_aggressive_removal_over_limit(time):
    config = GenConfig(years=2, day_of_year=1, aggressive=True)
    scheme = GenerationalScheme(time, config, count=2)
    backups = [
        makeBackup("test", time.local(1985, 1, 1)),
        makeBackup("test", time.local(1984, 1, 1)),
        makeBackup("test", time.local(1983, 1, 1)),
        makeBackup("test", time.local(1983, 1, 2))
    ]
    assertRemovalOrder(scheme, backups, [
        time.local(1983, 1, 1),
        time.local(1983, 1, 2)
    ])


def test_removal_order_week(time: Time):
    config = GenConfig(weeks=1, day_of_week='wed', aggressive=True)
    scheme = GenerationalScheme(time, config, count=1)
    backups = [
        makeBackup("test", time.local(2019, 10, 28)),
        makeBackup("test", time.local(2019, 10, 29)),
        makeBackup("test", time.local(2019, 10, 30, 1)),
        makeBackup("test", time.local(2019, 10, 30, 2)),
        makeBackup("test", time.local(2019, 10, 31)),
        makeBackup("test", time.local(2019, 11, 1)),
        makeBackup("test", time.local(2019, 11, 2)),
        makeBackup("test", time.local(2019, 11, 3)),
    ]
    assertRemovalOrder(scheme, backups, [
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

    backups = [
        makeBackup("test", time.local(2019, 1, 1)),
        makeBackup("test", time.local(2019, 1, 2)),
        makeBackup("test", time.local(2019, 1, 20, 1)),
        makeBackup("test", time.local(2019, 1, 20, 2)),
        makeBackup("test", time.local(2019, 1, 21)),
        makeBackup("test", time.local(2019, 1, 25)),
        makeBackup("test", time.local(2019, 1, 26)),
        makeBackup("test", time.local(2019, 1, 27)),
    ]
    assertRemovalOrder(scheme, backups, [
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

    backups = [
        makeBackup("test", time.local(2019, 7, 20)),  # preferred
        makeBackup("test", time.local(2018, 7, 18)),  # preferred
        makeBackup("test", time.local(2018, 7, 21)),
        makeBackup("test", time.local(2017, 1, 19)),
        makeBackup("test", time.local(2017, 1, 20)),  # preferred
        makeBackup("test", time.local(2017, 1, 31)),
        makeBackup("test", time.local(2016, 12, 1)),  # preferred
        makeBackup("test", time.local(2014, 1, 31)),
        makeBackup("test", time.local(2014, 1, 1)),  # preferred
    ]
    assertRemovalOrder(scheme, backups, [
        time.local(2014, 1, 31),
        time.local(2017, 1, 19),
        time.local(2017, 1, 31),
        time.local(2018, 7, 21),
    ])


def test_removal_order_years(time):
    config = GenConfig(years=2, day_of_year=15, aggressive=True)

    scheme = GenerationalScheme(time, config, count=10)

    backups = [
        makeBackup("test", time.local(2019, 2, 15)),
        makeBackup("test", time.local(2019, 1, 15)),  # keep
        makeBackup("test", time.local(2018, 1, 14)),
        makeBackup("test", time.local(2018, 1, 15)),  # keep
        makeBackup("test", time.local(2018, 1, 16)),
        makeBackup("test", time.local(2017, 1, 15)),
    ]
    assertRemovalOrder(scheme, backups, [
        time.local(2017, 1, 15),
        time.local(2018, 1, 14),
        time.local(2018, 1, 16),
        time.local(2019, 2, 15),
    ])


def getRemovalOrder(scheme, toCheck):
    backups = list(toCheck)
    removed = []
    while True:
        oldest = scheme.getOldest(backups)
        if not oldest:
            break
        removed.append(oldest.date())
        backups.remove(oldest)
    return removed


def assertRemovalOrder(scheme, toCheck, expected):
    backups = list(toCheck)
    removed = []
    index = 0
    time = scheme.time
    while True:
        oldest = scheme.getOldest(backups)
        if index >= len(expected):
            if oldest is not None:
                fail("at index {0}, expected 'None' but got {1}".format(
                    index, time.toLocal(oldest.date())))
            break
        if oldest.date() != expected[index]:
            fail("at index {0}, expected {1} but got {2}".format(
                index, time.toLocal(expected[index]), time.toLocal(oldest.date())))
        removed.append(oldest.date())
        backups.remove(oldest)
        index += 1
    return removed


def makeBackup(slug, date, name=None) -> Backup:
    if not name:
        name = slug
    return DummyBackup(name, date.astimezone(tzutc()), "src", slug)


def simulate(start: datetime, end: datetime, scheme: GenerationalScheme, backups=[]):
    today = start
    while today <= end:
        backups.append(makeBackup("test", today))
        oldest = scheme.getOldest(backups)
        while oldest is not None:
            backups.remove(oldest)
            oldest = scheme.getOldest(backups)
        today = today + timedelta(hours=27)
        today = scheme.time.local(today.year, today.month, today.day)
    return backups
