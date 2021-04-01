from backup.config import Config, Setting, Startable
from backup.logger import getLogger
import sys
from injector import inject, singleton
logger = getLogger(__name__)


@singleton
class DebugServer(Startable):
    @inject
    def __init__(self, config: Config):
        self._config = config

    async def start(self):
        if self._config.get(Setting.DEBUGGER_PORT) is not None:
            if 'ptvsd' not in sys.modules:
                logger.error("Unable to start the debugger server because the ptvsd library is not installed")
            else:
                import ptvsd
                port = self._config.get(Setting.DEBUGGER_PORT)
                logger.info("Starting debugger on port {}".format(port))
                ptvsd.enable_attach(('0.0.0.0', port))
