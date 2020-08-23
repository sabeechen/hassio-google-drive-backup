import asyncio
from datetime import datetime

from dateutil.tz import tzlocal, tzutc
from injector import inject, singleton
from dateutil.relativedelta import relativedelta
from dateutil.parser import parse
from .logger import getLogger

logger = getLogger(__name__)


@singleton
class Time(object):
    @inject
    def __init__(self, local_tz=tzlocal()):
        self.local_tz = local_tz

    def now(self) -> datetime:
        return datetime.now(tzutc())

    def nowLocal(self) -> datetime:
        return datetime.now(self.local_tz)

    @classmethod
    def parse(cls, text: str) -> datetime:
        ret = parse(text)
        if ret.tzinfo is None:
            ret = ret.replace(tzinfo=tzutc())
        return ret

    def toLocal(self, dt: datetime) -> datetime:
        return dt.astimezone(self.local_tz)

    def toUtc(self, dt: datetime) -> datetime:
        return dt.astimezone(tzutc())

    async def sleepAsync(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def local(self, year, month, day, hour=0, minute=0, second=0, ms=0):
        return datetime(year, month, day, hour, minute, second, ms, tzinfo=self.local_tz)

    def formatDelta(self, time: datetime, now=None) -> str:
        if not now:
            now = self.now()

        delta: relativedelta = None
        flavor = ""
        if time < now:
            delta = relativedelta(now, time)
            flavor = " ago"
        else:
            delta = relativedelta(time, now)
            flavor = ""
        if delta.years > 0:
            return "{0} years{1}".format(delta.years, flavor)
        if (delta.months != 0):
            if delta.days > 15:
                return "{0} months{1}".format(delta.months + 1, flavor)
            return "{0} months{1}".format(delta.months, flavor)
        if (delta.days != 0):
            if delta.hours >= 12:
                return "{0} days{1}".format(delta.days + 1, flavor)
            return "{0} days{1}".format(delta.days, flavor)
        if (delta.hours != 0):
            if delta.minutes >= 30:
                return "{0} hours{1}".format(delta.hours + 1, flavor)
            return "{0} hours{1}".format(delta.hours, flavor)
        if (delta.minutes != 0):
            if delta.minutes >= 30:
                return "{0} minutes{1}".format(delta.minutes + 1, flavor)
            return "{0} minutes{1}".format(delta.minutes, flavor)
        if (delta.seconds != 0):
            return "{0} seconds{1}".format(delta.seconds, flavor)
        return "right now"

    def asRfc3339String(self, time: datetime) -> str:
        if time is None:
            time = self.now()
        return time.strftime("%Y-%m-%dT%H:%M:%SZ")


class AcceleratedTime(Time):
    def __init__(self, dialation=1.0):
        super().__init__()
        self.start = datetime.now(tzutc())
        self.dialation = dialation

    def now(self):
        return self.start + relativedelta(seconds=(datetime.now(tzutc()) - self.start).total_seconds() * self.dialation)

    def nowLocal(self) -> datetime:
        return self.local(self.now())

    async def sleepAsync(self, seconds: float) -> None:
        await asyncio.sleep(seconds / self.dialation)


