from datetime import timedelta
import io
from typing import Dict

from aiohttp import ClientSession
from aiohttp.client import ClientResponse, ClientPayloadError, ClientOSError
from asyncio.exceptions import TimeoutError
from collections import deque

from ..exceptions import LogicError, ensureKey
from ..logger import getLogger
from ..time import Time

logger = getLogger(__name__)

CONTENT_LENGTH_HEADER = "content-length"
CONTENT_LENGTH_ERROR = "Content size must be provided if the webserver doesn't provide it"
SERVER_CONTENT_LENGTH_ERROR = "Server returned a content length that didn't match the requested size"
POSITION_ERROR_MESSAGE = "AsyncHttpGetter must also be set up at position 0"
DEFAULT_CHUNK_SIZE = 1024 * 1024


# This class is dumb but it gets around a dumb problem
class Stupid(io.BytesIO):
    def __len__(self):
        return len(self.getvalue())


class AsyncHttpGetter:
    def __init__(self, url, headers: Dict[str, str], session, size: int = None, timeout=None, timeoutFactory=None, otherErrorFactory=None, time: Time = None):
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

        self._history = deque()
        self._time = time
        self._startTime = self._time.now()
        self.timeoutFactory = timeoutFactory
        self.otherErrorFactory = otherErrorFactory
        self.timeout = timeout

    async def setup(self):
        if not self._position == 0:
            raise LogicError(POSITION_ERROR_MESSAGE)
        await self._startReadRemoteAt(0)
        if CONTENT_LENGTH_HEADER in self._response.headers:
            self._size = int(ensureKey(
                CONTENT_LENGTH_HEADER, self._response.headers, "web server get request's headers"))
        elif self._size is None:
            raise LogicError(
                CONTENT_LENGTH_ERROR)

        self._history.append([self._time.now(), 0])
        return self._size

    def _ensureSetup(self):
        if self._size is None:
            raise LogicError("AsyncHttpGetter.setup() must be called first")

    def size(self) -> int:
        self._ensureSetup()
        return self._size

    def __len__(self):
        return self.size()

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

    # return the estimated speed of the tranfser in bytes/second
    def speed(self, period: timedelta = timedelta(seconds=10)):
        if len(self._history) < 2:
            return None
        now = self._time.now()
        intervals = []
        current = self._history[0]
        last_speed = 0
        for x in range(1, len(self._history)):
            next = self._history[x]
            seconds = (next[0] - current[0]).total_seconds()
            data = next[1] - current[1]
            if seconds == 0:
                speed = 0  # avoid div by 0
            else:
                speed = data / seconds
            intervals.append([current[0], next[0], speed])
            current = next
            last_speed = speed

        if current[0] < now - period:
            # if we didn't transfer any data over the sample period, don't try to estimate
            return None

        # behave as though we continued with the pseed form the last interval
        intervals.append([current[0], now, last_speed])

        # calculate the time-averaged speed over the given period
        stop = now
        start = now - period
        total = 0
        for interval in intervals:
            if start > interval[1]:
                continue
            if stop < interval[0]:
                continue
            overlap_start = max(start, interval[0])
            overlap_stop = min(stop, interval[1])
            if overlap_stop > overlap_start:
                total += (overlap_stop - overlap_start).total_seconds() * interval[2]
        return total / period.total_seconds()

    def startTime(self):
        return self._startTime

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
        try:
            resp = await self._session.get(self._url, headers=headers, timeout=self.timeout)
        except TimeoutError:
            if self.timeoutFactory is not None:
                raise self.timeoutFactory()
            raise
        except ClientPayloadError:
            if self.otherErrorFactory is not None:
                raise self.otherErrorFactory()
            raise
        except ClientOSError:
            if self.otherErrorFactory is not None:
                raise self.otherErrorFactory()
            raise
        resp.raise_for_status()
        if where == 0 and self._size is not None and CONTENT_LENGTH_HEADER in resp.headers and int(resp.headers[CONTENT_LENGTH_HEADER]) != self._size:
            raise LogicError(SERVER_CONTENT_LENGTH_ERROR)
        self._response = resp
        self._responseStart = where

    async def read(self, count=DEFAULT_CHUNK_SIZE):
        self._ensureSetup()
        ret = Stupid()
        if self._size is not None and self._position >= self._size:
            return ret

        # See if we need to move the stream elsewhere
        if self._responseStart != self._position:
            # Reset the stream's position
            await self._startReadRemoteAt(self._position)

        # Limit by how much we can get from the stream
        needed = min(count, self.size() - self._position)

        # And then get it
        try:
            data = await self._response.content.readexactly(needed)
        except TimeoutError:
            if self.timeoutFactory is not None:
                raise self.timeoutFactory()
            raise
        except ClientPayloadError:
            if self.otherErrorFactory is not None:
                raise self.otherErrorFactory()
            raise
        except ClientOSError:
            if self.otherErrorFactory is not None:
                raise self.otherErrorFactory()
            raise
        ret.write(data)
        # Keep track of where we are in the stream
        self._responseStart += len(data)
        self._position += len(data)
        self._history.append([self._time.now(), self._position])
        if len(self._history) > 50:
            self._history.popleft()

        ret.seek(0)
        return ret

    async def __aenter__(self):
        await self.setup()

    async def __aexit__(self, type, value, traceback):
        if self._response is not None:
            await self._response.release()

    async def close(self):
        await self.__aexit__()

    def __aiter__(self):
        return self

    async def __anext__(self):
        val = await self.read()
        if len(val) == 0:
            raise StopAsyncIteration
        return val.getbuffer()
