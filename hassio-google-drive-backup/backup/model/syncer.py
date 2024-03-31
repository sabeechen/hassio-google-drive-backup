from typing import List

from injector import inject, singleton

from .coordinator import Coordinator
from backup.time import Time
from backup.worker import Worker, Trigger
from backup.logger import getLogger
from backup.exceptions import PleaseWait
from backup.config import Config, Setting

logger = getLogger(__name__)


@singleton
class Scyncer(Worker):
    @inject
    def __init__(self, time: Time, coord: Coordinator, config: Config, triggers: List[Trigger]):
        self._config = config
        super().__init__("Sync Worker", self.checkforSync, time, self.getInterval)
        self.coord = coord
        self.triggers: List[Trigger] = triggers
        self._time = time

    async def checkforSync(self):
        try:
            doSync = False
            for trigger in self.triggers:
                if await trigger.check():
                    logger.debug("Sync requested by " + str(trigger.name()))
                    doSync = True
            if doSync:
                while self.coord.isSyncing():
                    await self._time.sleepAsync(3)
                await self.coord.sync()
        except PleaseWait:
            # Ignore this, since it means a sync already started (unavoidable race condition)
            pass

    def getInterval(self):
        return self._config.get(Setting.BACKUP_CHECK_INTERVAL_SECONDS)
