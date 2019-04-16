from ..responsestream import IteratorByteStream
from ..seekablerequest import SeekableRequest


def test_iteration(mocker) -> None:
    stream = IteratorByteStream(generator(255))
    index = 0
    while index < 255:
        assert stream.read(1) == bytearray([index])
        index = index + 1
    assert stream.read(1) == bytearray()


def test_iteration_chunk(mocker) -> None:
    stream = IteratorByteStream(generator(255, 5))
    index = 0
    while index < 255:
        assert stream.read(1) == bytearray([index])
        index = index + 1
    assert stream.read(1) == bytearray()


def test_iteration_chunk_offset(mocker) -> None:
    stream = IteratorByteStream(generator(15, 5))

    assert stream.read(3) == bytearray([0, 1, 2])
    assert stream.read(3) == bytearray([3, 4, 5])
    assert stream.read(3) == bytearray([6, 7, 8])
    assert stream.read(3) == bytearray([9, 10, 11])
    assert stream.read(3) == bytearray([12, 13, 14])
    assert stream.read(3) == bytearray()


def test_iteration_chunk_offset_4(mocker) -> None:
    stream = IteratorByteStream(generator(15, 5))

    assert stream.read(4) == bytearray([0, 1, 2, 3])
    assert stream.read(4) == bytearray([4, 5, 6, 7])
    assert stream.read(4) == bytearray([8, 9, 10, 11])
    assert stream.read(4) == bytearray([12, 13, 14])
    assert stream.read(4) == bytearray()


def generator(length=255, chunk=1):
    index = 0
    while(index < length):
        ret = bytearray()
        inner_index = 0
        while inner_index < chunk and index < length:
            ret.append(int(index))
            index = index + 1
            inner_index = inner_index + 1
        yield ret


class FakeStream(SeekableRequest):
    def __init__(self, length, fake_chunk_size):
        super(FakeStream, self).__init__("", {}, chunk_size=fake_chunk_size)
        self.length = length
        self.ranges = []

    def _getContentLength(self):
        return self.length

    def _getByteRange(self, start, end):
        self.ranges.append((start, end))
        return bytearray(self.doIterate(start, end))

    def doIterate(self, start, end):
        for n in range(start, end + 1):
            yield n % 256


def test_seekable_trivial():
    stream = FakeStream(length=1, fake_chunk_size=1)
    assert stream.read(1) == bytearray([0])
    assert stream.read(1) == bytearray()
    assert stream.ranges == [(0, 0)]


def test_seekable_buffer_read_three():
    stream = FakeStream(length=3, fake_chunk_size=1)
    assert stream.read(1) == bytearray([0])
    assert stream.read(1) == bytearray([1])
    assert stream.read(1) == bytearray([2])
    assert stream.read(1) == bytearray()
    assert stream.ranges == [
        (0, 0),
        (1, 1),
        (2, 2)
    ]


def test_seekable_buffering():
    stream = FakeStream(length=10, fake_chunk_size=10)
    for x in range(10):
        assert stream.read(1) == bytearray([x])
    assert stream.read(1) == bytearray()

    assert stream.ranges == [(0, 9)]


def test_seekable_buffering_chunks():
    stream = FakeStream(length=25, fake_chunk_size=10)
    for x in range(25):
        assert stream.read(1) == bytearray([x])
    assert stream.read(1) == bytearray()

    assert stream.ranges == [(0, 9), (10, 19), (20, 24)]


def test_seekable_small_file():
    stream = FakeStream(length=10, fake_chunk_size=20)
    assert stream.read(100) == bytearray(range(10))
    assert stream.read(100) == bytearray()
    assert stream.ranges == [(0, 9)]
