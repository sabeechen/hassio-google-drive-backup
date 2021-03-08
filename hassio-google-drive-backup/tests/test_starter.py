import pytest
from backup.module import MainModule, BaseModule
from backup.starter import Starter
from injector import Injector
from backup.config import Config


@pytest.mark.asyncio
async def test_bootstrap_requirements():
    # This just verifies we're able to satisfy starter's injector requirements.
    injector = Injector([BaseModule(Config()), MainModule()])
    injector.get(Starter)
