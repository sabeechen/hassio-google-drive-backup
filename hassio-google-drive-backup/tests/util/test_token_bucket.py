from backup.util import TokenBucket
from ..faketime import FakeTime


async def test_consume(time: FakeTime):
    bucket = TokenBucket(time, 10, 1, 1)
    assert bucket.consume(1)
    assert not bucket.consume(1)

    time.advance(seconds=1)
    assert bucket.consume(1)
    assert not bucket.consume(1)


async def test_async_consume(time: FakeTime):
    bucket = TokenBucket(time, 10, 1, 1)
    assert await bucket.consumeWithWait(1, 2) == 1
    assert len(time.sleeps) == 0

    time.advance(seconds=2)
    assert await bucket.consumeWithWait(1, 2) == 2
    assert len(time.sleeps) == 0

    assert await bucket.consumeWithWait(1, 2) == 1
    assert len(time.sleeps) == 1
    assert time.sleeps[0] == 1


async def test_capacity(time: FakeTime):
    bucket = TokenBucket(time, 10, 1)
    assert await bucket.consumeWithWait(1, 10) == 10
    assert len(time.sleeps) == 0

    assert await bucket.consumeWithWait(5, 10) == 5
    assert len(time.sleeps) == 1
    assert time.sleeps[0] == 5

    time.clearSleeps()
    assert await bucket.consumeWithWait(20, 20) == 20
    assert len(time.sleeps) == 1
    assert time.sleeps[0] == 20

    time.clearSleeps()
    time.advance(seconds=5)
    assert await bucket.consumeWithWait(1, 10) == 5


async def test_higher_fill_rate(time: FakeTime):
    bucket = TokenBucket(time, capacity=1000, fill_rate=100)
    assert await bucket.consumeWithWait(1, 1000) == 1000
    assert len(time.sleeps) == 0
