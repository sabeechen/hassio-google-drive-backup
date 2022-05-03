from abc import ABC, abstractmethod
from calendar import monthrange
from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Set, Tuple

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
    def getOldest(self, backups: Sequence[Backup]) -> Tuple[str, Optional[Backup]]:
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
            return None, None
        return "default", min(backups, default=None, key=lambda s: s.date())

    def handleNaming(self, backups: Sequence[Backup]) -> None:
        for backup in backups:
            backup.setStatusDetail(None)


class Partition(object):
    def __init__(self, start: datetime, end: datetime, prefer: datetime, time: Time, details=None, delete_only: bool = False):
        self.start: datetime = start
        self.end: datetime = end
        self.prefer: datetime = prefer
        self.time = time
        self.details = details
        self.selected = None
        self._delete_only_partitions = delete_only

    def select(self, backups: List[Backup]) -> Optional[Backup]:
        options = list(RangeLookup(backups, lambda s: s.date()).matches(self.start, self.end - timedelta(milliseconds=1)))

        searcher = lambda s: self.day(s.date()) == self.day(self.prefer)

        preferred = list(filter(searcher, options))
        if len(preferred) > 0:
            self.selected = max(preferred, default=None, key=Backup.date)
        else:
            self.selected = min(options, default=None, key=Backup.date)
        return self.selected

    def delta(self) -> timedelta:
        return self.end - self.start

    def day(self, date: datetime):
        local = self.time.toLocal(date)
        return datetime(day=local.day, month=local.month, year=local.year)

    # True if the partition exists only to determine why a snapshot is getting deleted.
    @property
    def is_delete_only(self):
        return self._delete_only_partitions

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
        if self.config.days > 0:
            for x in range(0, self.config.days + 1):
                nextDay = currentDay + timedelta(days=1)
                lookups.append(
                    Partition(currentDay, nextDay, currentDay, self.time, "Day {0} of {1}".format(x + 1, self.config.days), delete_only=(x >= self.config.days)))
                currentDay = self.day(currentDay - timedelta(hours=12))

        if self.config.weeks > 0:
            for x in range(0, self.config.weeks + 1):
                start = self.time.local(last.year, last.month, last.day)
                start -= timedelta(days=last.weekday())
                start -= timedelta(weeks=x)
                end = start + timedelta(days=7)
                start += timedelta(days=day_of_week)
                lookups.append(Partition(start, end, start, self.time, "Week {0} of {1}".format(x + 1, self.config.weeks), delete_only=(x >= self.config.weeks)))

        if self.config.months > 0:
            for x in range(0, self.config.months + 1):
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
                    "{0} ({1} of {2} months)".format(start.strftime("%B"), x + 1, self.config.months), delete_only=(x >= self.config.months)))

        if self.config.years > 0:
            for x in range(0, self.config.years + 1):
                start = self.time.local(last.year - x, 1, 1)
                end = self.time.local(last.year - x + 1, 1, 1)
                lookups.append(Partition(
                    start, end, start + timedelta(days=self.config.day_of_year - 1), self.time,
                    "{0} ({1} of {2} years)".format(start.strftime("%Y"), x + 1, self.config.years), delete_only=(x >= self.config.years)))

        # Keep track of which backups are being saved for which time period.
        for lookup in lookups:
            lookup.select(backups)
        return lookups

    def getOldest(self, backups: Sequence[Backup]):
        if len(backups) == 0:
            return None, None

        sorted = list(backups)
        sorted.sort(key=lambda s: s.date())

        partitions = self._buildPartitions(sorted)
        keepers: Set[Backup] = set()
        for part in partitions:
            if part.selected is not None and not part.is_delete_only:
                keepers.add(part.selected)

        extras = []
        for backup in sorted:
            if backup not in keepers:
                extras.append(backup)

        if self.config.aggressive and len(extras) > 0:
            match = min(filter(lambda p: p.selected == extras[0], partitions), key=Partition.delta, default=None)
            if match is not None:
                return match, extras[0]
            return "default", extras[0]

        if len(sorted) <= self.count and not self.config.aggressive:
            return "default", None
        elif (self.config.aggressive or len(sorted) > self.count) and len(extras) > 0:
            return "default", min(extras, default=None, key=lambda s: s.date())
        elif len(sorted) > self.count:
            # no non-keep is invalid, so delete the oldest keeper
            return "default", min(keepers, default=None, key=lambda s: s.date())
        return None, None

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
