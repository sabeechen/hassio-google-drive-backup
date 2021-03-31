import aiorun
from .server import Server
from backup.config import Config
from backup.module import BaseModule
from injector import Injector
from injector import provider, singleton


class ServerModule(BaseModule):
    def __init__(self):
        super().__init__(override_dns=False)

    @provider
    @singleton
    def getConfig(self) -> Config:
        return Config.fromEnvironment()


async def main():
    module = ServerModule()
    injector = Injector(module)
    await injector.get(Server).start()


if __name__ == '__main__':
    print("Starting")
    aiorun.run(main())
