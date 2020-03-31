import aiorun
from .server import Server
from backup.config import Config
from backup.module import BaseModule
from injector import Injector


async def main():
    config = Config.fromEnvironment()
    module = BaseModule(config, override_dns=False)
    injector = Injector(module)
    await injector.get(Server).start()


if __name__ == '__main__':
    print("Starting")
    aiorun.run(main())
