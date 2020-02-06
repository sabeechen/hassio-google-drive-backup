import io
from typing import Dict
from .exceptions import LogicError, ensureKey
from aiohttp.client import ClientResponse
from aiohttp import ClientSession

CONTENT_LENGTH_HEADER = "content-length"


class AsyncHttpGetter:
    def __init__(self, url, headers: Dict[str, str], session, size: int = None):
        self._url: str = url

        # Current position of the stream
        self._position: int = 0

        # Total size of the stream
        self._size: int = size

        # Headers that should get sent with every request
        self._headers: Dict[str, str] = headers

        # Session used to make http requests.
        self._session: ClientSession = session

        # Most recent session request
        self._response: ClientResponse = None

        # Where the resposne currently starts
        self._responseStart = 0

    async def setup(self):
        if not self._position == 0:
            raise LogicError("AsyncHttpGetter must also be set up at position 0")
        await self._startReadRemoteAt(0)
        if CONTENT_LENGTH_HEADER in self._response.headers:
            self._size = int(ensureKey(CONTENT_LENGTH_HEADER, self._response.headers, "web server get request's headers"))
        elif self._size is None:
            raise LogicError("Content size must be provided if the webserver doesn't provide it")
        return self._size

    def _ensureSetup(self):
        if self._size is None:
            raise LogicError("AsyncHttpGetter.setup() must be called first")

    def size(self) -> int:
        self._ensureSetup()
        return self._size

    def position(self, pos=None):
        if pos is not None:
            self._position = pos
        return self._position

    async def generator(self, chunk_size):
        while True:
            chunk = await self.read(chunk_size)
            if len(chunk.getbuffer()) == 0:
                break
            yield chunk.getbuffer()

    def progress(self):
        if self._size == 0:
            return 0
        self._ensureSetup()
        if self._size == 0:
            return 0
        return 100 * float(self.position()) / float(self._size)

    def __format__(self, format_spec: str) -> str:
        return str(int(self.progress()))

    async def _startReadRemoteAt(self, where=None):
        if where is None:
            where = self._position
        headers = self._headers.copy()
        # request a byte range
        if where != 0:
            headers['range'] = "bytes=%s-%s" % (self._position, self._size - 1)
        if self._response is not None:
            await self._response.release()
        resp = await self._session.get(self._url, headers=headers)
        resp.raise_for_status()
        if where == 0 and self._size is not None and CONTENT_LENGTH_HEADER in resp.headers and int(resp.headers[CONTENT_LENGTH_HEADER]) != self._size:
            raise LogicError("Server returned a content length that didn't match the requested size")
        self._response = resp
        self._responseStart = where

    async def read(self, count):
        self._ensureSetup()
        ret = io.BytesIO()
        if self._size is not None and self._position >= self._size:
            return ret

        # See if we need to move the stream elsewhere
        if self._responseStart != self._position:
            # Reset the stream's position
            await self._startReadRemoteAt(self._position)

        # Limit by how much we can get from the stream
        needed = min(count, self.size() - self._position)

        # And then get it
        data = await self._response.content.readexactly(needed)
        ret.write(data)
        # Keep track of where we are in the stream
        self._responseStart += len(data)
        self._position += len(data)

        ret.seek(0)
        return ret

    async def __aenter__(self):
        await self.setup()

    async def __aexit__(self, type, value, traceback):
        if self._response is not None:
            await self._response.release()
