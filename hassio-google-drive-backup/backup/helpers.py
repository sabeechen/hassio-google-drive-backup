import traceback
import socket
import subprocess

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


def strToBool(value) -> bool:
    return str(value).lower() in ['true', 't', 'on', 'yes', 'y', '1', 'hai', 'si', 'omgyesplease']


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
    exc = traceback.format_exception(type(e), e, trace, chain=False)
    return'\n%s\n' % ''.join(exc)


def resolveHostname(host: str):
    try:
        ret = []
        for info in socket.getaddrinfo(host, 443, 0, 0, socket.IPPROTO_TCP):
            ret.append(info[4][0])
        return ret
    except Exception:
        return []


def getPingInfo(servers):
    pings = {}
    for server in servers:
        pings[server] = {
            server: 'Unknown'
        }
    ips = servers.copy()
    for address in pings.keys():
        for ip in resolveHostname(address):
            pings[address][ip] = "Unknown"
            if ip not in ips:
                ips.append(ip)
    command = "fping -t 1000 " + " ".join(ips)

    # fping each server
    output = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, encoding="utf-8")

    for line in output.stdout.split("\n"):
        for host in pings.keys():
            for address in pings[host].keys():
                if line.startswith(address):
                    response = line[len(address):].strip()
                    if response.startswith(":"):
                        response = response[2:].strip()
                    if response.startswith("is"):
                        response = response[3:].strip()
                    pings[host][address] = response
    return pings


def touch(file):
    with open(file, "w"):
        pass
