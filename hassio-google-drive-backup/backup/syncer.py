from .worker import Worker
from .time import Time
from .trigger import Trigger
from .coordinator import Coordinator
from typing import List


class Scyncer(Worker):
    def __init__(self, time: Time, coord: Coordinator, triggers: List[Trigger]):
        super().__init__("Sync Worker", self.checkforSync, time, 0.5)
        self.coord = coord
        self.triggers: List[Trigger] = triggers

    def checkforSync(self):
        doSync = False
        for trigger in self.triggers:
            if trigger.check():
                self.debug("Sync requested by " + str(trigger.name()))
                doSync = True
        if doSync:
            self.coord.sync()
