import asyncio

from .helpers import formatException
from .logbase import LogBase
from .time import Time


class StopWorkException(Exception):
    pass


class Worker(LogBase):
    def __init__(self, name, method, time: Time, interval=1):
        super().__init__()
        self._method = method
        self._time = time
        self._name = name
        self._last_error = None
        self._interval = interval
        self._task = None

    async def work(self):
        while True:
            try:
                await self._method()
            except StopWorkException:
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._last_error = e
                self.error(
                    "Worker {0} got an unexpected error".format(self._name))
                self.error(formatException(e))
            await self._time.sleepAsync(self._interval)

    def start(self):
        self._task = asyncio.create_task(self.work(), name=self._name)
        return self._task

    def isRunning(self):
        if self._task is None:
            return False
        return not self._task.done()

    def getLastError(self):
        return self._last_error
