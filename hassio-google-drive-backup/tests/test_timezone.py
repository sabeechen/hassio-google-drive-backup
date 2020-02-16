import datetime

from backup.time import Time


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
