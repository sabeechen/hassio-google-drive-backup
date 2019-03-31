import os
from .helpers import formatException
from .config import Config
from typing import Optional, List

class Watcher(object):

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
            if self.config.verbose():
                print("Backup directory: {}".format(dirs))
            dirs.sort()
            if dirs == self.last_list:
                return False
            else:
                print("Backup directory has changed")
                self.last_list = dirs
                return True
        except Exception as e:
            print(formatException(e))
            return False

