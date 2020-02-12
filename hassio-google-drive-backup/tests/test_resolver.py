import pytest
import socket

from backup.config import Config, Setting
from backup.util import Resolver


@pytest.mark.asyncio
async def test_empty_name_server(resolver: Resolver, config: Config):
    assert resolver._alt_dns.nameservers == ["8.8.8.8", "8.8.4.4"]
    assert resolver._resolver is resolver._original_dns
    config.override(Setting.ALTERNATE_DNS_SERVERS, "")
    resolver.updateConfig()
    assert resolver._resolver is resolver._alt_dns

    # make sure the value is cached
    prev = resolver._alt_dns
    resolver.updateConfig()
    assert resolver._alt_dns is prev


@pytest.mark.asyncio
async def test_toggle(resolver: Resolver):
    assert resolver._resolver is resolver._original_dns
    resolver.toggle()
    assert resolver._resolver is resolver._alt_dns
    resolver.toggle()
    assert resolver._resolver is resolver._original_dns


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
    resolver.toggle()
    assert await resolver.resolve("www.googleapis.com", 1234, 0) == expected
    resolver.toggle()
    assert await resolver.resolve("www.googleapis.com", 1234, 0) == expected
