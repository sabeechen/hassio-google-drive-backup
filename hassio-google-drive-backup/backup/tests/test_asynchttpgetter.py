import pytest
from aiohttp import ClientSession


@pytest.mark.asyncio
async def test_basics(uploader, server, session: ClientSession):
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
