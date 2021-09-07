import asyncio

from ..time import Time
from ..config import Startable
from ..logger import getLogger

logger = getLogger(__name__)


class StopWorkException(Exception):
    pass


class Worker(Startable):
    def __init__(self, name, method, time: Time, interval=1):
        super().__init__()
        self._method = method
        self._time = time
        self._name = name
        self._last_error = None
        self._interval = interval
        self._task = None
        self._should_stop = False

    async def work(self):
        while not self._should_stop:
            try:
                await self._method()
            except StopWorkException:
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._last_error = e
                logger.error(
                    "Worker {0} got an unexpected error".format(self._name))
                logger.printException(e)
            await self._time.sleepAsync(self._interval)

    async def start(self):
        self._should_stop = False
        self._task = asyncio.create_task(self.work(), name=self._name)
        return self._task

    async def stop(self):
        self._should_stop = True
        if self._task is not None:
            self._task.cancel()
            await asyncio.wait([self._task])

    def isRunning(self):
        if self._task is None:
            return False
        return not self._task.done()

    def getLastError(self):
        return self._last_error
