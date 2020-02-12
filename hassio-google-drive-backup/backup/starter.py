from injector import inject, singleton
from typing import List

from .config import Startable


@singleton
class Starter():
    @inject
    def __init__(self, startables: List[Startable]):
        self.startables = startables

    async def startup(self):
        for startable in self.startables:
            await startable.start()
