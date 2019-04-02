from typing import Dict, List, Tuple, Sequence, Optional
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
    def getOldest(self, snapshots: Sequence[Snapshot]) -> Optional[Snapshot]:
        return min(snapshots, default=None, key=lambda s: s.date())


class Partition(object):
    def __init__(self, start: datetime, end: datetime, prefer: datetime):
        self.start: datetime = start
        self.end: datetime = end
        self.prefer: datetime = prefer

    def select(self, snapshots: List[Snapshot]) -> Optional[Snapshot]:
        options: List[Snapshot] = []
        for snapshot in snapshots:
            if snapshot.date() >= self.start and snapshot.date() < self.end:
                options.append(snapshot)
        return min(options, default=None, key=lambda s: abs((s.date() - self.prefer).total_seconds()))


class GenerationalScheme(BackupScheme):
    def __init__(self, time: Time, partitions: Dict[str, int]):
        self.time: Time = time
        self.partitions: Dict[str, Any] = partitions
        pass

    def getOldest(self, to_segment: Sequence[Snapshot]) -> Optional[Snapshot]:
        snapshots: List[Snapshot] = list(to_segment)

        # build the list of dates we should partition by

        if len(snapshots) == 0:
            return None

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
        if 'day_of_week' in self.partitions and self.partitions['day_of_week'] in lookup:
            day_of_week = lookup[self.partitions['day_of_week']]
            

        last = self.time.toLocal(snapshots[len(snapshots) - 1].date())
        lookups: List[Partition] = []
        for x in range(0, self.partitions['days']):
            start = datetime(last.year, last.month, last.day, tzinfo=last.tzinfo) - timedelta(days=x)
            end = start + timedelta(days=1)
            lookups.append(Partition(start, end, start + timedelta(hours=12)))

        for x in range(0, self.partitions['weeks']):
            start = datetime(last.year, last.month, last.day, tzinfo=last.tzinfo) - timedelta(days=last.weekday()) - timedelta(weeks=x)
            end = start + timedelta(days=7)
            lookups.append(Partition(start, end, start + timedelta(days=day_of_week, hours=12)))

        for x in range(0, self.partitions['months']):
            year_offset = int(x / 12)
            month_offset = int(x % 12)
            if last.month - month_offset < 1:
                year_offset = year_offset + 1
                month_offset = month_offset - 12
            start = datetime(last.year - year_offset, last.month - month_offset, 1, tzinfo=last.tzinfo)
            weekday, days = monthrange(start.year, start.month)
            end = start + timedelta(days=days)
            lookups.append(Partition(start, end, start + timedelta(days=self.partitions['day_of_month'] - 1)))

        for x in range(0, self.partitions['years']):
            start = datetime(last.year - x, 1, 1, tzinfo=last.tzinfo)
            end = datetime(last.year - x + 1, 1, 1, tzinfo=last.tzinfo)
            lookups.append(Partition(start, end, start + timedelta(days=self.partitions['day_of_year'] - 1)))

        keepers = set()
        for lookup in lookups:
            keeper = lookup.select(snapshots)
            if keeper:
                keepers.add(keeper)

        for snapshot in snapshots:
            if snapshot not in keepers:
                return snapshot

        # no non-keep is invalid, so delete the oldest keeper
        return min(keepers, default=None, key=lambda s: s.date())

        
