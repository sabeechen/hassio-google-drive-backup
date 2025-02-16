import socket
from typing import Any, Dict, List

import aiodns
from aiohttp.resolver import AsyncResolver
from injector import inject, singleton

from ..config import Config, Setting
from ..logger import getLogger

logger = getLogger(__name__)

TTL_HOURS = 12


@singleton
class Resolver(AsyncResolver):
    @inject
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._original_dns = self._resolver
        self._alternate_resolver: AsyncResolver | None = None
        self.setAlternateResolver()
        config.subscribe(self.updateConfig)

    async def resolve(self, host: str, port: int = 0,
                      family: int = socket.AF_INET) -> List[Dict[str, Any]]:
        if host == self.config.get(Setting.DRIVE_HOST_NAME) and family == 0:
            if len(self.config.get(Setting.DRIVE_IPV4)) > 0:
                # return the specified drive address instead of looking it up.
                return [{
                    'family': 0,
                    'flags': socket.AddressInfo.AI_NUMERICHOST,
                    'port': port,
                    'proto': 0,
                    'host': self.config.get(Setting.DRIVE_IPV4),
                    'hostname': host
                }]
            elif self._alternate_resolver is not None:
                # if the drive address is not specified, use the alternate DNS servers.
                return await self._alternate_resolver.resolve(host, port, family)
        addresses = await super().resolve(host, port, family)
        return addresses

    def updateConfig(self):
        if self._alt_ns != self.config.get(Setting.ALTERNATE_DNS_SERVERS):
            self.setAlternateResolver()

    def setAlternateResolver(self):
        if len(self.config.get(Setting.ALTERNATE_DNS_SERVERS)) > 0:
            self._alternate_resolver = AsyncResolver(None, nameservers=self.config.get(Setting.ALTERNATE_DNS_SERVERS).split(","))
        else:
            self._alternate_resolver = None
        self._alt_ns = self.config.get(Setting.ALTERNATE_DNS_SERVERS)
