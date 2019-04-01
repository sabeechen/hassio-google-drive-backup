from datetime import datetime
from dateutil.tz import tzutc
from dateutil.tz import tzlocal
from dateutil.parser import parse
from time import sleep


class Time(object):
    def __init__(self, local_tz = tzlocal()):
        self.local_tz = local_tz

    def now(self) -> datetime:
        return datetime.now(tzutc())

    def nowLocal(self) -> datetime:
        return datetime.now(self.local_tz)

    def parse(self, text: str) -> datetime:
        return parse(text, tzinfos=tzutc)

    def toLocal(self, dt: datetime) -> datetime:
        return dt.astimezone(self.local_tz)

    def toUtc(self, dt: datetime) -> datetime:
        return dt.astimezone(tzutc())

    def sleep(self, seconds: float) -> None:
        sleep(seconds)