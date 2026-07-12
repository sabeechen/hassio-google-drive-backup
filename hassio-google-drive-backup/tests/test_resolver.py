import pytest
import socket

from backup.config import Config, Setting
from backup.util import Resolver


@pytest.mark.asyncio
async def test_empty_name_server(resolver: Resolver, config: Config):
    assert len(resolver._resolver.nameservers) > 0
    assert resolver._alternate_resolver is None

    config.override(Setting.ALTERNATE_DNS_SERVERS, "1.2.3.4,5.6.7.8")
    resolver.updateConfig()
    assert resolver._alternate_resolver is not None
    assert resolver._alternate_resolver._resolver.nameservers == ["1.2.3.4", "5.6.7.8"]


@pytest.mark.asyncio
async def test_hard_resolve(resolver: Resolver, config: Config):
    expected = [{
        'family': 0,
        'flags': socket.AddressInfo.AI_NUMERICHOST,
        'port': 1234,
        'proto': 0,
        'host': "1.2.3.4",
        'hostname': "www.googleapis.com"
    }]
    config.override(Setting.DRIVE_IPV4, "1.2.3.4")
    assert await resolver.resolve("www.googleapis.com", 1234, 0) == expected
