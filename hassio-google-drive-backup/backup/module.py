import socket
import sys

import aiohttp
from aiohttp import ClientSession
from injector import Module, provider, singleton

from .config import Config, _LOOKUP
from .drive import DriveSource
from .ha import HaSource
from .model import SnapshotDestination, SnapshotSource
from .util import Resolver


class MainModule(Module):
    @provider
    @singleton
    def getConfig(self) -> Config:
        config_path = None
        if len(sys.argv) > 1:
            config_path = "hassio-google-drive-backup/dev/data/{0}_options.json".format(
                sys.argv[1])
        config = Config(config_path)

        if len(sys.argv) > 1:
            for key in list(config.config.keys()):
                config.override(_LOOKUP[key], config.config[key])
        return config

    @provider
    @singleton
    def getSession(self, resolver: Resolver) -> ClientSession:
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
