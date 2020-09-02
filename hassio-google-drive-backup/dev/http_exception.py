from aiohttp.web import HTTPClientError


class HttpMultiException(HTTPClientError):
    def __init__(self, code):
        self.status_code = code
