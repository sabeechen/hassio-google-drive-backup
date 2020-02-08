import sys
import aiohttp
import socket
import os
import ptvsd
from .starter import Starter
from aiorun import run
from .config import Config
from .settings import _LOOKUP
from .hasource import HaSource
from .drivesource import DriveSource
from .resolver import SubvertingResolver
from .model import SnapshotSource, SnapshotDestination
from injector import Module, provider, Injector, singleton
from aiohttp import ClientSession
from .logbase import LogBase


class MainModule(Module):
    @provider
    @singleton
    def getConfig(self) -> Config:
        config_path = None
        if len(sys.argv) > 1:
            config_path = "backup/dev/data/{0}_options.json".format(sys.argv[1])
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
