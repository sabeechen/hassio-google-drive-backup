from datetime import datetime, timedelta
from dateutil.tz import tzutc
from dateutil.tz import tzlocal
from .helpers import parseDateTime
from time import sleep


class Time(object):
    def __init__(self, local_tz=tzlocal()):
        self.local_tz = local_tz

    def now(self) -> datetime:
        return datetime.now(tzutc())

    def nowLocal(self) -> datetime:
        return datetime.now(self.local_tz)

    def parse(self, text: str) -> datetime:
        return parseDateTime(text)

    def toLocal(self, dt: datetime) -> datetime:
        return dt.astimezone(self.local_tz)

    def toUtc(self, dt: datetime) -> datetime:
        return dt.astimezone(tzutc())

    def sleep(self, seconds: float) -> None:
        sleep(seconds)

    def local(self, year, month, day, hour=0, minute=0, second=0, ms=0):
        return datetime(year, month, day, hour, minute, second, ms, tzinfo=self.local_tz)


class FakeTime(Time):
    def __init__(self, now: datetime = None):
        super().__init__()
        if now:
            self._now = now
        else:
            self._now = self.toUtc(datetime(1985, 12, 6, 0, 0, 0))
        self.sleeps = []

    def setNow(self, now: datetime):
        self._now = now
        return self

    def advanceDay(self, days=1):
        return self.advance(days=1)

    def advance(self, days=0, hours=0, seconds=0):
        self._now = self._now + timedelta(days=days, hours=hours, seconds=seconds)
        return self

    def now(self) -> datetime:
        return self._now

    def nowLocal(self) -> datetime:
        return self.toLocal(self._now)

    def sleep(self, seconds: int):
        self.sleeps.append(seconds)
        self._now = self._now + timedelta(seconds=seconds)
