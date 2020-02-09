from injector import ClassAssistedBuilder, Injector, inject

from .asyncserver import AsyncServer
from .coordinator import Coordinator
from .debugworker import DebugWorker
from .drivesource import DriveSource
from .hasource import HaSource
from .haupdater import HaUpdater
from .logbase import LogBase
from .syncer import Scyncer
from .watcher import Watcher


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
        self.injector.get(ClassAssistedBuilder[Scyncer]).build(
            triggers=triggers).start()
