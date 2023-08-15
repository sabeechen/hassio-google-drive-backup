from ..time import Time


class TokenBucket:
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
        if tokens < 0:
            return False
        self.refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    async def consumeWithWait(self, min_tokens: int, max_tokens: int):
        self.refill()
        if self.tokens >= max_tokens:
            self.consume(max_tokens)
            return max_tokens
        if self.tokens >= min_tokens:
            ret = self.tokens
            self.consume(self.tokens)
            return ret

        # delay until the minimum tokens are available and reset
        delta = min_tokens - self.tokens
        await self._time.sleepAsync(delta / self.fill_rate)
        self.tokens = 0
        self.timestamp = self._time.monotonic()
        return min_tokens

    def refill(self):
        now = self._time.monotonic()
        if self.tokens < self.capacity:
            delta = self.fill_rate * (now - self.timestamp)
            self.tokens = min(self.capacity, self.tokens + delta)
        self.timestamp = now
