from .backups import Backup
from .dummybackupsource import DummyBackupSource
from ..logger import getLogger

logger = getLogger(__name__)


class DummyBackup(Backup):
    def __init__(self, name, date, source, slug, size=0, ignore=False):
        super().__init__(None)
        self._size = size
        self._ignore = ignore
        self.addSource(DummyBackupSource(name, date, source, slug))

    def size(self):
        return self._size

    def ignore(self):
        return self._ignore
