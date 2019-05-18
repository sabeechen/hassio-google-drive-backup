import pytest
import socket
import requests

from dns.exception import Timeout
from dns.resolver import NXDOMAIN
from .faketime import FakeTime
from ..resolver import Resolver


@pytest.fixture
def resolver(time: FakeTime):
    return Resolver(time)


def test_entry(resolver: Resolver):
    old_method = socket.getaddrinfo
    with resolver as res:
        assert socket.getaddrinfo is not old_method
        assert socket.getaddrinfo == res._override_getaddrinfo
    assert socket.getaddrinfo is old_method


def test_resolution(resolver: Resolver):
    with resolver:
        resolver.toggle()
        resolver.setDnsServers(["8.8.8.8", "8.8.4.4"])
        resolver.addResolveAddress("google.com")
        requests.get("http://google.com/")

    assert resolver.cache["google.com"] is not None


def test_timeout(resolver: Resolver):
    with resolver:
        resolver.toggle()
        resolver.setDnsServers(["8.8.8.8.6"])
        resolver.resolver.timeout = 5
        resolver.addResolveAddress("google.com")
        with pytest.raises(Timeout):
            requests.get("http://google.com/")


def test_bad_name(resolver: Resolver):
    with resolver:
        resolver.toggle()
        resolver.setDnsServers(["8.8.8.8"])
        resolver.addResolveAddress("dfleinahsgftrutyo.com")
        with pytest.raises(NXDOMAIN):
            requests.get("http://dfleinahsgftrutyo.com/")

