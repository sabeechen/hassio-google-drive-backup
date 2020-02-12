import os

import ptvsd
from aiorun import run
from injector import Injector


from backup.logbase import LogBase
from backup.module import MainModule
from backup.starter import Starter


async def main():
    await Injector(MainModule()).get(Starter).startup()

if __name__ == '__main__':
    if os.environ.get("DEBUGGER") == "true":
        LogBase().info("Starting debugger on port 3000")
        ptvsd.enable_attach(('0.0.0.0', 3000))
    run(main())
