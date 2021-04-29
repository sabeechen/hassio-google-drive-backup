import platform
import asyncio
from aiorun import run
from injector import Injector

from backup.module import MainModule, BaseModule
from backup.starter import Starter


async def main():
    await Injector([BaseModule(), MainModule()]).get(Starter).start()
    while True:
        await asyncio.sleep(1)


if __name__ == '__main__':
    if platform.system() == "Windows":
        # Needed for dev on windows machines
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    else:
        run(main())
