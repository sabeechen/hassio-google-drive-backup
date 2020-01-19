import os
from .config import Config
from .settings import Setting
from .exceptions import LowSpaceError
from .snapshots import Snapshot
from .logbase import LogBase
from .helpers import asSizeString
from .globalinfo import GlobalInfo
from typing import List


class Estimator(LogBase):
    def __init__(self, config: Config, global_info: GlobalInfo):
        super().__init__()
        self.config = config
        self._blocksUsed = 0
        self._blocksTotal = 1
        self._blockSize = 0
        self._global_info = global_info

    def refresh(self):
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

    def checkSpace(self, snapshots: List[Snapshot]):
        if not self.config.get(Setting.WARN_FOR_LOW_SPACE):
            # Don't check, just go
            return
        try:
            self._checkSpace(snapshots)
        except Exception as e:
            if isinstance(e, LowSpaceError):
                raise e
            # Just log the error and continue otherwise
            self.error("Encountered an error while trying to check disk space remaining: " + str(e))

    def _checkSpace(self, snapshots: List[Snapshot]):
        # get the most recent snapshot size
        space_needed = self.config.get(Setting.LOW_SPACE_THRESHOLD)
        snapshots.sort(key=lambda s: s.date(), reverse=True)
        for snapshot in snapshots:
            latest_size = snapshot.sizeInt()
            if latest_size > 1:
                # Bump the size a little to estimate organic growth.
                space_needed = latest_size * 1.1
                break

        if space_needed > self.getBytesFree() and not self._global_info.isSkipSpaceCheckOnce():
            raise LowSpaceError("{0}%".format(int(self.getUsagePercent())), asSizeString(self.getBytesFree()))

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
