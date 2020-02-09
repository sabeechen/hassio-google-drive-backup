from datetime import datetime
from traceback import TracebackException
from typing import Callable, Dict, Generator, Sequence, TypeVar

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from dateutil.tz import tzutc

"""
Some helper functions because I find python's API's intolerable
"""
T = TypeVar('T')
V = TypeVar('V')


def strToBool(value) -> bool:
    return str(value).lower() in ['true', 't', 'on', 'yes', 'y', '1', 'hai', 'si', 'omgyesplease']


def parseDateTime(text: str) -> datetime:
    ret = parse(text)
    if ret.tzinfo is None:
        ret = ret.replace(tzinfo=tzutc())
    return ret


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


def formatTimeSince(time: datetime, now=None) -> str:
    if not now:
        now = now

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


def formatException(e: Exception) -> str:
    trace = None
    if (hasattr(e, "__traceback__")):
        trace = e.__traceback__
    tbe = TracebackException(type(e), e, trace, limit=None)
    lines = list(_format(tbe))
    return'\n%s' % ''.join(lines)


def _format(tbe):
    if (tbe.__context__ is not None and not tbe.__suppress_context__):
        yield from _format(tbe.__context__)
        yield "Whose handling caused:\n"
    is_addon, stack = _formatStack(tbe)
    yield from stack
    yield from tbe.format_exception_only()


def _formatStack(tbe):
    _RECURSIVE_CUTOFF = 3
    result = []
    last_file = None
    last_line = None
    last_name = None
    count = 0
    is_addon = False
    buffer = []
    for frame in tbe.stack:
        line_internal = True
        if (last_file is None or last_file != frame.filename or last_line is None or last_line != frame.lineno or last_name is None or last_name != frame.name):
            if count > _RECURSIVE_CUTOFF:
                count -= _RECURSIVE_CUTOFF
                result.append(
                    f'  [Previous line repeated {count} more '
                    f'time{"s" if count > 1 else ""}]\n'
                )
            last_file = frame.filename
            last_line = frame.lineno
            last_name = frame.name
            count = 0
        count += 1
        if count > _RECURSIVE_CUTOFF:
            continue
        fileName = frame.filename
        pos = fileName.rfind("hassio-google-drive-backup/backup")
        if pos > 0:
            is_addon = True
            line_internal = False
            fileName = "/addon" + \
                fileName[pos + len("hassio-google-drive-backup/backup"):]

        pos = fileName.rfind("site-packages")
        if pos > 0:
            fileName = fileName[pos - 1:]

        pos = fileName.rfind("python3.7")
        if pos > 0:
            fileName = fileName[pos - 1:]
            pass
        line = '  {}:{} ({})\n'.format(fileName, frame.lineno, frame.name)
        if line_internal:
            buffer.append(line)
        else:
            result.extend(_compressFrames(buffer))
            buffer = []
            result.append(line)
    if count > _RECURSIVE_CUTOFF:
        count -= _RECURSIVE_CUTOFF
        result.append(
            f'  [Previous line repeated {count} more '
            f'time{"s" if count > 1 else ""}]\n'
        )
    result.extend(_compressFrames(buffer))
    return is_addon, result


def _compressFrames(buffer):
    if len(buffer) > 1:
        yield buffer[0]
        if len(buffer) == 3:
            yield buffer[1]
        elif len(buffer) > 2:
            yield "  [{} hidden frames]\n".format(len(buffer) - 2)
        yield buffer[len(buffer) - 1]
    elif len(buffer) > 0:
        yield buffer[len(buffer) - 1]
        pass


def touch(file):
    with open(file, "w"):
        pass


def asSizeString(size):
    size_bytes = float(size)
    if size_bytes <= 1024.0:
        return str(int(size_bytes)) + " B"
    if size_bytes <= 1024.0 * 1024.0:
        return str(int(size_bytes / 1024.0)) + " kB"
    if size_bytes <= 1024.0 * 1024.0 * 1024.0:
        return str(int(size_bytes / (1024.0 * 1024.0))) + " MB"
    if size_bytes <= 1024.0 * 1024.0 * 1024.0 * 1024:
        return str(int(size_bytes / ((1024.0 * 1024.0 * 1024.0) / 10)) / 10) + " GB"
    if size_bytes <= 1024.0 * 1024.0 * 1024.0 * 1024 * 1024:
        return str(int(size_bytes / ((1024.0 * 1024.0 * 1024.0 * 1024.0) / 10)) / 10) + " TB"
    if size_bytes <= 1024.0 * 1024.0 * 1024.0 * 1024 * 1024 * 1024:
        return str(int(size_bytes / ((1024.0 * 1024.0 * 1024.0 * 1024.0 * 1024.0) / 10)) / 10) + " PB"
    if size_bytes <= 1024.0 * 1024.0 * 1024.0 * 1024 * 1024 * 1024 * 1024:
        return str(int(size_bytes / ((1024.0 * 1024.0 * 1024.0 * 1024.0 * 1024.0 * 1024.0) / 10)) / 10) + " EB"
    if size_bytes <= 1024.0 * 1024.0 * 1024.0 * 1024 * 1024 * 1024 * 1024 * 1024:
        return str(int(size_bytes / ((1024.0 * 1024.0 * 1024.0 * 1024.0 * 1024.0 * 1024.0 * 1024.0) / 10)) / 10) + " ZB"
    if size_bytes <= 1024.0 * 1024.0 * 1024.0 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024:
        return str(int(size_bytes / ((1024.0 * 1024.0 * 1024.0 * 1024.0 * 1024.0 * 1024.0 * 1024.0 * 1024.0) / 10)) / 10) + " YB"
    return "A lot"
