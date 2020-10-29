import pytest
from backup.module import MainModule, BaseModule
from backup.starter import Starter
from injector import Injector
from backup.ha import HaUpdater, HaSource, AddonStopper
from backup.worker import Watcher
from backup.debugworker import DebugWorker
from backup.config import Config
from backup.ui import UiServer
from backup.model import Scyncer


@pytest.mark.asyncio
async def test_bootstarp_requirements():
    # This just verifies we're able to satisfy starter's injector requirements.
    injector = Injector([BaseModule(Config()), MainModule()])
    injector.get(Starter)


@pytest.mark.asyncio
async def test_start_work(injector, server):
    starter = injector.get(Starter)
    await starter.startup()

    # it would be nicer if Startable implemented a "isStarted" method instead of this hodge-podge
    assert injector.get(HaUpdater).isRunning()
    assert injector.get(DebugWorker).isRunning()
    assert injector.get(Scyncer).isRunning()
    assert injector.get(HaSource).isInitialized()
    assert injector.get(UiServer).running
    assert injector.get(Watcher).isStarted()
    assert injector.get(AddonStopper).isRunning()

    # Config should have Restarter and Resolver subscribed
    assert len(injector.get(Config)._subscriptions) == 2
