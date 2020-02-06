import pytest
from ..resolver import SubvertingResolver
from ..config import Config
from ..settings import Setting


@pytest.mark.asyncio
async def test_empty_name_server(resolver: SubvertingResolver, config: Config):
    assert resolver._alt_dns.nameservers == ["8.8.8.8", "8.8.4.4"]
    assert resolver._resolver is resolver._original_dns
    config.override(Setting.ALTERNATE_DNS_SERVERS, "")
    resolver.updateConfig()
    assert resolver._resolver is resolver._alt_dns

    # make sure the value is cached
    prev = resolver._alt_dns
    resolver.updateConfig()
    assert resolver._alt_dns is prev


async def test_toggle(resolver: SubvertingResolver):
    assert resolver._resolver is resolver._original_dns
    resolver.toggle()
    assert resolver._resolver is resolver._alt_dns
    resolver.toggle()
    assert resolver._resolver is resolver._original_dns
