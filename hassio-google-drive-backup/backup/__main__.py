import os

import platform
import asyncio
from aiorun import run
from injector import Injector

from .logger import getLogger
from backup.config import Config, Setting
from backup.module import MainModule, BaseModule
from backup.starter import Starter

from sys import argv
from os.path import join, abspath

logger = getLogger(__name__)


async def main(config):
    await Injector([BaseModule(config), MainModule()]).get(Starter).startup()
    while True:
        await asyncio.sleep(1)


if __name__ == '__main__':
    config = Config()

    if len(argv) > 1:
        # Needed to load a different config for dev environments.
        config = Config.withFileOverrides(abspath(join(__file__, "../../dev/data", argv[1] + "_options.json")))
    else:
        config = Config.fromFile(Setting.CONFIG_FILE_PATH.default())
    
    logger.overrideLevel(config.get(Setting.CONSOLE_LOG_LEVEL), config.get(Setting.LOG_LEVEL))
    # if config.get(Setting.DEBUGGER_PORT) is not None:
    #    port = config.get(Setting.DEBUGGER_PORT)
    #    logger.info("Starting debugger on port {}".format(port))
    #    ptvsd.enable_attach(('0.0.0.0', port))

    if platform.system() == "Windows":
        # Needed for dev on windows machines
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main(config))
    else:
        run(main(config))
