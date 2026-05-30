import asyncio
from datetime import datetime, timedelta
from .logger import getLogger
import pytz
import os
import time as base_time
from pytz import timezone, utc
from tzlocal import get_localzone_name, get_localzone
from dateutil.tz import tzlocal

from injector import inject, singleton
from dateutil.relativedelta import relativedelta
import collections
from dateutil.parser import parse


# this hack is for dateutil, it imports Callable from the wrong place
collections.Callable = collections.abc.Callable


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

    async def sleepAsync(self, seconds: float, early_exit: asyncio.Event | None = None) -> None:
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
        from .i18n import _
        if not now:
            now = self.now()

        if time < now:
            delta = relativedelta(now, time)
            past = True
        else:
            delta = relativedelta(time, now)
            past = False

        def fmt(n, singular, plural):
            return "{0} {1}".format(n, _(singular) if n == 1 else _(plural))

        if delta.years > 0:
            text = fmt(delta.years, "year", "years")
        elif delta.months != 0:
            months = delta.months + 1 if delta.days > 15 else delta.months
            text = fmt(months, "month", "months")
        elif delta.days != 0:
            days = delta.days + 1 if delta.hours >= 12 else delta.days
            text = fmt(days, "day", "days")
        elif delta.hours != 0:
            hours = delta.hours + 1 if delta.minutes >= 30 else delta.hours
            text = fmt(hours, "hour", "hours")
        elif delta.minutes != 0:
            minutes = delta.minutes + 1 if delta.minutes >= 30 else delta.minutes
            text = fmt(minutes, "minute", "minutes")
        elif delta.seconds != 0:
            text = fmt(delta.seconds, "second", "seconds")
        else:
            return _("right now")

        if past:
            return _("{0} ago").format(text)
        return text

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
