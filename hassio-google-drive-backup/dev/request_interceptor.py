
import re
from aiohttp.web import Request, Response
from asyncio import Event, sleep
from injector import singleton, inject


class UrlMatch():
    def __init__(self, url, attempts=None, status=None, response="", wait=False, sleep=None):
        self.url: str = url
        self.attempts: int = attempts
        self.status: int = status
        self.wait_event: Event = Event()
        self.trigger_event: Event = Event()
        self.response: str = ""
        self.wait: bool = wait
        self.trigger_event.clear()
        self.wait_event.clear()
        self.sleep = sleep

    def isMatch(self, request):
        return re.match(self.url, request.url.path)

    async def waitForCall(self):
        await self.trigger_event.wait()

    def clear(self):
        self.wait_event.set()

    async def _doAction(self, request):
        if self.status is not None:
            await self._readAll(request)
            return Response(status=self.status, text=self.response)
        elif self.wait:
            self.trigger_event.set()
            await self.wait_event.wait()
        elif self.sleep is not None:
            await sleep(self.sleep)

    async def called(self, request):
        if self.attempts is None or self.attempts <= 0:
            return await self._doAction(request)
        elif self.attempts is not None:
            self.attempts -= 1

    async def _readAll(self, request):
        data = bytearray()
        content = request.content
        while True:
            chunk, done = await content.readchunk()
            data.extend(chunk)
            if len(chunk) == 0:
                break
        return data


@singleton
class RequestInterceptor:
    @inject
    def __init__(self):
        self._matchers = []

    def setError(self, url, status, attempts=None):
        matcher = UrlMatch(url, attempts, status)
        self._matchers.append(matcher)

    def clear(self):
        self._matchers.clear()

    def setWaiter(self, url, attempts=None):
        matcher = UrlMatch(url, attempts, wait=True)
        self._matchers.append(matcher)
        return matcher

    def setSleep(self, url, attempts=None, sleep=None):
        matcher = UrlMatch(url, attempts, sleep=sleep)
        self._matchers.append(matcher)
        return matcher

    async def checkUrl(self, request):
        self.record(request)
        for match in self._matchers:
            if match.isMatch(request):
                return await match.called(request)
        return None

    def record(self, request):
        pass
