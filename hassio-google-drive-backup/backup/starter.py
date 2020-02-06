from .config import Config
from .hasource import HaSource
from .drivesource import DriveSource
from .asyncserver import AsyncServer
from .coordinator import Coordinator
from .time import Time
from .logbase import LogBase
from .syncer import Scyncer
from .haupdater import HaUpdater
from .watcher import Watcher
from .debugworker import DebugWorker
from injector import inject, ClassAssistedBuilder, Injector


class Starter(LogBase):
    @inject
    def __init__(self, injector: Injector):
        self.injector = injector

    async def startup(self):
        self.injector.get(HaUpdater).start()
        self.injector.get(DebugWorker).start()

        # TODO: Relaoding settings (eg by web request) always possibly trigger reloading the server and reloading the resolver
        try:
            await self.injector.get(HaSource).init()
        except Exception:
            pass

        await self.injector.get(AsyncServer).run()

        triggers = [
            self.injector.get(Coordinator),
            self.injector.get(HaSource),
            self.injector.get(DriveSource),
            self.injector.get(Watcher),
            self.injector.get(AsyncServer)
        ]
        self.injector.get(ClassAssistedBuilder[Scyncer]).build(triggers=triggers).start()
