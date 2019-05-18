import threading
from .time import Time
from .helpers import formatException
from .logbase import LogBase


class StopWorkException(Exception):
    pass


class Worker(threading.Thread, LogBase):
    def __init__(self, name, method, time: Time, interval=1):
        super().__init__(name=name, target=self.work)
        self._method = method
        self._time = time
        self._name = name
        self._last_error = None
        self._interval = interval

    def work(self):
        while True:
            try:
                self._method()
            except StopWorkException:
                break
            except Exception as e:
                self._last_error = e
                self.error("Worker {0} got an unexpected error".format(self._name))
                self.error(formatException(e))
            self._time.sleep(self._interval)

    def getLastError(self):
        return self._last_error
