from .backups import Backup
from .dummybackupsource import DummyBackupSource
from ..logger import getLogger

logger = getLogger(__name__)


class DummyBackup(Backup):
    def __init__(self, name, date, source, slug, size=0, ignore=False, note=None):
        super().__init__(None)
        self._size = size
        self._ignore = ignore
        self._note = note
        self.addSource(DummyBackupSource(name, date, source, slug))

    def size(self):
        return self._size

    def ignore(self):
        return self._ignore

    def note(self):
        if self._note is not None:
            return self._note
        else:
            return super().note()
