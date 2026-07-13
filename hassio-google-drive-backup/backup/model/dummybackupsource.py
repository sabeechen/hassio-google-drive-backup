from .backups import AbstractBackup
from ..logger import getLogger

logger = getLogger(__name__)


class DummyBackupSource(AbstractBackup):
    def __init__(self, name, date, source, slug, retain=False):
        super().__init__(
            name=name,
            slug=slug,
            date=date,
            size=0,
            source=source,
            backupType="dummy",
            version="dummy_version",
            protected=True,
            retained=retain,
            uploadable=True,
            details={})
        self._created_by_automatic_settings = False

    def createdByAutomaticSettings(self):
        return self._created_by_automatic_settings

    def setCreatedByAutomaticSettings(self, value):
        self._created_by_automatic_settings = value
