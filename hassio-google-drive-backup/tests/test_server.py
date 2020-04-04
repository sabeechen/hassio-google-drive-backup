
import pytest
from yarl import URL
from dev.simulationserver import SimulationServer
from aiohttp import ClientSession, ClientResponse
from backup.config import Config, Setting

@pytest.mark.asyncio
async def test_refresh_known_error(server: SimulationServer, session: ClientSession, config: Config, server_url: str):
    async with session.post(URL(server_url).with_path("drive/refresh"), json={"blah": "blah"}) as r:
        assert r.status == 503
        assert await r.json() == {
            'error': "Required key 'refresh_token' was missing from the request payload"
        }


@pytest.mark.asyncio
async def test_refresh_unknown_error(server: SimulationServer, session: ClientSession, config: Config, server_url: str):
    async with session.post(URL(server_url).with_path("drive/refresh"), data={}) as r:
        assert r.status == 500
        assert len((await r.json())["error"]) > 0
