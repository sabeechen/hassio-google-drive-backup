import socket
import sys
import aiohttp
import os
from aiohttp import ClientSession
from injector import Module, provider, singleton, multiprovider
from typing import List

from backup.config import Config, Startable, Setting
from backup.drive import DriveSource
from backup.ha import HaSource, HaUpdater, AddonStopper
from backup.model import BackupDestination, BackupSource, Scyncer
from backup.util import Resolver
from backup.model import Coordinator
from backup.worker import Trigger, Watcher
from backup.ui import UiServer, Restarter
from backup.logger import getLogger
from backup.debug import DebugServer
from .debugworker import DebugWorker
from .tracing_session import TracingSession
logger = getLogger(__name__)


class BaseModule(Module):
    '''
    A module shared between tests and main
    '''
    def __init__(self, override_dns=True):
        self._override_dns = override_dns

    @multiprovider
    @singleton
    def getTriggers(self, coord: Coordinator, ha: HaSource, drive: DriveSource, watcher: Watcher, server: UiServer) -> List[Trigger]:
        return [coord, ha, drive, watcher, server]

    @provider
    @singleton
    def getDrive(self, drive: DriveSource) -> BackupDestination:
        return drive

    @provider
    @singleton
    def getHa(self, ha: HaSource) -> BackupSource:
        return ha

    @multiprovider
    @singleton
    def getStartables(self, debug_server: DebugServer, ha_updater: HaUpdater, debugger: DebugWorker, ha_source: HaSource,
                      server: UiServer, restarter: Restarter, syncer: Scyncer, watcher: Watcher, stopper: AddonStopper) -> List[Startable]:
        # Order here matters, since its the order in which components of the addon are initialized.
        return [debug_server, ha_updater, debugger, ha_source, server, restarter, syncer, watcher, stopper]

    @provider
    @singleton
    def getSession(self, resolver: Resolver) -> ClientSession:
        conn = None
        if self._override_dns:
            conn = aiohttp.TCPConnector(resolver=resolver, family=socket.AF_INET)
        return TracingSession(connector=conn)


class MainModule(Module):
    @provider
    @singleton
    def getConfig(self) -> Config:
        alt_config = None
        index = 1
        for arg in sys.argv[1:]:
            if arg == "--config":
                alt_config = sys.argv[index + 1]
                break
            index += 1

        if alt_config:
            config = Config.withFileOverrides(alt_config)
        elif "PYTEST_CURRENT_TEST" in os.environ:
            config = Config()
        else:
            config = Config.fromFile(Setting.CONFIG_FILE_PATH.default())
        logger.overrideLevel(config.get(Setting.CONSOLE_LOG_LEVEL), config.get(Setting.LOG_LEVEL))
        return config
