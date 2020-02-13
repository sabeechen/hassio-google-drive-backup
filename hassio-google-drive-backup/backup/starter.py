from injector import inject, singleton
from typing import List

from .config import Startable
from .logger import getLogger

logger = getLogger(__name__)


@singleton
class Starter():
    @inject
    def __init__(self, startables: List[Startable]):
        self.startables = startables

    async def startup(self):
        for startable in self.startables:
            await startable.start()
