import dateutil
import datetime
import traceback

from dateutil.tz import tzutc
from dateutil.parser import parse
from datetime import datetime
from dateutil.relativedelta import relativedelta

"""
Some helper functions because I find python's API's intolerable
"""
def parseDateTime(text) :
    return parse(text, tzinfos=tzutc)

def nowutc():
    return datetime.now(tzutc())

def makeDict(iterable, func):
    ret = {}
    for item in iterable:
        ret[func(item)] = item
    return ret

def count(iterable, func):
    ret = 0
    for item in iterable:
        if func(item):
            ret = ret + 1
    return ret

def take(iterable, count):
    sent = 0
    for item in iterable:
        if sent < count:
            sent = sent + 1
            yield item
        else:
            break


def formatTimeSince(time):
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

def formatException(e):
	trace = None
	if (hasattr(e, "__traceback__")):
		trace = e.__traceback__
	exc = traceback.format_exception(type(e), e, trace, chain=False)
	return'\n%s\n' % ''.join(exc)
