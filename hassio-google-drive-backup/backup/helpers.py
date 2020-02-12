from datetime import datetime
from dateutil.tz import tzutc

SIZE_SI = ["B", "kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]


def nowutc() -> datetime:
    return datetime.now(tzutc())


def touch(file):
    with open(file, "w"):
        pass


# TODO: Add tests for this method
def asSizeString(size):
    current = float(size)
    for id in SIZE_SI:
        if current < 1024:
            return "{0} {1}".format(round(current, 1), id)
        current /= 1024
    return "Beyond mortal comprehension"
