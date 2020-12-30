from backup.config.durationparser import DurationParser
from datetime import timedelta


def test_parse_days():
    parser = DurationParser()
    assert parser.parse("1 days") == timedelta(days=1)
    assert parser.parse("5 days") == timedelta(days=5)
    assert parser.parse("5 d") == timedelta(days=5)
    assert parser.parse("5d") == timedelta(days=5)
    assert parser.parse("5.0d") == timedelta(days=5)
    assert parser.parse("5.0day") == timedelta(days=5)
    assert parser.parse("5.0 day") == timedelta(days=5)
    assert parser.parse("5.5 days") == timedelta(days=5, hours=12)


def test_parse_hours():
    parser = DurationParser()
    assert parser.parse("1 hours") == timedelta(hours=1)
    assert parser.parse("5 hours") == timedelta(hours=5)
    assert parser.parse("5 h") == timedelta(hours=5)
    assert parser.parse("5hour") == timedelta(hours=5)
    assert parser.parse("5.0h") == timedelta(hours=5)
    assert parser.parse("5.0 hour") == timedelta(hours=5)
    assert parser.parse("5.5 h") == timedelta(hours=5, minutes=30)


def test_parse_minutes():
    parser = DurationParser()
    assert parser.parse("1 minutes") == timedelta(minutes=1)
    assert parser.parse("5 min") == timedelta(minutes=5)
    assert parser.parse("5 m") == timedelta(minutes=5)
    assert parser.parse("5mins") == timedelta(minutes=5)
    assert parser.parse("5.0m") == timedelta(minutes=5)
    assert parser.parse("5.0 min") == timedelta(minutes=5)
    assert parser.parse("5.5 m") == timedelta(minutes=5, seconds=30)


def test_parse_seconds():
    parser = DurationParser()
    assert parser.parse("1 seconds") == timedelta(seconds=1)
    assert parser.parse("5 sec") == timedelta(seconds=5)
    assert parser.parse("5 s") == timedelta(seconds=5)
    assert parser.parse("5secs") == timedelta(seconds=5)
    assert parser.parse("5.0s") == timedelta(seconds=5)
    assert parser.parse("5.0 secs") == timedelta(seconds=5)
    assert parser.parse("5.5 s") == timedelta(seconds=5, milliseconds=500)


def test_parse_multiple():
    parser = DurationParser()
    assert parser.parse("1 day, 5 hours, 30 seconds") == timedelta(days=1, hours=5, seconds=30)
    assert parser.parse("1 day 5 hours 30 seconds") == timedelta(days=1, hours=5, seconds=30)
    assert parser.parse("1d 5 hours 30s") == timedelta(days=1, hours=5, seconds=30)
    assert parser.parse("1d 5h 30s") == timedelta(days=1, hours=5, seconds=30)
    assert parser.parse("5m 1d 5h 30s") == timedelta(days=1, hours=5, minutes=5, seconds=30)


def test_format():
    parser = DurationParser()
    assert parser.format(timedelta(days=1)) == "1 days"
    assert parser.format(timedelta(seconds=86400)) == "1 days"
    assert parser.format(timedelta(hours=1)) == "1 hours"
    assert parser.format(timedelta(minutes=1)) == "1 minutes"
    assert parser.format(timedelta(seconds=60)) == "1 minutes"
    assert parser.format(timedelta(seconds=5)) == "5 seconds"
    assert parser.format(timedelta(seconds=1)) == "1 seconds"
    assert parser.format(timedelta(days=5, hours=6, minutes=7)) == "5 days, 6 hours, 7 minutes"
    assert parser.format(timedelta(days=5, hours=6, minutes=7, seconds=8)) == "5 days, 6 hours, 7 minutes, 8 seconds"


def test_back_and_forth():
    doTestConvert(timedelta(hours=5))
    doTestConvert(timedelta(minutes=600))
    doTestConvert(timedelta(days=30))
    doTestConvert(timedelta(days=5, minutes=6, hours=10, seconds=20))


def doTestConvert(duration):
    parser = DurationParser()
    assert parser.parse(parser.format(duration)) == duration


def test_convert_empty_seconds():
    parser = DurationParser()
    assert parser.parse("") == timedelta(seconds=0)
    assert parser.parse("0") == timedelta(seconds=0)
    assert parser.parse("30") == timedelta(seconds=30)
    assert parser.parse(str(60 * 60)) == timedelta(seconds=60 * 60)
