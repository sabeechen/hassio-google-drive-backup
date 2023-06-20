import datetime
import os
from backup.time import Time, _infer_timezone_from_env, _infer_timezone_from_name, _infer_timezone_from_offset, _infer_timezone_from_system
from .faketime import FakeTime


def test_parse() -> None:
    time = Time.parse("1985-12-06 01:01:01.0001")
    assert str(time) == "1985-12-06 01:01:01.000100+00:00"

    time = Time.parse("1985-12-06 01:01:01.0001+01:00")
    assert str(time) == "1985-12-06 01:01:01.000100+01:00"


def test_parse_timezone(time) -> None:
    assertUtc(Time.parse("1985-12-06"))
    assertUtc(Time.parse("1985-12-06 21:21"))
    assertUtc(Time.parse("1985-12-06 21:21+00:00"))
    assertUtc(Time.parse("1985-12-06 21:21 UTC"))
    assertUtc(Time.parse("1985-12-06 21:21 GGGR"))

    assertOffset(Time.parse("1985-12-06 21:21+10"), 10)
    assertOffset(Time.parse("1985-12-06 21:21-10"), -10)


def assertOffset(time, hours):
    assert time.tzinfo.utcoffset(time) == datetime.timedelta(hours=hours)


def assertUtc(time):
    assertOffset(time, 0)


def test_common_timezones(time: FakeTime):
    assert _infer_timezone_from_system() is not None
    assert _infer_timezone_from_name() is not None
    assert _infer_timezone_from_offset() is not None
    assert _infer_timezone_from_env() is None

    os.environ["TZ"] = "America/Denver"
    assert _infer_timezone_from_env().tzname(None) == "America/Denver"

    os.environ["TZ"] = "Australia/Brisbane"
    assert _infer_timezone_from_env().tzname(None) == "Australia/Brisbane"

    tzs = {"SYSTEM": _infer_timezone_from_system(),
           "ENV": _infer_timezone_from_env(),
           "OFFSET": _infer_timezone_from_offset(),
           "NAME": _infer_timezone_from_name()}

    for name, tz in tzs.items():
        print(name)
        time.setTimeZone(tz)
        time.now()
        time.nowLocal()
        time.localize(datetime.datetime(1985, 12, 6))
        time.local(1985, 12, 6)
        time.toLocal(time.now())
        time.toUtc(time.nowLocal())


def test_system_timezone(time: FakeTime):
    tz = _infer_timezone_from_system()
    assert tz.tzname(time.now()) == "UTC"
