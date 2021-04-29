from injector import inject, singleton
from typing import List

from .config import Startable, Config, Setting
from .logger import getLogger

logger = getLogger(__name__)


@singleton
class Starter(Startable):
    @inject
    def __init__(self, config: Config, startables: List[Startable]):
        self.startables = startables
        self.config = config

    async def start(self):
        logger.overrideLevel(self.config.get(Setting.CONSOLE_LOG_LEVEL), self.config.get(Setting.LOG_LEVEL))
        for startable in self.startables:
            await startable.start()

    async def stop(self):
        for startable in self.startables:
            await startable.stop()
