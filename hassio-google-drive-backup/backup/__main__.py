import os

import ptvsd
import platform
import asyncio
from aiorun import run
from injector import Injector

from backup.config import Config, Setting
from backup.module import MainModule, BaseModule
from backup.starter import Starter

from time import sleep
from sys import argv
from os.path import join, abspath
from .logger import getLogger

logger = getLogger(__name__)


async def main(config):
    await Injector([BaseModule(config), MainModule()]).get(Starter).startup()
    while True:
        await asyncio.sleep(1)


if __name__ == '__main__':
    if os.environ.get("DEBUGGER") == "true":
        # This is can be used to debug the addon when installaed as a local addon.
        logger.info("Starting debugger on port 3000")
        ptvsd.enable_attach(('0.0.0.0', 3000))

    config = Config()

    if len(argv) > 1:
        # Needed to load a different config for dev environments.
        config = Config.withFileOverrides(abspath(join(__file__, "../../dev/data", argv[1] + "_options.json")))
    else:
        config = Config.fromFile(Setting.CONFIG_FILE_PATH.default())

    if platform.system() == "Windows":
        # Needed for dev on windows machines
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main(config))
    else:
        run(main(config))
