import socket
import dns
import dns.resolver

from .logbase import LogBase
from threading import Lock
from typing import Dict, List, Any
from datetime import timedelta

TTL_HOURS = 12


class Resolver(LogBase):
    def __init__(self, time):
        self.cache: Dict[str, Any] = {}
        self.overrides: Dict[str, List[str]] = {}
        self.resolver: dns.resolver.Resolver = None
        self.lock: Lock = Lock()
        self.old_getaddrinfo = None
        self.ignoreIpv6 = False
        self.time = time
        self.enabled = False

    def addResolveAddress(self, address):
        with self.lock:
            if address not in self.cache:
                self.cache[address] = None

    def addOverride(self, host, addresses):
        with self.lock:
            self.overrides[host] = addresses

    def toggle(self):
        self.enabled = not self.enabled

    def clearOverrides(self):
        with self.lock:
            self.overrides = {}

    def setDnsServers(self, servers):
        with self.lock:
            self.resolver = dns.resolver.Resolver()
            self.resolver.nameservers = servers

    def setIgnoreIpv6(self, ignore):
        self.ignoreIpv6 = ignore

    def __enter__(self):
        with self.lock:
            self.old_getaddrinfo = socket.getaddrinfo
            socket.getaddrinfo = self._override_getaddrinfo
        return self

    def __exit__(self, a, b, c):
        with self.lock:
            socket.getaddrinfo = self.old_getaddrinfo
            self.old_getaddrinfo = None

    def _override_getaddrinfo(self, *args, **kwargs):
        with self.lock:
            if len(args) > 1 and args[0] in self.cache:
                override = self.cachedLookup(args[0])
                if override is not None and len(override) > 0:
                    resp = []
                    for ip in override:
                        resp.append((socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, args[1])))
                    return resp

        responses = self.old_getaddrinfo(*args, **kwargs)
        if self.ignoreIpv6:
            responses = [response for response in responses if response[0] != socket.AF_INET6]
        return responses

    def cachedLookup(self, host):
        if host in self.overrides:
            return self.overrides[host]
        if self.resolver is None:
            return None
        if not self.enabled:
            return None
        
        entry = self.cache.get(host)
        if entry is not None and entry[1] > self.time.now():
            return entry[0]
        addresses = []
        for data in self.resolver.query(host, "A", tcp=True):
            addresses.append(data.address)
        data = (addresses, self.time.now() + timedelta(hours=TTL_HOURS))
        self.cache[host] = data
        return addresses
