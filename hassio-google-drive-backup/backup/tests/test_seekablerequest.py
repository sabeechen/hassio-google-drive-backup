from ..seekablerequest import SeekableRequest
from io import BytesIO
import requests


def test_test_stream():
    size = 1024 * 1024
    stream1 = getTestStream(size)
    stream2 = getTestStream(size)
    assert compareReads(stream1, stream2) == size


def test_upload(server):
    stream = getTestStream(1024 * 1024)
    upload(stream, "test")
    download = requests.get("http://localhost:1234/readfile?name=test")
    download.raise_for_status()
    response = BytesIO(download.content)
    stream.seek(0)
    assert compareReads(stream, response) == 1024 * 1024


def test_partial_read(server):
    length = 1024 * 1024
    offset = 1024
    stream = getTestStream(length)
    upload(stream, "test")

    stream.seek(offset)
    range_stream = getRangeStream(offset, length - 1, "test")
    assert compareReads(stream, range_stream) == length - offset


def test_various_ranges(server):
    verifyRanges(1024 * 1024, 1024, 2048)
    verifyRanges(100, 50, 75)
    verifyRanges(256, 0, 255)


def test_various_seekable(server):
    verifySeekandRead(length=27, start=10, seekable_chunk_size=3, read_chunk_size=4)
    verifySeekandRead(length=27, start=10, seekable_chunk_size=200, read_chunk_size=200)


def verifySeekandRead(length, start, seekable_chunk_size=1024, read_chunk_size=1024):
    stream: BytesIO = getTestStream(length)
    upload(stream)
    seekable = SeekableRequest("http://localhost:1234/readfile?name=test", headers={}, chunk_size=seekable_chunk_size)
    stream.seek(start)
    seekable.seek(start)
    assert compareReads(stream, seekable, chunk=read_chunk_size) == length - start


def verifyRanges(length, start, stop):
    assert stop < length
    assert stop >= start
    assert length > 0
    assert start >= 0
    stream: BytesIO = getTestStream(length)
    upload(stream)
    data_source = stream.getbuffer()[start:stop + 1]
    data_dest = getRangeStream(start, stop).getbuffer()
    assert data_dest == data_source


def getRangeStream(start, stop, name="test"):
    header = {"Range": "bytes={0}-{1}".format(start, stop)}
    download = requests.get("http://localhost:1234/readfile?name=" + name, headers=header)
    download.raise_for_status()
    assert download.headers["Content-Length"] == str(stop - start + 1)
    return BytesIO(download.content)


def upload(stream, name="test"):
    requests.post("http://localhost:1234/uploadfile?name=" + name, data=stream).raise_for_status()


def compareReads(stream1, stream2, chunk: int = 126):
    read = 0
    while(True):
        data1 = stream1.read(chunk)
        data2 = stream2.read(chunk)
        assert data1 == data2
        read += len(data1)
        if len(data1) == 0:
            break
    return read


def getTestStream(size: int):
    """
    Produces a stream of repeating prime sequences to avoid accidental repetition
    """
    arr = bytearray()
    while True:
        for prime in [4759, 4783, 4787, 4789, 4793, 4799, 4801, 4813, 4817, 4831, 4861, 4871, 4877, 4889, 4903, 4909, 4919, 4931, 4933, 4937]:
            for x in range(prime):
                if len(arr) < size:
                    arr.append(x % 255)
                else:
                    break
            if len(arr) >= size:
                break
        if len(arr) >= size:
            break
    return BytesIO(arr)
