from injector import singleton, inject
import asyncio
from ipaddress import ip_address
from typing import Any, Dict, Union, Optional

import aiohttp
from aiohttp import hdrs, web, ClientSession
from aiohttp.web_exceptions import (
    HTTPBadGateway,
    HTTPServiceUnavailable,
    HTTPUnauthorized,
    HTTPNotFound
)
from multidict import CIMultiDict, istr

from backup.logger import getLogger
from .ports import Ports
from .base_server import BaseServer
from .simulated_supervisor import SimulatedSupervisor

ATTR_ADMIN = "admin"
ATTR_ENABLE = "enable"
ATTR_ICON = "icon"
ATTR_PANELS = "panels"
ATTR_SESSION = "session"
ATTR_TITLE = "title"
COOKIE_INGRESS = "ingress_session"
HEADER_TOKEN = "X-Supervisor-Token"
HEADER_TOKEN_OLD = "X-Hassio-Key"
REQUEST_FROM = "HASSIO_FROM"
JSON_RESULT = "result"
JSON_DATA = "data"
JSON_MESSAGE = "message"
RESULT_ERROR = "error"
RESULT_OK = "ok"

_LOGGER = getLogger(__name__)


def api_return_error(message: Optional[str] = None) -> web.Response:
    """Return an API error message."""
    return web.json_response(
        {JSON_RESULT: RESULT_ERROR, JSON_MESSAGE: message}, status=400
    )


def api_return_ok(data: Optional[Dict[str, Any]] = None) -> web.Response:
    """Return an API ok answer."""
    return web.json_response({JSON_RESULT: RESULT_OK, JSON_DATA: data or {}})


def api_process(method):
    """Wrap function with true/false calls to rest api."""

    async def wrap_api(api, *args, **kwargs):
        """Return API information."""
        try:
            answer = await method(api, *args, **kwargs)
        except Exception as err:
            return api_return_error(message=str(err))

        if isinstance(answer, dict):
            return api_return_ok(data=answer)
        if isinstance(answer, web.Response):
            return answer
        elif isinstance(answer, bool) and not answer:
            return api_return_error()
        return api_return_ok()

    return wrap_api


class Addon():
    def __init__(self, ports: Ports, token: str):
        self.ports = ports
        self.ip_address = "127.0.0.1"
        self.ingress_port = ports.ingress
        self.token = token


class SysIngress():
    def __init__(self, ports: Ports, token: str, cookie_value: str):
        self.ports = ports
        self.token = token
        self.cookie_value = cookie_value

    def validate_session(self, session):
        return session == self.cookie_value

    def get(self, token):
        if token == self.token:
            return Addon(self.ports, self.token)
        return None


class CoreSysAttributes():
    def __init__(self, ports: Ports, session: ClientSession, token: str, cookie_value: str):
        self.sys_ingress = SysIngress(ports, token, cookie_value)
        self.sys_websession = session


@singleton
class APIIngress(CoreSysAttributes, BaseServer):
    @inject
    def __init__(self, ports: Ports, session: ClientSession, supervisor: SimulatedSupervisor):
        self.addon_token = self.generateId(10)
        self.cookie_value = self.generateId(10)
        super().__init__(ports, session, self.addon_token, self.cookie_value)
        self.ports = ports
        self.supervisor = supervisor

    def routes(self):
        return [
            web.get("/startingress", self.start_ingress),
            web.get("/hassio/ingress/{slug}", self.ingress_panel),
            web.view("/api/hassio_ingress/{token}/{path:.*}", self.handler),
        ]

    def start_ingress(self, request: web.Request):
        resp = web.Response(status=303)
        resp.headers[hdrs.LOCATION] = "/hassio/ingress/" + self.supervisor._addon_slug
        resp.set_cookie(name=COOKIE_INGRESS, value=self.cookie_value, expires="Session", domain=request.url.host, path="/api/hassio_ingress/", httponly="false", secure="false")
        return resp

    def ingress_panel(self, request: web.Request):
        slug = request.match_info.get("slug")
        if slug != self.supervisor._addon_slug:
            raise HTTPNotFound()
        body = """
        <html>
            <head>
                <meta content="text/html;charset=utf-8" http-equiv="Content-Type">
                <meta content="utf-8" http-equiv="encoding">
                <title>Simulated Supervisor Ingress Panel</title>
                <style type="text/css" >
                    iframe {{
                        display: block;
                        width: 100%;
                        height: 100%;
                        border: 0;
                    }}
                </style>
            </head>
            <body>
                <div>
                    The Web-UI below is loaded through an iframe. <a href='startingress'>Start a new ingress session</a> if you get permission errors.
                </div>
                <iframe src="api/hassio_ingress/{0}/">
                    <html>
                        <head></head>
                        <body></body>
                    </html>
                </iframe>
            </body>
        </html>
        """.format(self.addon_token)
        resp = web.Response(body=body, content_type="text/html")
        resp.set_cookie(name=COOKIE_INGRESS, value=self.cookie_value, expires="Session", domain=request.url.host, path="/api/hassio_ingress/", httponly="false", secure="false")
        return resp

    """
    The class body below here is copied from
    https://github.com/home-assistant/supervisor/blob/38b0aea8e2a3b9a9614bb5d94959235a0fae235e/supervisor/api/ingress.py#L35
    In order to correctly reproduce the supervisor's kooky ingress proxy behavior.
    """

    def _extract_addon(self, request: web.Request) -> Addon:
        """Return addon, throw an exception it it doesn't exist."""
        token = request.match_info.get("token")

        # Find correct add-on
        addon = self.sys_ingress.get(token)
        if not addon:
            _LOGGER.warning("Ingress for %s not available", token)
            raise HTTPServiceUnavailable()

        return addon

    def _check_ha_access(self, request: web.Request) -> None:
        # always allow
        pass

    def _create_url(self, addon: Addon, path: str) -> str:
        """Create URL to container."""
        return f"http://{addon.ip_address}:{addon.ingress_port}/{path}"

    @api_process
    async def panels(self, request: web.Request) -> Dict[str, Any]:
        """Create a list of panel data."""
        addons = {}
        for addon in self.sys_ingress.addons:
            addons[addon.slug] = {
                ATTR_TITLE: addon.panel_title,
                ATTR_ICON: addon.panel_icon,
                ATTR_ADMIN: addon.panel_admin,
                ATTR_ENABLE: addon.ingress_panel,
            }

        return {ATTR_PANELS: addons}

    @api_process
    async def create_session(self, request: web.Request) -> Dict[str, Any]:
        """Create a new session."""
        self._check_ha_access(request)

        session = self.sys_ingress.create_session()
        return {ATTR_SESSION: session}

    async def handler(
        self, request: web.Request
    ) -> Union[web.Response, web.StreamResponse, web.WebSocketResponse]:
        """Route data to Supervisor ingress service."""
        self._check_ha_access(request)

        # Check Ingress Session
        session = request.cookies.get(COOKIE_INGRESS)
        if not self.sys_ingress.validate_session(session):
            _LOGGER.warning("No valid ingress session %s", session)
            raise HTTPUnauthorized()

        # Process requests
        addon = self._extract_addon(request)
        path = request.match_info.get("path")
        try:
            # Websocket
            if _is_websocket(request):
                return await self._handle_websocket(request, addon, path)

            # Request
            return await self._handle_request(request, addon, path)

        except aiohttp.ClientError as err:
            _LOGGER.error("Ingress error: %s", err)

        raise HTTPBadGateway()

    async def _handle_websocket(
        self, request: web.Request, addon: Addon, path: str
    ) -> web.WebSocketResponse:
        """Ingress route for websocket."""
        if hdrs.SEC_WEBSOCKET_PROTOCOL in request.headers:
            req_protocols = [
                str(proto.strip())
                for proto in request.headers[hdrs.SEC_WEBSOCKET_PROTOCOL].split(",")
            ]
        else:
            req_protocols = ()

        ws_server = web.WebSocketResponse(
            protocols=req_protocols, autoclose=False, autoping=False
        )
        await ws_server.prepare(request)

        # Preparing
        url = self._create_url(addon, path)
        source_header = _init_header(request, addon)

        # Support GET query
        if request.query_string:
            url = f"{url}?{request.query_string}"

        # Start proxy
        async with self.sys_websession.ws_connect(
            url,
            headers=source_header,
            protocols=req_protocols,
            autoclose=False,
            autoping=False,
        ) as ws_client:
            # Proxy requests
            await asyncio.wait(
                [
                    _websocket_forward(ws_server, ws_client),
                    _websocket_forward(ws_client, ws_server),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )

        return ws_server

    async def _handle_request(
        self, request: web.Request, addon: Addon, path: str
    ) -> Union[web.Response, web.StreamResponse]:
        """Ingress route for request."""
        url = self._create_url(addon, path)
        data = await request.read()
        source_header = _init_header(request, addon)

        async with self.sys_websession.request(
            request.method,
            url,
            headers=source_header,
            params=request.query,
            allow_redirects=False,
            data=data,
        ) as result:
            headers = _response_header(result)

            # Simple request
            if (
                hdrs.CONTENT_LENGTH in result.headers and int(result.headers.get(hdrs.CONTENT_LENGTH, 0)) < 4_194_000
            ):
                # Return Response
                body = await result.read()

                return web.Response(
                    headers=headers,
                    status=result.status,
                    content_type=result.content_type,
                    body=body,
                )

            # Stream response
            response = web.StreamResponse(status=result.status, headers=headers)
            response.content_type = result.content_type

            try:
                await response.prepare(request)
                async for data in result.content.iter_chunked(4096):
                    await response.write(data)

            except (
                aiohttp.ClientError,
                aiohttp.ClientPayloadError,
                ConnectionResetError,
            ) as err:
                _LOGGER.error("Stream error with %s: %s", url, err)

            return response


def _init_header(
    request: web.Request, addon: str
) -> Union[CIMultiDict, Dict[str, str]]:
    """Create initial header."""
    headers = {}

    # filter flags
    for name, value in request.headers.items():
        if name in (
            hdrs.CONTENT_LENGTH,
            hdrs.CONTENT_ENCODING,
            hdrs.SEC_WEBSOCKET_EXTENSIONS,
            hdrs.SEC_WEBSOCKET_PROTOCOL,
            hdrs.SEC_WEBSOCKET_VERSION,
            hdrs.SEC_WEBSOCKET_KEY,
            istr(HEADER_TOKEN),
            istr(HEADER_TOKEN_OLD),
        ):
            continue
        headers[name] = value

    # Update X-Forwarded-For
    forward_for = request.headers.get(hdrs.X_FORWARDED_FOR)
    connected_ip = ip_address(request.transport.get_extra_info("peername")[0])
    headers[hdrs.X_FORWARDED_FOR] = f"{forward_for}, {connected_ip!s}"

    return headers


def _response_header(response: aiohttp.ClientResponse) -> Dict[str, str]:
    """Create response header."""
    headers = {}

    for name, value in response.headers.items():
        if name in (
            hdrs.TRANSFER_ENCODING,
            hdrs.CONTENT_LENGTH,
            hdrs.CONTENT_TYPE,
            hdrs.CONTENT_ENCODING
        ):
            continue
        headers[name] = value

    return headers


def _is_websocket(request: web.Request) -> bool:
    """Return True if request is a websocket."""
    headers = request.headers

    if (
        "upgrade" in headers.get(hdrs.CONNECTION, "").lower() and headers.get(hdrs.UPGRADE, "").lower() == "websocket"
    ):
        return True
    return False


async def _websocket_forward(ws_from, ws_to):
    """Handle websocket message directly."""
    try:
        async for msg in ws_from:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await ws_to.send_str(msg.data)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await ws_to.send_bytes(msg.data)
            elif msg.type == aiohttp.WSMsgType.PING:
                await ws_to.ping()
            elif msg.type == aiohttp.WSMsgType.PONG:
                await ws_to.pong()
            elif ws_to.closed:
                await ws_to.close(code=ws_to.close_code, message=msg.extra)
    except RuntimeError:
        _LOGGER.warning("Ingress Websocket runtime error")
