import socket

import aiohttp
from aiohttp import ClientSession
from injector import Module, provider, singleton, multiprovider
from typing import List

from backup.config import Config, Startable
from backup.drive import DriveSource
from backup.ha import HaSource, HaUpdater, AddonStopper
from backup.model import SnapshotDestination, SnapshotSource, Scyncer
from backup.util import Resolver
from backup.model import Coordinator
from backup.worker import Trigger, Watcher
from backup.ui import UiServer, Restarter
from backup.logger import getLogger
from .time import AcceleratedTime, Time
from .debugworker import DebugWorker
from .tracing_session import TracingSession
logger = getLogger(__name__)


class BaseModule(Module):
    '''
    A module shared between tests and main
    '''
    def __init__(self, config: Config, override_dns=True):
        self._config = config
        self._override_dns = override_dns

    @provider
    @singleton
    def getConfig(self) -> Config:
        return self._config

    @multiprovider
    @singleton
    def getTriggers(self, coord: Coordinator, ha: HaSource, drive: DriveSource, watcher: Watcher, server: UiServer) -> List[Trigger]:
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
                      server: UiServer, restarter: Restarter, syncer: Scyncer, watcher: Watcher, stopper: AddonStopper) -> List[Startable]:
        # Order here matters, since its the order in which components of the addon are initialized.
        return [ha_updater, debugger, ha_source, server, restarter, syncer, watcher, stopper]

    @provider
    @singleton
    def getSession(self, resolver: Resolver) -> ClientSession:
        conn = None
        if self._override_dns:
            conn = aiohttp.TCPConnector(resolver=resolver, family=socket.AF_INET)
        return TracingSession(connector=conn)

    
    #@provider
    #@singleton
    #def getTime(self) -> Time:
    #    return AcceleratedTime(5000)
    #    return AcceleratedTime(1)


class MainModule(Module):
    # Reserved for future use
    pass
