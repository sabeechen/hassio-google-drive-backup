import io
from typing import Any
from .logbase import LogBase


class IteratorByteStream(io.IOBase, LogBase):
    def __init__(self, request_iterator: Any, size: int = None):
        self._position = 0
        self._bytes = bytearray()
        self._iterator = request_iterator

    def close(self):
        pass

    def isatty(self):
        return False

    def fileno(self):
        raise OSError()

    def flush(self):
        pass

    def readable(self):
        return True

    def seekable(self):
        return False

    def truncate(self, size=None):
        raise OSError()

    def writable(self):
        return False

    def readline(self, size=-1):
        raise OSError()

    def tell(self) -> Any:
        return self._position

    def read(self, size: int = 1024) -> Any:
        if len(self._bytes) > size:
            # buffer is big enough, just return
            ret = self._bytes[:size]
            self._position = self._position + size
            self._bytes = self._bytes[size:]
            return bytes(ret)

        # buffer is too small.  Advance until we fill it
        ret = self._bytes
        self._position = self._position + len(self._bytes)
        self._bytes = bytearray()
        while len(ret) < size:
            needed = size - len(ret)
            try:
                next_block = next(self._iterator)
                if len(next_block) <= needed:
                    # all goes to return
                    ret.extend(next_block)
                    self._position = self._position + len(next_block)
                    self._bytes = bytearray()
                else:
                    # part goes to return
                    ret.extend(next_block[:needed])
                    self._position = self._position + needed
                    self._bytes = bytearray(next_block[needed:])
            except StopIteration:
                break
        return bytes(ret)
