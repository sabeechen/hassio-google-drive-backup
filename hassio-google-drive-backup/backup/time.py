import asyncio
from datetime import datetime, timedelta


from injector import inject, singleton
from dateutil.relativedelta import relativedelta
from dateutil.parser import parse
from .logger import getLogger
import pytz
import os
import time as base_time
from pytz import timezone, utc
from tzlocal import get_localzone_name, get_localzone
from dateutil.tz import tzlocal


logger = getLogger(__name__)


def get_local_tz():
    methods = [
        _infer_timezone_from_env,
        _infer_timezone_from_name,
        _infer_timezone_from_system,
        _infer_timezone_from_offset
    ]
    for method in methods:
        try:
            tz = method()
            if tz is not None:
                return tz
        except Exception:
            pass
    return utc


def _infer_timezone_from_offset():
    now = datetime.now()
    desired_offset = tzlocal().utcoffset(now)
    for tz_name in pytz.all_timezones:
        tz = pytz.timezone(tz_name)
        if desired_offset == tz.utcoffset(now):
            return tz
    return None


def _infer_timezone_from_name():
    name = get_localzone_name()
    if name is not None:
        return timezone(name)
    return None


def _infer_timezone_from_system():
    tz = get_localzone()
    if tz is None:
        return None
    return timezone(tz.tzname(datetime.now()))


def _infer_timezone_from_env():
    if "TZ" in os.environ:
        tz = timezone(os.environ["TZ"])
        if tz is not None:
            return tz
    return None


@singleton
class Time(object):
    @inject
    def __init__(self, local_tz=get_local_tz()):
        self.local_tz = local_tz
        self._offset = timedelta(seconds=0)

    def now(self) -> datetime:
        return datetime.now(pytz.utc) + self._offset

    def nowLocal(self) -> datetime:
        return datetime.now(self.local_tz) + self._offset

    @property
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, delta: timedelta):
        self._offset = delta

    @classmethod
    def parse(cls, text: str) -> datetime:
        ret = parse(text)
        if ret.tzinfo is None:
            ret = ret.replace(tzinfo=utc)
        return ret

    def monotonic(self):
        return base_time.monotonic()

    def toLocal(self, dt: datetime) -> datetime:
        return dt.astimezone(self.local_tz)

    def localize(self, dt: datetime) -> datetime:
        return self.local_tz.localize(dt)

    def toUtc(self, dt: datetime) -> datetime:
        return dt.astimezone(utc)

    async def sleepAsync(self, seconds: float, early_exit: asyncio.Event = None) -> None:
        if early_exit is None:
            await asyncio.sleep(seconds)
        else:
            try:
                await asyncio.wait_for(early_exit.wait(), seconds)
            except asyncio.TimeoutError:
                pass

    def local(self, year, month, day, hour=0, minute=0, second=0, ms=0):
        return self.local_tz.localize(datetime(year, month, day, hour, minute, second, ms))

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
        self.start = datetime.now(utc)
        self.dialation = dialation

    def now(self):
        return self.start + timedelta(seconds=(datetime.now(utc) - self.start).total_seconds() * self.dialation)

    def nowLocal(self) -> datetime:
        return self.localize(self.now())

    async def sleepAsync(self, seconds: float) -> None:
        await asyncio.sleep(seconds / self.dialation)
