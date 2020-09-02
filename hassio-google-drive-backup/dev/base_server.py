import random
import re
import io
from aiohttp.web import HTTPBadRequest, Request, Response
from typing import Any

rangePattern = re.compile("bytes=\\d+-\\d+")
bytesPattern = re.compile("^bytes \\d+-\\d+/\\d+$")
intPattern = re.compile("\\d+")


class BaseServer:
    def generateId(self, length: int = 30) -> str:
        random_int = random.randint(0, 1000000)
        ret = str(random_int)
        return ret + ''.join(map(lambda x: str(x), range(0, length - len(ret))))

    def timeToRfc3339String(self, time) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ")

    def serve_bytes(self, request: Request, bytes: bytearray, include_length: bool = True) -> Any:
        if "Range" in request.headers:
            # Do range request
            if not rangePattern.match(request.headers['Range']):
                raise HTTPBadRequest()

            numbers = intPattern.findall(request.headers['Range'])
            start = int(numbers[0])
            end = int(numbers[1])

            if start < 0:
                raise HTTPBadRequest()
            if start > end:
                raise HTTPBadRequest()
            if end > len(bytes) - 1:
                raise HTTPBadRequest()
            resp = Response(body=bytes[start:end + 1], status=206)
            resp.headers['Content-Range'] = "bytes {0}-{1}/{2}".format(
                start, end, len(bytes))
            if include_length:
                resp.headers["Content-length"] = str(len(bytes))
            return resp
        else:
            resp = Response(body=io.BytesIO(bytes))
            resp.headers["Content-length"] = str(len(bytes))
            return resp

    async def readAll(self, request):
        data = bytearray()
        content = request.content
        while True:
            chunk, done = await content.readchunk()
            data.extend(chunk)
            if len(chunk) == 0:
                break
        return data
