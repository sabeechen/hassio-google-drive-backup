from io import IOBase
from io import SEEK_SET, SEEK_END, SEEK_CUR
from .logbase import LogBase
from .exceptions import LogicError, ProtocolError, ensureKey
from typing import Dict


class WrappedException(Exception):
    """
    A weird error exists in httplib2 where if the underlying stream returns certain exception types, it produces
    an index out of bounds error while handling it and just eats the error.  This wraps the error in an exception of
    a different type so so we can actually surface it.  Hacky, yes, but it works.
    """
    def __init__(self, innerException):
        self.innerException = innerException


class SeekableRequest(IOBase, LogBase):
    def __init__(self, url, headers: Dict[str, str], size, session, chunk_size=1024 * 1024 * 10):
        self.url: str = url
        self.offset: int = 0
        self._size: int = size
        self.headers: Dict[str, str] = headers
        self.buffer: bytearray = bytearray()
        self.bufferStart = 0
        self.chunk_size = chunk_size
        self.session = session

    async def prepare(self):
        await self.size()
        return self

    async def size(self) -> int:
        if self._size < 0:
            self._size = await self._getContentLength()
        return self._size

    async def _readFromServer(self, count=-1) -> bytearray:
        if count == 0:
            return bytearray()
        if count < 0:
            count = await self.size() - self.offset

        end = self.offset + count - 1
        return await self._getByteRange(self.offset, end)

    async def read(self, count=1):
        ret = await self._read(count)
        if len(ret) == 0:
            return bytes(ret)
        while(len(ret) < count):
            needed = count - len(ret)
            additional = await self._read(needed)
            if len(additional) == 0:
                return bytes(ret)
            else:
                ret.extend(additional)
        return bytes(ret)

    async def _read(self, count):
        if self.offset + count >= await self.size():
            count = await self.size() - self.offset
        if count == 0 or self.offset >= await self.size():
            return bytearray()

        if self.bufferStart + count < len(self.buffer):
            # read from the internal buffer
            end = self.bufferStart + count
            data = bytearray(self.buffer[self.bufferStart:end])
            self.offset = self.offset + count
            self.bufferStart = self.bufferStart + count
            return data
        else:
            # buffer isn't big enough, so read from the server
            data = bytearray(self.buffer[self.bufferStart:])

            self.offset += len(data)
            left = await self.size() - self.offset
            self.buffer = await self._readFromServer(min(self.chunk_size, left))
            self.bufferStart = 0

            needed = count - len(data)
            if needed > 0:
                take = min(needed, len(self.buffer))
                data.extend(self.buffer[:take])
                self.offset += take
                self.bufferStart += take
            return data

    def seek(self, offset, whence=0):
        if whence == SEEK_SET:
            if(self.offset == offset):
                # good god this drive library is terrible.  Who seeks to current position?
                return
            self.offset = offset
        elif whence == SEEK_CUR:
            self.offset += offset
        elif whence == SEEK_END:
            self.offset = self.size() + offset
        else:
            raise LogicError("Invalid whence")
        self.buffer = bytearray()
        self.bufferStart = 0

    def tell(self):
        return self.offset

    async def progress(self):
        return 100 * float(self.tell()) / float(await self.size())

    async def __format__(self, format_spec: str) -> str:
        return str(int(await self.progress()))

    async def _getContentLength(self):
        async with self.session.get(self.url, headers=self.headers) as resp:
            return int(ensureKey('Content-length', resp.headers, "web server get request's headers"))

    async def _getByteRange(self, start, end):
        headers = self.headers.copy()
        headers['range'] = "bytes=%s-%s" % (self.offset, end)
        async with self.session.get(self.url, headers=headers) as resp:
            data = await resp.read()
            if len(data) != (end - start + 1):
                raise ProtocolError("Asked for range [{1}, {2}] at url {0}, but got back data length={3}".format(self.url, start, end, len(data)))
            return data
