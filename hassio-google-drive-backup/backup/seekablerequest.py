from io import IOBase
from io import SEEK_SET, SEEK_END, SEEK_CUR
from urllib.request import urlopen
from urllib.request import Request
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
    def __init__(self, url, headers: Dict[str, str], size: int = -1, chunk_size=1024 * 1024 * 10):
        self.url: str = url
        self.offset: int = 0
        self._size: int = size
        self.headers: Dict[str, str] = headers
        self.buffer: bytearray = bytearray()
        self.bufferStart = 0
        self.chunk_size = chunk_size

    def prepare(self):
        self.size()
        return self

    def size(self) -> int:
        if self._size < 0:
            self._size = self._getContentLength()
        return self._size

    def _readFromServer(self, count=-1) -> bytearray:
        if count == 0:
            return bytearray()
        if count < 0:
            count = self.size() - self.offset

        end = self.offset + count - 1
        return self._getByteRange(self.offset, end)

    def read(self, count=1):
        ret = self._read(count)
        if len(ret) == 0:
            return bytes(ret)
        while(len(ret) < count):
            needed = count - len(ret)
            additional = self._read(needed)
            if len(additional) == 0:
                return bytes(ret)
            else:
                ret.extend(additional)
        return bytes(ret)

    def _read(self, count):
        if self.offset + count >= self.size():
            count = self.size() - self.offset
        if count == 0 or self.offset >= self.size():
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
            left = self.size() - self.offset
            self.buffer = self._readFromServer(min(self.chunk_size, left))
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

    def progress(self):
        return 100 * float(self.tell()) / float(self.size())

    def __format__(self, format_spec: str) -> str:
        return str(int(self.progress()))

    def _getContentLength(self):
        req: Request = Request(self.url)
        for header in self.headers:
            req.headers[header] = self.headers[header]
        f = urlopen(req)
        return int(ensureKey('Content-length', f.headers, "web server get request's headers"))

    def _getByteRange(self, start, end):
        req: Request = Request(self.url)
        for header in self.headers:
            req.headers[header] = self.headers[header]
        req.headers.update(self.headers)
        req.headers['range'] = "bytes=%s-%s" % (self.offset, end)
        f = urlopen(req)
        data = f.read()
        if len(data) != (end - start + 1):
            raise ProtocolError("Asked for range [{1}, {2}] at url {0}, but got back data length={3}".format(self.url, start, end, len(data)))
        return data
