import asyncio
from datetime import datetime, timedelta
from backup.time import Time
from pytz import timezone


class FakeTime(Time):
    def __init__(self, now: datetime = None):
        super().__init__(local_tz=timezone('EST'))
        if now:
            self._now = now
        else:
            self._now = self.toUtc(
                datetime(1985, 12, 6, 0, 0, 0, tzinfo=timezone('EST')))
        self.sleeps = []

    def setTimeZone(self, tz):
        if isinstance(tz, str):
            self.local_tz = timezone(tz)
        else:
            self.local_tz = tz

    def setNow(self, now: datetime):
        self._now = now
        return self

    def advanceDay(self, days=1):
        return self.advance(days=1)

    def advance(self, days=0, hours=0, minutes=0, seconds=0, duration=None):
        self._now = self._now + \
            timedelta(days=days, hours=hours, seconds=seconds, minutes=minutes)
        if duration is not None:
            self._now = self._now + duration
        return self

    def now(self) -> datetime:
        return self._now

    def nowLocal(self) -> datetime:
        return self.toLocal(self._now)

    async def sleepAsync(self, seconds: float, _exit_early: asyncio.Event = None):
        self.sleeps.append(seconds)
        self._now = self._now + timedelta(seconds=seconds)
        # allow the task to be interrupted if such a thing is requested.
        await asyncio.sleep(0)

    def clearSleeps(self):
        self.sleeps = []
