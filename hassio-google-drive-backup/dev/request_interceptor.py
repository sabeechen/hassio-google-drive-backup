import re
from aiohttp.web import Request, Response
from asyncio import Event, sleep
from aiohttp.web_response import json_response
from injector import singleton, inject


class UrlMatch():
    def __init__(self, url, fail_after=None, status=None, response=None, wait=False, sleep=None, fail_for=None):
        self.url: str = url
        self.fail_after: int = fail_after
        self.status: int = status
        self.wait_event: Event = Event()
        self.trigger_event: Event = Event()
        self.response: str = ""
        self.wait: bool = wait
        self.trigger_event.clear()
        self.wait_event.clear()
        self.sleep = sleep
        self.response = response
        self.fail_for = fail_for
        self.responses = []
        self._calls = 0

    def addResponse(self, response):
        self.responses.append(response)

    def isMatch(self, request):
        return re.match(self.url, request.url.path)

    async def waitForCall(self):
        await self.trigger_event.wait()

    def clear(self):
        self.wait_event.set()

    def callCount(self):
        return self._calls

    async def _doAction(self, request: Request):
        self._calls += 1
        if len(self.responses) > 0:
            return self.responses.pop(0)
        if self.status is not None:
            await self._readAll(request)
            if self.response:
                return json_response(self.response, status=self.status)
            else:
                return Response(status=self.status)
        elif self.wait:
            self.trigger_event.set()
            await self.wait_event.wait()
        elif self.sleep is not None:
            await sleep(self.sleep)

    async def called(self, request: Request):
        if self.fail_after is None or self.fail_after <= 0:
            if self.fail_for is not None and self.fail_for > 0:
                self.fail_for -= 1
                return await self._doAction(request)
            elif self.fail_for is not None:
                return None

            return await self._doAction(request)
        elif self.fail_after is not None:
            self.fail_after -= 1

    async def _readAll(self, request: Request):
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
        self._history = []

    def setError(self, url, status=None, fail_after=None, fail_for=None, response=None) -> UrlMatch:
        matcher = UrlMatch(url, fail_after, status=status, response=response, fail_for=fail_for)
        self._matchers.append(matcher)
        return matcher

    def clear(self):
        self._matchers.clear()
        self._history.clear()

    def setWaiter(self, url, attempts=None):
        matcher = UrlMatch(url, attempts, wait=True)
        self._matchers.append(matcher)
        return matcher

    def setSleep(self, url, attempts=None, sleep=None, wait_for=None):
        matcher = UrlMatch(url, attempts, sleep=sleep, fail_for=wait_for)
        self._matchers.append(matcher)
        return matcher

    async def checkUrl(self, request):
        ret = None
        self.record(request)
        for match in self._matchers:
            if match.isMatch(request):
                ret = await match.called(request)
        return ret

    def record(self, request: Request):
        record = str(request.url.path)
        if len(request.url.query_string) > 0:
            record += "?" + str(request.url.query_string)
        self._history.append(record)

    def urlWasCalled(self, url) -> bool:
        for called_url in self._history:
            if url == called_url or re.match(url, called_url):
                return True
        return False
