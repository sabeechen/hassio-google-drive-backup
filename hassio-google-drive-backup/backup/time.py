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
            plural = "s" if delta.years > 1 else ""
            return "{0} year{2}{1}".format(delta.years, flavor, plural)
        if (delta.months != 0):
            plural = "s" if delta.months > 1 else ""
            if delta.days > 15:
                return "{0} month{2}{1}".format(delta.months + 1, flavor, plural)
            return "{0} month{2}{1}".format(delta.months, flavor, plural)
        if (delta.days != 0):
            plural = "s" if delta.days > 1 else ""
            if delta.hours >= 12:
                return "{0} day{2}{1}".format(delta.days + 1, flavor, plural)
            return "{0} day{2}{1}".format(delta.days, flavor, plural)
        if (delta.hours != 0):
            plural = "s" if delta.hours > 1 else ""
            if delta.minutes >= 30:
                return "{0} hour{2}{1}".format(delta.hours + 1, flavor, plural)
            return "{0} hour{2}{1}".format(delta.hours, flavor, plural)
        if (delta.minutes != 0):
            plural = "s" if delta.minutes > 1 else ""
            if delta.minutes >= 30:
                return "{0} minute{2}{1}".format(delta.minutes + 1, flavor, plural)
            return "{0} minute{2}{1}".format(delta.minutes, flavor, plural)
        if (delta.seconds != 0):
            plural = "s" if delta.seconds > 1 else ""
            return "{0} second{2}{1}".format(delta.seconds, flavor, plural)
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
