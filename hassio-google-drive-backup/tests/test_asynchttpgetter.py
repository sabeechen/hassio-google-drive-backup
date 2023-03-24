from datetime import timedelta
import pytest
from aiohttp import ClientSession
from aiohttp.web import StreamResponse
from .conftest import Uploader
from backup.exceptions import LogicError
from dev.request_interceptor import RequestInterceptor
from .conftest import FakeTime


@pytest.mark.asyncio
async def test_basics(uploader: Uploader, server, session: ClientSession):
    getter = await uploader.upload(bytearray([0, 1, 2, 3, 4, 5, 6, 7]))
    await getter.setup()
    assert (await getter.read(1)).read() == bytearray([0])
    assert (await getter.read(2)).read() == bytearray([1, 2])
    assert (await getter.read(3)).read() == bytearray([3, 4, 5])
    assert (await getter.read(3)).read() == bytearray([6, 7])
    assert (await getter.read(3)).read() == bytearray([])
    assert (await getter.read(3)).read() == bytearray([])

    getter.position(2)
    assert (await getter.read(2)).read() == bytearray([2, 3])
    assert (await getter.read(3)).read() == bytearray([4, 5, 6])

    getter.position(2)
    assert (await getter.read(2)).read() == bytearray([2, 3])

    getter.position(2)
    assert (await getter.read(2)).read() == bytearray([2, 3])
    assert (await getter.read(100)).read() == bytearray([4, 5, 6, 7])
    assert (await getter.read(3)).read() == bytearray([])
    assert (await getter.read(3)).read() == bytearray([])

@pytest.mark.asyncio
async def test_position_error(uploader: Uploader, server):
    getter = await uploader.upload(bytearray([0, 1, 2, 3, 4, 5, 6, 7]))
    await getter.setup()
    assert (await getter.read(1)).read() == bytearray([0])

    with pytest.raises(LogicError):
        await getter.setup()


@pytest.mark.asyncio
async def test_no_content_length(uploader: Uploader, server, interceptor: RequestInterceptor):
    getter = await uploader.upload(bytearray([0, 1, 2, 3, 4, 5, 6, 7]))
    intercept = interceptor.setError("/readfile")
    intercept.addResponse(StreamResponse(headers={}))
    with pytest.raises(LogicError) as e:
        await getter.setup()
    assert e.value.message() == "Content size must be provided if the webserver doesn't provide it"


@pytest.mark.asyncio
async def test_no_setup_error(uploader: Uploader, server):
    getter = await uploader.upload(bytearray([0, 1, 2, 3, 4, 5, 6, 7]))
    with pytest.raises(LogicError):
        await getter.read(1)


@pytest.mark.asyncio
async def test_progress(uploader: Uploader, server):
    getter = await uploader.upload(bytearray([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]))
    await getter.setup()
    assert getter.progress() == 0
    assert (await getter.read(1)).read() == bytearray([0])
    assert getter.progress() == 10
    assert (await getter.read(2)).read() == bytearray([1, 2])
    assert getter.progress() == 30
    assert (await getter.read(7)).read() == bytearray([3, 4, 5, 6, 7, 8, 9])
    assert getter.progress() == 100
    assert str.format("{0}", getter) == "100"


@pytest.mark.asyncio
async def test_speed(uploader: Uploader, server, time: FakeTime):
    getter = await uploader.upload(bytearray(x for x in range(0, 100)))
    assert getter.startTime() == time.now()
    await getter.setup()
    assert getter.speed(period=timedelta(seconds=10)) is None
    time.advance(seconds=1)
    await getter.read(1)
    assert getter.speed(period=timedelta(seconds=10)) == 1

    time.advance(seconds=1)
    await getter.read(1)
    assert getter.speed(period=timedelta(seconds=10)) == 1
    assert getter.speed(period=timedelta(seconds=1)) == 1
    assert getter.speed(period=timedelta(seconds=1.5)) == 1
    assert getter.speed(period=timedelta(seconds=0.5)) == 1

    time.advance(seconds=1)
    assert getter.speed(period=timedelta(seconds=10)) == 1
    assert getter.speed(period=timedelta(seconds=1)) == 1
    assert getter.speed(period=timedelta(seconds=1.5)) == 1
    time.advance(seconds=0.5)
    assert getter.speed(period=timedelta(seconds=1)) == 0.5
    time.advance(seconds=0.5)
    assert getter.speed(period=timedelta(seconds=1)) == 0

    # Now 4 seconds have passed, and we've transferred 4 bytes
    await getter.read(2)
    assert getter.speed(period=timedelta(seconds=4)) == 1
    assert getter.speed(period=timedelta(seconds=10)) == 1

    time.advance(seconds=10)
    await getter.read(10)
    assert getter.speed(period=timedelta(seconds=10)) == 1

    time.advance(seconds=10)
    await getter.read(20)
    assert getter.speed(period=timedelta(seconds=10)) == 2
    time.advance(seconds=10)
    assert getter.speed(period=timedelta(seconds=10)) == 2
    time.advance(seconds=5)
    assert getter.speed(period=timedelta(seconds=10)) == 1
