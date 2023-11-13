from ..time import Time
from injector import inject, singleton


@singleton
class TokenBucket:
    """
    Implements a "leaky bucket" token algorithm, used to limit upload speed to Google Drive.
    """
    @inject
    def __init__(self, time: Time, capacity, fill_rate, initial_tokens=None):
        self.capacity = float(capacity)
        self.fill_rate = float(fill_rate)
        self._time = time
        if initial_tokens is not None:
            self.tokens = float(initial_tokens)
        else:
            self.tokens = float(capacity)
        self.timestamp = self._time.monotonic()

    def consume(self, tokens):
        """
        Attempts to consume the given number of tokens, returning true if there were enough tokenas availabel and 
        false otherwise.
        """
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    async def consumeWithWait(self, min_tokens: int, max_tokens: int):
        """
        Consumes a number of tokens between min_tokens and max_tokens
        - If at least max_tokens are available, consumes that many and returns immediately
        - If less than min_tokens are available, waits until min_tokens are availabel and consumes them
        - Else consumes as many tokens as are available
        Always returns the positive number of tokens consumed.
        """
        self._refill()
        if self.tokens >= max_tokens:
            self.consume(max_tokens)
            return max_tokens
        if self.tokens >= min_tokens:
            ret = self.tokens
            self.consume(self.tokens)
            return ret

        # Delay until the minimum tokens are available and reset
        delta = min_tokens - self.tokens
        await self._time.sleepAsync(delta / self.fill_rate)
        self.tokens = 0
        self.timestamp = self._time.monotonic()
        return min_tokens

    def _refill(self):
        now = self._time.monotonic()
        if self.tokens < self.capacity:
            delta = self.fill_rate * (now - self.timestamp)
            self.tokens = min(self.capacity, self.tokens + delta)
        self.timestamp = now
