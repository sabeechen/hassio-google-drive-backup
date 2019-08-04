from ..helpers import parseDateTime
import datetime


def test_parse(mocker) -> None:
    time = parseDateTime("1985-12-06 01:01:01.0001")
    assert str(time) == "1985-12-06 01:01:01.000100+00:00"

    time = parseDateTime("1985-12-06 01:01:01.0001+01:00")
    assert str(time) == "1985-12-06 01:01:01.000100+01:00"


def test_parse_timezone(time) -> None:
    assertUtc(parseDateTime("1985-12-06"))
    assertUtc(parseDateTime("1985-12-06 21:21"))
    assertUtc(parseDateTime("1985-12-06 21:21+00:00"))
    assertUtc(parseDateTime("1985-12-06 21:21 UTC"))
    assertUtc(parseDateTime("1985-12-06 21:21 GGGR"))

    assertOffset(parseDateTime("1985-12-06 21:21+10"), 10)
    assertOffset(parseDateTime("1985-12-06 21:21-10"), -10)


def assertOffset(time, hours):
    assert time.tzinfo.utcoffset(time) == datetime.timedelta(hours=hours)


def assertUtc(time):
    assertOffset(time, 0)
