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
async def test_bootstrap_requirements():
    # This just verifies we're able to satisfy starter's injector requirements.
    injector = Injector([BaseModule(Config()), MainModule()])
    injector.get(Starter)
