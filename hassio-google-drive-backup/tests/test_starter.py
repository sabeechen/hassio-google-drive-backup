import pytest
from backup.module import MainModule, BaseModule
from backup.starter import Starter
from injector import Injector


@pytest.mark.asyncio
async def test_bootstrap_requirements():
    # This just verifies we're able to satisfy starter's injector requirements.
    injector = Injector([BaseModule(), MainModule()])
    injector.get(Starter)


@pytest.mark.asyncio
async def test_start_and_stop(injector):
    starter = injector.get(Starter)
    await starter.start()
    await starter.stop()
