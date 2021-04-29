from ..logger import getLogger

MAX_FACTOR = 20  # avoid weirdness with python's arbitary integer precision
MAX_WAIT = 60 * 60  # 1 hour

logger = getLogger(__name__)


class Backoff():
    def __init__(self, initial=None, base=2, exp=2, max=MAX_WAIT, attempts=None):
        self._attempts = attempts
        self._initial = initial
        self._start = base
        self._max = max
        self._exp = exp
        self._counter = 0

    def reset(self):
        self._counter = 0

    def peek(self):
        exp = self._counter - 1
        if self._counter == 1 and self._initial is not None:
            return self._initial
        elif self._initial is not None:
            exp -= 1

        exp = min(exp, MAX_FACTOR)
        computed = self._start * pow(self._exp, exp)

        if self._max:
            computed = min(self._max, computed)
        return computed

    def backoff(self, error):
        if self._attempts and self._counter >= self._attempts:
            raise error
        self._counter += 1
        return self.peek()

    def maxOut(self):
        self._counter = 100
