from ..logger import getLogger

logger = getLogger(__name__)


class Startable():
    async def start(self):
        pass

    async def stop(self):
        pass
