import pytest
import mock 

from ..engine import Engine
from ..time import Time
from ..drive import Drive
from ..hassio import Hassio
from ..config import Config
from ..snapshots import Snapshot, HASnapshot, DriveSnapshot
from ..backupscheme import GenerationalScheme
from ..backupscheme import OldestScheme
from pytest_mock import mocker
from datetime import datetime, timedelta, timezone
from dateutil.tz import gettz
from dateutil.tz import tzutc

base_date: datetime = datetime(1985, 12, 6, 1, 0, 0, tzinfo=timezone.utc)
next_minute: datetime = datetime(1985, 12, 6, 1, 1, 0, tzinfo=timezone.utc)
prev_minute: datetime = datetime(1985, 12, 6, 0, 59, 0, tzinfo=timezone.utc)
next_day: datetime = datetime(1985, 12, 7, 1, 0, 0, tzinfo=timezone.utc)
test_tz = gettz('Egypt Standard Time')


def test_trivial(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = {
        'days': 1, 
        'weeks': 0, 
        'months': 0, 
        'years': 0
    }

    scheme = GenerationalScheme(time, config)

    snapshots = [
        makeHASnapshot("single", datetime(1928, 12, 6, tzinfo=test_tz))
    ]

    assert scheme.getOldest(snapshots).date() == datetime(1928, 12, 6, tzinfo=test_tz)


def test_trivial_oldest(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = {
        'days': 1,
        'weeks': 0,
        'months': 0,
        'years': 0
    }
    scheme = GenerationalScheme(time, config)

    snapshots = [
        makeHASnapshot("test", datetime(1985, 12, 6, 10, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 12, 6, 12, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 12, 6, 13, tzinfo=test_tz))
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1985, 12, 6, 10, tzinfo=test_tz),
        datetime(1985, 12, 6, 13, tzinfo=test_tz),
        datetime(1985, 12, 6, 12, tzinfo=test_tz)
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

    scheme = GenerationalScheme(time, config)

    snapshots = [
        makeHASnapshot("test", datetime(1985, 12, 5, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 12, 4, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 12, 1, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 12, 2, tzinfo=test_tz))
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1985, 12, 1, tzinfo=test_tz),
        datetime(1985, 12, 2, tzinfo=test_tz),
        datetime(1985, 12, 5, tzinfo=test_tz),
        datetime(1985, 12, 4, tzinfo=test_tz)
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

    scheme = GenerationalScheme(time, config)

    snapshots = [
        makeHASnapshot("test", datetime(1985, 12, 6, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 12, 2, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 11, 20, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 11, 1, tzinfo=test_tz))
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1985, 11, 1, tzinfo=test_tz),
        datetime(1985, 12, 2, tzinfo=test_tz),
        datetime(1985, 11, 20, tzinfo=test_tz),
        datetime(1985, 12, 6, tzinfo=test_tz)
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

    scheme = GenerationalScheme(time, config)

    snapshots = [
        makeHASnapshot("test", datetime(1985, 12, 31, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 1, 1, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1984, 12, 31, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1984, 1, 1, tzinfo=test_tz))
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1984, 12, 31, tzinfo=test_tz),
        datetime(1985, 12, 31, tzinfo=test_tz),
        datetime(1984, 1, 1, tzinfo=test_tz),
        datetime(1985, 1, 1, tzinfo=test_tz)
    ]

def test_removal_order(mocker) -> None:
    time: Time = getMockTime(mocker, base_date)
    config = {
        'days': 5,

        'weeks': 2,
        'day_of_week': 'mon',

        'months': 2,
        'day_of_month' : 15,

        'years': 2,
        'day_of_year': 1
    }
    
    scheme = GenerationalScheme(time, config)

    snapshots = [
        # 5 days, week 1
        makeHASnapshot("test", datetime(1985, 12, 7, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 12, 6, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 12, 5, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 12, 4, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 12, 3, tzinfo=test_tz)),

        # week 2
        makeHASnapshot("test", datetime(1985, 12, 1, tzinfo=test_tz)),  # sun, first to go
        makeHASnapshot("test", datetime(1985, 11, 25, tzinfo=test_tz)),  # mon

        # month2
        makeHASnapshot("test", datetime(1985, 11, 15, tzinfo=test_tz)),

        # year 1
        makeHASnapshot("test", datetime(1985, 1, 1, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1985, 1, 2, tzinfo=test_tz)),

        # year 2
        makeHASnapshot("test", datetime(1984, 6, 1, tzinfo=test_tz)),
        makeHASnapshot("test", datetime(1984, 7, 1, tzinfo=test_tz)),

        # year 3
        makeHASnapshot("test", datetime(1983, 1, 1, tzinfo=test_tz)),
    ]
    assert getRemovalOrder(scheme, snapshots) == [
        datetime(1983, 1, 1, tzinfo=test_tz),
        datetime(1984, 7, 1, tzinfo=test_tz),
        datetime(1985, 1, 2, tzinfo=test_tz),
        datetime(1985, 12, 1, tzinfo=test_tz),
        datetime(1984, 6, 1, tzinfo=test_tz),
        datetime(1985, 1, 1, tzinfo=test_tz),
        datetime(1985, 11, 15, tzinfo=test_tz),
        datetime(1985, 11, 25, tzinfo=test_tz),
        datetime(1985, 12, 3, tzinfo=test_tz),
        datetime(1985, 12, 4, tzinfo=test_tz),
        datetime(1985, 12, 5, tzinfo=test_tz),
        datetime(1985, 12, 6, tzinfo=test_tz),
        datetime(1985, 12, 7, tzinfo=test_tz)
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

    scheme = GenerationalScheme(time, config)
    num_snapshots = 16
    today = datetime(2019, 1, 1, tzinfo=test_tz)
    snapshots = []
    while today < datetime(2023, 1, 1, tzinfo=test_tz):
        snapshots.append(makeHASnapshot("test", today))
        while len(snapshots) > num_snapshots:
            snapshots.remove(scheme.getOldest(snapshots))
        today = today + timedelta(days=1)
    
    assert getRemovalOrder(scheme, snapshots) == [
        # 4 years
        datetime(2019, 1, 1, tzinfo=test_tz),
        datetime(2020, 1, 1, tzinfo=test_tz),
        datetime(2021, 1, 1, tzinfo=test_tz),
        datetime(2022, 1, 1, tzinfo=test_tz),

        # 4 months
        datetime(2022, 9, 1, tzinfo=test_tz),
        datetime(2022, 10, 1, tzinfo=test_tz),
        datetime(2022, 11, 1, tzinfo=test_tz),
        datetime(2022, 12, 1, tzinfo=test_tz),

        # 4 weeks
        datetime(2022, 12, 5, tzinfo=test_tz),
        datetime(2022, 12, 12, tzinfo=test_tz),
        datetime(2022, 12, 19, tzinfo=test_tz),
        datetime(2022, 12, 26, tzinfo=test_tz),

        # 4 days
        datetime(2022, 12, 28, tzinfo=test_tz),
        datetime(2022, 12, 29, tzinfo=test_tz),
        datetime(2022, 12, 30, tzinfo=test_tz),
        datetime(2022, 12, 31, tzinfo=test_tz),
    ]


def getRemovalOrder(scheme, toCheck):
    snapshots = list(toCheck)
    removed = []
    while len(snapshots) > 0:
        oldest = scheme.getOldest(snapshots)
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


def makeHASnapshot(slug, date, name=None) -> HASnapshot:
    if not name:
        name = slug
    return Snapshot(HASnapshot({"slug": slug, "date": str(date.astimezone(tzutc())), "name": name}))
