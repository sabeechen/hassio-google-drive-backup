import datetime

from typing import Dict, List, Tuple

class BackupScheme(object):
    def __init__(self, partitions: List[datetime.datetime]):
        self.partitions = None

    def getOldest(self):
        pass
