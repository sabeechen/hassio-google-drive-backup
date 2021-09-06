
import aiohttp.client as aiohttp
import aiohttp.tracing as tracing
from .logger import getLogger

logger = getLogger(__name__)


class TracingSession(aiohttp.ClientSession):
    def __init__(self, **kwargs):
        self.trace_config = aiohttp.TraceConfig()
        self.trace_config.on_request_start.append(self.trace_request_start)
        self.trace_config.on_request_end.append(self.trace_request_end)
        self.trace_config.on_request_exception.append(self.trace_request_exception)
        self.trace_config.on_response_chunk_received.append(self.trace_chunk_recv)
        self.trace_config.on_request_chunk_sent.append(self.trace_chunk_sent)
        self._record = False
        self._records = []
        super().__init__(**kwargs, trace_configs=[self.trace_config])

    @property
    def record(self) -> bool:
        return self._record

    @record.setter
    def record(self, value: bool):
        self._record = value

    def clearRecord(self):
        self._records = []

    async def _request(self, method, url, **kwargs):
        if self.record:
            self._records.append({'method': method, 'url': url, 'other_args': kwargs})
        resp = await super()._request(method, url, **kwargs, trace_request_ctx="{0} {1}".format(method, url))
        logger.trace("Initial response data: %s %s", resp.method, resp.url)
        logger.trace("  headers:")
        for header in resp.headers:
            logger.trace("    %s: %s", header, resp.headers[header])
        return resp

    def print_headers(self, headers):
        for header in headers:
            logger.trace("    %s: %s", header, 'redacted' if ('Authorization' in header) else headers[header])

    async def trace_request_start(self, session, trace_config_ctx, params: tracing.TraceRequestStartParams):
        logger.trace("Request started: %s", trace_config_ctx.trace_request_ctx)
        logger.trace("  sent headers:")
        self.print_headers(params.headers)

    async def trace_request_exception(self, session, trace_config_ctx, params: tracing.TraceRequestExceptionParams):
        logger.trace("Request exception: %s", trace_config_ctx.trace_request_ctx)
        logger.trace(logger.formatException(params.exception))

    async def trace_request_end(self, session, trace_config_ctx, params: tracing.TraceRequestEndParams):
        logger.trace("Request ending: %s", trace_config_ctx.trace_request_ctx)
        logger.trace("  status: %s", params.response.status)
        logger.trace("  recieved headers:")
        self.print_headers(params.response.headers)

    async def trace_chunk_recv(self, session, trace_config_ctx, params: tracing.TraceResponseChunkReceivedParams):
        logger.trace("Recieved chunk: %s", trace_config_ctx.trace_request_ctx)
        logger.trace("  length: %s", len(params.chunk))

    async def trace_chunk_sent(self, session, trace_config_ctx, params: tracing.TraceRequestChunkSentParams):
        logger.trace("Sent chunk: %s", trace_config_ctx.trace_request_ctx)
        logger.trace("  length: %s", len(params.chunk))
