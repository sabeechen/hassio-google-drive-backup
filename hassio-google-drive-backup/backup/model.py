from .snapshots import AbstractSnapshot, Snapshot
from .config import Config
from .time import Time
from .logbase import LogBase

from datetime import datetime, timedelta
from typing import TypeVar, Generic, List, Dict, Optional, Tuple
from io import IOBase

T = TypeVar('T')


class CreateOptions(object):
    def __init__(self, when: datetime, name_template: str, retain_sources: Dict[str, bool]):
        self.when: datetime = when
        self.name_template: str = name_template
        self.retain_sources: Dict[str, bool] = retain_sources


class SnapshotSource(Generic[T]):
    def __init__(self):
        pass

    def name(self) -> str:
        return "Unnamed"

    def enabled(self) -> bool:
        return True

    def create(self, options: CreateOptions) -> T:
        pass

    def get(self) -> Dict[str, T]:
        pass

    def delete(self, snapshot: T):
        pass

    def save(self, snapshot: AbstractSnapshot, bytes: IOBase) -> T:
        pass

    def read(self, snapshot: T) -> IOBase:
        pass

    def retain(self, snapshot: T, retain: bool) -> None:
        pass


class Model(LogBase):
    def __init__(self, config: Config, time: Time, source: SnapshotSource[AbstractSnapshot], dest: SnapshotSource[AbstractSnapshot]):
        self.config: Config = config
        self.time = time
        self.source: SnapshotSource = source
        self.dest: SnapshotSource = dest
        self.reinitialize()
        self.snapshots: Dict[str, Snapshot] = {}
        self.firstSync = True

    def reinitialize(self):
        self._time_of_day: Optional[Tuple[int, int]] = self._parseTimeOfDay()
        self.generational_config = self.config.getGenerationalConfig()

    def _parseTimeOfDay(self) -> Optional[Tuple[int, int]]:
        if not self.config.snapshotTimeOfDay():
            return None
        parts = self.config.snapshotTimeOfDay().split(":")
        if len(parts) != 2:
            return None
        try:
            hour: int = int(parts[0])
            minute: int = int(parts[1])
            if hour < 0 or minute < 0 or hour > 23 or minute > 59:
                return None
            return (hour, minute)
        except ValueError:
            # Parse error
            return None

    def getTimeOfDay(self):
        return self._time_of_day

    def nextSnapshot(self, now: datetime, last_snapshot: Optional[datetime]) -> Optional[datetime]:
        if self.config.daysBetweenSnapshots() <= 0:
            return None
        if not last_snapshot:
            return now

        timeofDay = self.getTimeOfDay()
        if not timeofDay:
            return last_snapshot + timedelta(days=self.config.daysBetweenSnapshots())

        newest_local: datetime = self.time.toLocal(last_snapshot)
        time_that_day_local = datetime(newest_local.year, newest_local.month, newest_local.day, timeofDay[0], timeofDay[1], tzinfo=self.time.local_tz)
        if newest_local < time_that_day_local:
            # Latest snapshot is before the snapshot time for that day
            next = self.time.toUtc(time_that_day_local)
        else:
            # return the next snapshot after the delta
            next = self.time.toUtc(time_that_day_local + timedelta(days=self.config.daysBetweenSnapshots()))
        if next < now:
            return now
        else:
            return next

    def _syncSnapshots(self, now: datetime, sources: List[SnapshotSource]):
        for source in sources:
            if source.enabled:
                from_source: Dict[str, AbstractSnapshot] = source.get()
            else:
                from_source: Dict[str, AbstractSnapshot] = []
            for snapshot in from_source.values():
                if snapshot.slug() not in self.snapshots:
                    self.snapshots[snapshot.slug()] = Snapshot(snapshot)
                else:
                    self.snapshots[snapshot.slug()].add(snapshot)
            for snapshot in self.snapshots.values():
                if snapshot.slug() not in from_source:
                    snapshot.remove(source.name())
                    if snapshot.isDeleted():
                        del self.snapshots[snapshot.slug()]
        self.firstSync = False

    def sync(self, now: datetime):
        self._syncSnapshots(now, [self.source, self.dest])
