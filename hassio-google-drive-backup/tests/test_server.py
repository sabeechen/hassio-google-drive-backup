
import pytest
from yarl import URL
from dev.simulationserver import SimulationServer
from aiohttp import ClientSession, hdrs
from backup.config import Config


@pytest.mark.asyncio
async def test_refresh_known_error(server: SimulationServer, session: ClientSession, config: Config, server_url: URL):
    async with session.post(server_url.with_path("drive/refresh"), json={"blah": "blah"}) as r:
        assert r.status == 503
        assert await r.json() == {
            'error': "Required key 'refresh_token' was missing from the request payload"
        }


@pytest.mark.asyncio
async def test_refresh_unknown_error(server: SimulationServer, session: ClientSession, config: Config, server_url: URL):
    async with session.post(server_url.with_path("drive/refresh"), data={}) as r:
        assert r.status == 500
        assert len((await r.json())["error"]) > 0


@pytest.mark.asyncio
async def test_old_auth_method(server: SimulationServer, session: ClientSession, server_url: URL):
    start_auth = server_url.with_path("drive/authorize").with_query({
        "redirectbacktoken": "http://example.com"
    })

    # Verify the redirect to Drive's oauthv2 endpoint
    async with session.get(start_auth, data={}, allow_redirects=False) as r:
        assert r.status == 303
        redirect = URL(r.headers[hdrs.LOCATION])
        assert redirect.path == "/o/oauth2/v2/auth"
        assert redirect.host == "localhost"

    # Verify the redirect back to the server's oauth page
    async with session.get(redirect, data={}, allow_redirects=False) as r:
        assert r.status == 303
        redirect = URL(r.headers[hdrs.LOCATION])
        assert redirect.path == "/drive/authorize"
        assert redirect.host == "localhost"

    # Verify we gte redirected back to the addon (example.com) with creds
    async with session.get(redirect, data={}, allow_redirects=False) as r:
        assert r.status == 303
        redirect = URL(r.headers[hdrs.LOCATION])
        assert redirect.query.get("creds") is not None
        assert redirect.host == "example.com"
