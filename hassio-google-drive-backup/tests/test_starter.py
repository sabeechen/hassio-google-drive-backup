import pytest
import os
from backup.module import MainModule, BaseModule
from backup.starter import Starter
from backup.config import Config, Setting
from injector import Injector


@pytest.mark.asyncio
async def test_bootstrap_requirements(cleandir):
    # This just verifies we're able to satisfy starter's injector requirements.
    injector = Injector([BaseModule(), MainModule()])
    config = injector.get(Config)
    config.override(Setting.DATA_CACHE_FILE_PATH, os.path.join(cleandir, "data_cache.json"))
    injector.get(Starter)


@pytest.mark.asyncio
async def test_start_and_stop(injector):
    starter = injector.get(Starter)
    await starter.start()
    await starter.stop()
