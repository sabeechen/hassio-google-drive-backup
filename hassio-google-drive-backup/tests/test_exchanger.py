import pytest

from dev.simulationserver import SimulationServer
from backup.time import Time
from aiohttp import ClientSession
from backup.config import Config, Setting
from backup.drive import DriveRequests
from backup.exceptions import CredRefreshMyError


@pytest.mark.asyncio
async def test_correct_host(time: Time, session: ClientSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, server_url):
    assert config._preferredTokenHost is None

    # Verfiy the preferred host gets set when exchanging creds
    await drive_requests.exchanger.refresh(drive_requests.creds)

    assert config._preferredTokenHost == "localhost"


@pytest.mark.asyncio
async def test_some_bad_hosts(time: Time, session: ClientSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, server_url):
    assert config._preferredTokenHost is None
    config.override(Setting.TOKEN_SERVER_HOST, "https://this.goes.nowhere.info," + str(server_url))

    # Verfiy the preferred host gets set when exchanging creds
    await drive_requests.exchanger.refresh(drive_requests.creds)

    assert config._preferredTokenHost == "localhost"


@pytest.mark.asyncio
async def test_all_bad_hosts(time: Time, session: ClientSession, config: Config, server: SimulationServer, drive_requests: DriveRequests):
    assert config._preferredTokenHost is None
    config.override(Setting.TOKEN_SERVER_HOST, "https://this.goes.nowhere.info,http://also.a.bad.host")

    # Verfiy the preferred host gets set when exchanging creds
    with pytest.raises(CredRefreshMyError):
        await drive_requests.exchanger.refresh(drive_requests.creds)

    assert config._preferredTokenHost is None
