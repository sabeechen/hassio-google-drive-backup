import traceback

from dateutil.tz import tzutc
from dateutil.parser import parse
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Generator, Sequence, TypeVar, Callable, Dict
"""
Some helper functions because I find python's API's intolerable
"""
T = TypeVar('T')
V = TypeVar('V')

def parseDateTime(text: str) -> datetime:
    return parse(text, tzinfos=tzutc)


def nowutc() -> datetime:
    return datetime.now(tzutc())


def makeDict(iterable: Sequence[T], func: Callable[[T], V]) -> Dict[V, T]:
    ret: Dict[V, T] = {}
    for item in iterable:
        ret[func(item)] = item
    return ret


def count(iterable: Sequence[T], func: Callable[[T], bool]) -> int:
    ret = 0
    for item in iterable:
        if func(item):
            ret = ret + 1
    return ret


def take(iterable: Sequence[T], count: int) -> Generator[T, None, None]:
    sent: int = 0
    for item in iterable:
        if sent < count:
            sent = sent + 1
            yield item
        else:
            break


def formatTimeSince(time: datetime) -> str:
    delta = relativedelta(nowutc(), time)
    if (delta.months != 0):
        return "{} months ago".format(delta.months)
    if (delta.days != 0):
        return "{} days ago".format(delta.days)
    if (delta.hours != 0):
        return "{} hours ago".format(delta.hours)
    if (delta.minutes != 0):
        return "{} minutes ago".format(delta.minutes)
    if (delta.seconds != 0):
        return "{} seconds ago".format(delta.seconds)
    return "just now"


def formatException(e: Exception) -> str:
    trace = None
    if (hasattr(e, "__traceback__")):
        trace = e.__traceback__
    exc = traceback.format_exception(type(e), e, trace, chain=False)
    return'\n%s\n' % ''.join(exc)
