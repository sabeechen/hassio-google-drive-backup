from typing import List

from injector import inject, singleton

from .coordinator import Coordinator
from ..time import Time
from ..worker import Worker, Trigger


@singleton
class Scyncer(Worker):
    @inject
    def __init__(self, time: Time, coord: Coordinator, triggers: List[Trigger]):
        super().__init__("Sync Worker", self.checkforSync, time, 0.5)
        self.coord = coord
        self.triggers: List[Trigger] = triggers

    async def checkforSync(self):
        doSync = False
        for trigger in self.triggers:
            if trigger.check():
                self.debug("Sync requested by " + str(trigger.name()))
                doSync = True
        if doSync:
            await self.coord.sync()
