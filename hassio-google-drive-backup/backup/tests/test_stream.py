from ..seekablerequest import SeekableRequest


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
