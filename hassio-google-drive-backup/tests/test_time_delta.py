from backup.time import Time
from .faketime import FakeTime


def test_format_delta_plural() -> None:
    assert Time().formatDelta(FakeTime().advance(days=800).now(), FakeTime().now()) == "2 years"
    assert Time().formatDelta(FakeTime().advance(days=366).now(), FakeTime().now()) == "1 year"
    assert Time().formatDelta(FakeTime().advance(days=50).now(), FakeTime().now()) == "2 months"
    assert Time().formatDelta(FakeTime().advance(days=40).now(), FakeTime().now()) == "1 month"
    assert Time().formatDelta(FakeTime().advance(days=1, hours=17).now(), FakeTime().now()) == "2 days"
    assert Time().formatDelta(FakeTime().advance(days=1, hours=4).now(), FakeTime().now()) == "1 day"
    assert Time().formatDelta(FakeTime().advance(hours=1, minutes=38).now(), FakeTime().now()) == "2 hours"
    assert Time().formatDelta(FakeTime().advance(minutes=1, seconds=35).now(), FakeTime().now()) == "2 minutes"
    assert Time().formatDelta(FakeTime().advance(seconds=35).now(), FakeTime().now()) == "35 seconds"
