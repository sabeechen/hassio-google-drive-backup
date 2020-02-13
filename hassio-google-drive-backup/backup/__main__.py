import os

import ptvsd
from aiorun import run
from injector import Injector

from backup.config import Config
from backup.module import MainModule, BaseModule
from backup.starter import Starter
from sys import argv
from os.path import join, abspath
from .logger import getLogger

logger = getLogger(__name__)


async def main(config):
    await Injector([BaseModule(config), MainModule()]).get(Starter).startup()


if __name__ == '__main__':
    if os.environ.get("DEBUGGER") == "true":
        logger.info("Starting debugger on port 3000")
        ptvsd.enable_attach(('0.0.0.0', 3000))

    config = Config()

    if len(argv) > 1:
        config.loadOverrides(abspath(join(__file__, "../../dev/data", argv[1] + "_options.json")))
    else:
        config.loadDefaults()
    run(main(config))
