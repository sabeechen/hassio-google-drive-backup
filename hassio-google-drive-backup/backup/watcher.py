import os
from .helpers import formatException
from .config import Config
from .logbase import LogBase
from typing import Optional, List


class Watcher(LogBase):
    def __init__(self, config: Config):
        self.last_list: Optional[List[str]] = None
        self.config: Config = config

    def haveFilesChanged(self) -> bool:
        try:
            if self.last_list is None:
                self.last_list = os.listdir(self.config.backupDirectory())
                self.last_list.sort()
                return False
            dirs = os.listdir(self.config.backupDirectory())
            dirs.sort()
            if dirs == self.last_list:
                return False
            else:
                self.info("Backup directory has changed")
                self.last_list = dirs
                return True
        except Exception as e:
            self.error(formatException(e))
            return False
