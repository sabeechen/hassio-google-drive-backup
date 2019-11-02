from typing import List, Sequence, Optional
from abc import ABC, abstractmethod
from .snapshots import Snapshot
from .time import Time
from datetime import datetime
from datetime import timedelta
from calendar import monthrange


class BackupScheme(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def getOldest(self, snapshots: Sequence[Snapshot]) -> Optional[Snapshot]:
        pass


class OldestScheme(BackupScheme):
    def __init__(self, count=0):
        self.count = count

    def getOldest(self, snapshots: Sequence[Snapshot]) -> Optional[Snapshot]:
        if len(snapshots) <= self.count:
            return None
        return min(snapshots, default=None, key=lambda s: s.date())


class Partition(object):
    def __init__(self, start: datetime, end: datetime, prefer: datetime, time: Time):
        self.start: datetime = start
        self.end: datetime = end
        self.prefer: datetime = prefer
        self.time = time

    def select(self, snapshots: List[Snapshot]) -> Optional[Snapshot]:
        options: List[Snapshot] = []
        for snapshot in snapshots:
            if snapshot.date() >= self.start and snapshot.date() < self.end:
                options.append(snapshot)

        preferred = list(filter(lambda s: self.day(s.date()) == self.day(self.prefer), options))
        if len(preferred) > 0:
            return max(preferred, default=None, key=lambda s: s.date())

        return min(options, default=None, key=lambda s: s.date())

    def day(self, date: datetime):
        local = self.time.toLocal(date)
        return datetime(day=local.day, month=local.month, year=local.year)


class GenConfig():
    def __init__(self, days=0, weeks=0, months=0, years=0, day_of_week='mon', day_of_month=1, day_of_year=1, aggressive=False):
        self.days = days
        self.weeks = weeks
        self.months = months
        self.years = years
        self.day_of_week = day_of_week
        self.day_of_month = day_of_month
        self.day_of_year = day_of_year
        self.aggressive = aggressive

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, GenConfig):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __hash__(self):
        """Overrides the default implementation"""
        return hash(tuple(sorted(self.__dict__.items())))


class GenerationalScheme(BackupScheme):
    def __init__(self, time: Time, config: GenConfig, count=0):
        self.count = count
        self.time: Time = time
        self.config = config

    def getOldest(self, to_segment: Sequence[Snapshot]) -> Optional[Snapshot]:
        snapshots: List[Snapshot] = list(to_segment)

        if len(snapshots) == 0:
            return None

        # build the list of dates we should partition by
        snapshots.sort(key=lambda s: s.date())
        day_of_week = 3
        lookup = {
            'mon': 0,
            'tue': 1,
            'wed': 2,
            'thu': 3,
            'fri': 4,
            'sat': 5,
            'sun': 6,
        }
        if self.config.day_of_week in lookup:
            day_of_week = lookup[self.config.day_of_week]

        last = self.time.toLocal(snapshots[len(snapshots) - 1].date())
        lookups: List[Partition] = []
        currentDay = self.day(last)
        for x in range(0, self.config.days):
            lookups.append(Partition(currentDay, currentDay + timedelta(days=1), currentDay, self.time))
            currentDay = self.day(currentDay - timedelta(hours=12))

        for x in range(0, self.config.weeks):
            start = self.time.local(last.year, last.month, last.day) - timedelta(days=last.weekday()) - timedelta(weeks=x)
            end = start + timedelta(days=7)
            lookups.append(Partition(start, end, start + timedelta(days=day_of_week), self.time))

        for x in range(0, self.config.months):
            year_offset = int(x / 12)
            month_offset = int(x % 12)
            if last.month - month_offset < 1:
                year_offset = year_offset + 1
                month_offset = month_offset - 12
            start = self.time.local(last.year - year_offset, last.month - month_offset, 1)
            weekday, days = monthrange(start.year, start.month)
            end = start + timedelta(days=days)
            lookups.append(Partition(start, end, start + timedelta(days=self.config.day_of_month - 1), self.time))

        for x in range(0, self.config.years):
            start = self.time.local(last.year - x, 1, 1)
            end = self.time.local(last.year - x + 1, 1, 1)
            lookups.append(Partition(start, end, start + timedelta(days=self.config.day_of_year - 1), self.time))

        keepers = set()
        for lookup in lookups:
            keeper = lookup.select(snapshots)
            if keeper:
                keepers.add(keeper)
            else:
                print("whoops")
                pass

        extras = []
        for snapshot in snapshots:
            if snapshot not in keepers:
                if self.config.aggressive:
                    return snapshot
                else:
                    extras.append(snapshot)

        if len(to_segment) <= self.count and not self.config.aggressive:
            return None
        elif (self.config.aggressive or len(to_segment) > self.count) and len(extras) > 0:
            return min(extras, default=None, key=lambda s: s.date())
        elif len(to_segment) > self.count:
            # no non-keep is invalid, so delete the oldest keeper
            return min(keepers, default=None, key=lambda s: s.date())

    def day(self, date: datetime):
        local = self.time.toLocal(date)
        return datetime(day=local.day, month=local.month, year=local.year, tzinfo=local.tzinfo)
