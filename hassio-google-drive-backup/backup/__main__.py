import os
import socket
import sys

import aiohttp
import ptvsd
from aiohttp import ClientSession
from aiorun import run
from injector import Injector, Module, provider, singleton

from .config import Config
from .drivesource import DriveSource
from .hasource import HaSource
from .logbase import LogBase
from .model import SnapshotDestination, SnapshotSource
from .resolver import SubvertingResolver
from .settings import _LOOKUP
from .starter import Starter


class MainModule(Module):
    @provider
    @singleton
    def getConfig(self) -> Config:
        config_path = None
        if len(sys.argv) > 1:
            config_path = "backup/dev/data/{0}_options.json".format(
                sys.argv[1])
        config = Config(config_path)

        if len(sys.argv) > 1:
            for key in list(config.config.keys()):
                config.override(_LOOKUP[key], config.config[key])
        return config

    @provider
    @singleton
    def getSession(self, resolver: SubvertingResolver) -> ClientSession:
        conn = aiohttp.TCPConnector(resolver=resolver, family=socket.AF_INET)
        return ClientSession(connector=conn)

    @provider
    @singleton
    def getDrive(self, drive: DriveSource) -> SnapshotDestination:
        return drive

    @provider
    @singleton
    def getHa(self, ha: HaSource) -> SnapshotSource:
        return ha


async def main():
    await Injector(MainModule()).get(Starter).startup()

if __name__ == '__main__':
    if os.environ.get("DEBUGGER") == "true":
        LogBase().info("Starting debugger on port 3000")
        ptvsd.enable_attach(('0.0.0.0', 3000))
    run(main())
