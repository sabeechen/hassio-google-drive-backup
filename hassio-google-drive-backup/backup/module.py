import socket

import aiohttp
from aiohttp import ClientSession
from injector import Module, provider, singleton, multiprovider
from typing import List

from .config import Config, Startable
from .drive import DriveSource
from .ha import HaSource, HaUpdater
from .model import SnapshotDestination, SnapshotSource, Scyncer
from .util import Resolver
from .model import Coordinator
from .worker import Trigger, Watcher, DebugWorker
from .server import AsyncServer, Restarter
from .logger import getLogger

logger = getLogger(__name__)


class BaseModule(Module):
    '''
    A module shared between tests and main
    '''
    def __init__(self, config: Config):
        self._config = config

    @provider
    @singleton
    def getConfig(self) -> Config:
        return self._config

    @multiprovider
    @singleton
    def getTriggers(self, coord: Coordinator, ha: HaSource, drive: DriveSource, watcher: Watcher, server: AsyncServer) -> List[Trigger]:
        return [coord, ha, drive, watcher, server]

    @provider
    @singleton
    def getDrive(self, drive: DriveSource) -> SnapshotDestination:
        return drive

    @provider
    @singleton
    def getHa(self, ha: HaSource) -> SnapshotSource:
        return ha

    @multiprovider
    @singleton
    def getStartables(self, ha_updater: HaUpdater, debugger: DebugWorker, ha_source: HaSource,
                      server: AsyncServer, restarter: Restarter, syncer: Scyncer, watcher: Watcher) -> List[Startable]:
        # Order here matters, since its the order in which components of the addon are initialized.
        return [ha_updater, debugger, ha_source, server, restarter, syncer, watcher]

    @provider
    @singleton
    def getSession(self, resolver: Resolver) -> ClientSession:
        conn = aiohttp.TCPConnector(resolver=resolver, family=socket.AF_INET)
        return ClientSession(connector=conn)


class MainModule(Module):
    # Reserved for future use
    pass
