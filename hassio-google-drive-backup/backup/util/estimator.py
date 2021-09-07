import os
import platform

from injector import inject, singleton

from ..config import Config, Setting
from ..exceptions import LowSpaceError
from .globalinfo import GlobalInfo
from ..logger import getLogger

logger = getLogger(__name__)

SIZE_SI = ["B", "kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]


@singleton
class Estimator():
    @inject
    def __init__(self, config: Config, global_info: GlobalInfo):
        super().__init__()
        self.config = config
        self._blocksUsed = 0
        self._blocksTotal = 1
        self._blockSize = 0
        self._global_info = global_info

    def refresh(self):
        if platform.system() == "Windows":
            # Unsupported on windows
            return self
        # This roughly matches the results you get by running "df",
        # except its a bit more conservative, which isn't necessarily
        # correct, but we're aiming for ballpark numbers here so it
        # should be ok.
        stats = os.statvfs(self.config.get(Setting.BACKUP_DIRECTORY_PATH))
        total = stats.f_blocks
        available = stats.f_bavail
        availableToRoot = stats.f_bfree
        self._blocksUsed = total - availableToRoot
        self._blocksTotal = self._blocksUsed + available
        self._blockSize = stats.f_frsize
        return self

    def checkSpace(self, backups):
        if platform.system() == "Windows":
            # Unsupported on windows
            return
        if not self.config.get(Setting.WARN_FOR_LOW_SPACE):
            # Don't check, just go
            return
        try:
            self._checkSpace(backups)
        except Exception as e:
            if isinstance(e, LowSpaceError):
                raise e
            # Just log the error and continue otherwise
            logger.error(
                "Encountered an error while trying to check disk space remaining: " + str(e))

    def _checkSpace(self, backups):
        # get the most recent backup size
        space_needed = self.config.get(Setting.LOW_SPACE_THRESHOLD)
        backups.sort(key=lambda s: s.date(), reverse=True)
        for backup in backups:
            latest_size = backup.sizeInt()
            if latest_size > 1:
                # Bump the size a little to estimate organic growth.
                space_needed = latest_size * 1.1
                break

        if space_needed > self.getBytesFree() and not self._global_info.isSkipSpaceCheckOnce():
            raise LowSpaceError("{0}%".format(
                int(self.getUsagePercent())), Estimator.asSizeString(self.getBytesFree()))

    def getUsagePercent(self):
        return 100.0 * float(self.getBlocksUsed()) / float(self.getBlocksTotal())

    def getBlocksUsed(self):
        return self._blocksUsed

    def getBlocksTotal(self):
        return self._blocksTotal

    def getBlocksFree(self):
        return self.getBlocksTotal() - self.getBlocksUsed()

    def getBytesFree(self):
        return self._blockSize * self.getBlocksFree()

    def getBytesUsed(self):
        return self._blockSize * self.getBlocksUsed()

    def getBytesTotal(self):
        return self._blockSize * self.getBlocksTotal()

    @classmethod
    def asSizeString(cls, size):
        current = float(size)
        for id in SIZE_SI:
            if current < 1024:
                return "{0} {1}".format(round(current, 1), id)
            current /= 1024
        return "Beyond mortal comprehension"
