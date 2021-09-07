from abc import ABC, abstractmethod
from calendar import monthrange
from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Set

from .backups import Backup
from backup.util import RangeLookup
from ..time import Time
from ..config import GenConfig
from ..logger import getLogger
logger = getLogger(__name__)


class BackupScheme(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def getOldest(self, backups: Sequence[Backup]) -> Optional[Backup]:
        pass

    def handleNaming(self, backups: Sequence[Backup]) -> None:
        for backup in backups:
            backup.setStatusDetail(None)


class DeleteAfterUploadScheme(BackupScheme):
    def __init__(self, source: str, destinations: List[str]):
        self.source = source
        self.destinations = destinations

    def getOldest(self, backups: Backup):
        consider = []
        for backup in backups:
            uploaded = True
            if backup.getSource(self.source) is None:
                # No source, so ignore it
                uploaded = False
            for destination in self.destinations:
                if backup.getSource(destination) is None:
                    # its not in destination, so ignore it
                    uploaded = False
            if uploaded:
                consider.append(backup)

        # Delete the oldest first
        return OldestScheme().getOldest(consider)


class OldestScheme(BackupScheme):
    def __init__(self, count=0):
        self.count = count

    def getOldest(self, backups: Sequence[Backup]) -> Optional[Backup]:
        if len(backups) <= self.count:
            return None
        return min(backups, default=None, key=lambda s: s.date())

    def handleNaming(self, backups: Sequence[Backup]) -> None:
        for backup in backups:
            backup.setStatusDetail(None)


class Partition(object):
    def __init__(self, start: datetime, end: datetime, prefer: datetime, time: Time, details=None):
        self.start: datetime = start
        self.end: datetime = end
        self.prefer: datetime = prefer
        self.time = time
        self.details = details
        self.selected = None

    def select(self, backups: List[Backup]) -> Optional[Backup]:
        options = list(RangeLookup(backups, lambda s: s.date()).matches(self.start, self.end - timedelta(milliseconds=1)))

        searcher = lambda s: self.day(s.date()) == self.day(self.prefer)

        preferred = list(filter(searcher, options))
        if len(preferred) > 0:
            self.selected = max(preferred, default=None, key=Backup.date)
        else:
            self.selected = min(options, default=None, key=Backup.date)
        return self.selected

    def day(self, date: datetime):
        local = self.time.toLocal(date)
        return datetime(day=local.day, month=local.month, year=local.year)

    def __hash__(self):
        """Overrides the default implementation"""
        return hash(tuple(sorted(self.__dict__.items())))


class GenerationalScheme(BackupScheme):
    def __init__(self, time: Time, config: GenConfig, count=0):
        self.count = count
        self.time: Time = time
        self.config = config

    def _buildPartitions(self, backups):
        backups: List[Backup] = list(backups)

        # build the list of dates we should partition by
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

        last = self.time.toLocal(backups[len(backups) - 1].date())
        lookups: List[Partition] = []
        currentDay = self.day(last)
        for x in range(0, self.config.days):
            nextDay = currentDay + timedelta(days=1)
            lookups.append(
                Partition(currentDay, nextDay, currentDay, self.time, "Day {0} of {1}".format(x + 1, self.config.days)))
            currentDay = self.day(currentDay - timedelta(hours=12))

        for x in range(0, self.config.weeks):
            start = self.time.local(last.year, last.month, last.day)
            start -= timedelta(days=last.weekday())
            start -= timedelta(weeks=x)
            end = start + timedelta(days=7)
            start += timedelta(days=day_of_week)
            lookups.append(Partition(start, end, start, self.time, "Week {0} of {1}".format(x + 1, self.config.weeks)))

        for x in range(0, self.config.months):
            year_offset = int(x / 12)
            month_offset = int(x % 12)
            if last.month - month_offset < 1:
                year_offset = year_offset + 1
                month_offset = month_offset - 12
            start = self.time.local(
                last.year - year_offset, last.month - month_offset, 1)
            weekday, days = monthrange(start.year, start.month)
            end = start + timedelta(days=days)
            lookups.append(Partition(
                start, end, start + timedelta(days=self.config.day_of_month - 1), self.time,
                "{0} ({1} of {2} months)".format(start.strftime("%B"), x + 1, self.config.months)))

        for x in range(0, self.config.years):
            start = self.time.local(last.year - x, 1, 1)
            end = self.time.local(last.year - x + 1, 1, 1)
            lookups.append(Partition(
                start, end, start + timedelta(days=self.config.day_of_year - 1), self.time,
                "{0} ({1} of {2} years)".format(start.strftime("%Y"), x + 1, self.config.years)))

        # Keep track of which backups are being saved for which time period.
        for lookup in lookups:
            lookup.select(backups)
        return lookups

    def getOldest(self, backups: Sequence[Backup]) -> Optional[Backup]:
        if len(backups) == 0:
            return None

        sorted = list(backups)
        sorted.sort(key=lambda s: s.date())

        partitions = self._buildPartitions(sorted)
        keepers: Set[Backup] = set()
        for part in partitions:
            if part.selected is not None:
                keepers.add(part.selected)

        extras = []
        for backup in sorted:
            if backup not in keepers:
                extras.append(backup)

        if self.config.aggressive and len(extras) > 0:
            return extras[0]

        if len(sorted) <= self.count and not self.config.aggressive:
            return None
        elif (self.config.aggressive or len(sorted) > self.count) and len(extras) > 0:
            return min(extras, default=None, key=lambda s: s.date())
        elif len(sorted) > self.count:
            # no non-keep is invalid, so delete the oldest keeper
            return min(keepers, default=None, key=lambda s: s.date())

    def handleNaming(self, backups: Sequence[Backup]) -> None:
        if len(backups) == 0:
            return
        sorted = list(backups)
        sorted.sort(key=lambda s: s.date())
        for backup in sorted:
            backup.setStatusDetail(None)
        for part in self._buildPartitions(sorted):
            if part.selected is not None:
                if part.selected.getStatusDetail() is None:
                    part.selected.setStatusDetail([])
                part.selected.getStatusDetail().append(part.details)

    def day(self, date: datetime):
        local = self.time.toLocal(date)
        return datetime(day=local.day, month=local.month, year=local.year, tzinfo=local.tzinfo)
