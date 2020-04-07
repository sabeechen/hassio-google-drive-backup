from .uiserver import UiServer
from ..config import Config, Startable
from asyncio import create_task, Event
from injector import inject, singleton
from ..logger import getLogger

logger = getLogger(__name__)


@singleton
class Restarter(Startable):
    @inject
    def __init__(self, server: UiServer, config: Config):
        self._server = server
        self._config = config
        self._old_options = config.getServerOptions()
        self._restarted = Event()

    async def start(self):
        self._config.subscribe(self.trigger)

    async def check(self):
        if self._old_options == self._config.getServerOptions():
            # no restart is necessary because the server didn't change
            return
        self._old_options = self._config.getServerOptions()
        try:
            # Restart the server
            logger.info("Restarting Web-UI server")
            await self._server.run()
            self._restarted.set()
        except Exception as e:
            logger.error("Problem while restarting the Web-UI server " + logger.formatException(e))

    def trigger(self):
        create_task(self.check(), name="Web-UI Restarter")

    async def waitForRestart(self):
        await self._restarted.wait()
        self._restarted.clear()
