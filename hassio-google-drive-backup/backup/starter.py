from injector import ClassAssistedBuilder, Injector, inject

from .server import AsyncServer, Restarter
from .model import Coordinator, Scyncer
from .worker import DebugWorker, Watcher
from .drive import DriveSource
from .ha import HaSource, HaUpdater
from .logbase import LogBase


class Starter(LogBase):
    @inject
    def __init__(self, injector: Injector):
        self.injector = injector

    async def startup(self):
        self.injector.get(HaUpdater).start()
        self.injector.get(DebugWorker).start()

        try:
            await self.injector.get(HaSource).init()
        except Exception:
            pass

        await self.injector.get(AsyncServer).run()
        self.injector.get(Restarter).init()

        triggers = [
            self.injector.get(Coordinator),
            self.injector.get(HaSource),
            self.injector.get(DriveSource),
            self.injector.get(Watcher),
            self.injector.get(AsyncServer)
        ]
        self.injector.get(ClassAssistedBuilder[Scyncer]).build(
            triggers=triggers).start()
