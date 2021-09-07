from .model import CreateOptions, BackupDestination
from .backups import Backup
from .dummybackupsource import DummyBackupSource
from typing import Dict
from io import IOBase
from ..ha import BackupName
from ..logger import getLogger

logger = getLogger(__name__)


class SimulatedSource(BackupDestination):
    def __init__(self, name):
        self._name = name
        self.current: Dict[str, DummyBackupSource] = {}
        self.saved = []
        self.deleted = []
        self.created = []
        self._enabled = True
        self._upload = True
        self.index = 0
        self.max = 0
        self.backup_name = BackupName()
        self.host_info = {}
        self.backup_type = "Full"
        self.working = False
        self.needConfig = None

    def setEnabled(self, value):
        self._enabled = value
        return self

    def needsConfiguration(self) -> bool:
        if self.needConfig is not None:
            return self.needConfig
        return super().needsConfiguration()

    def setNeedsConfiguration(self, value: bool):
        self.needConfig = value

    def setUpload(self, value):
        self._upload = value
        return self

    def upload(self):
        return self._upload

    def setMax(self, count):
        self.max = count
        return self

    def isWorking(self):
        return self.working

    def setIsWorking(self, value):
        self.working = value

    def maxCount(self) -> None:
        return self.max

    def insert(self, name, date, slug=None, retain=False):
        if slug is None:
            slug = name
        new_backup = DummyBackupSource(
            name,
            date,
            self._name,
            slug)
        self.current[new_backup.slug()] = new_backup
        return new_backup

    def name(self) -> str:
        return self._name

    def enabled(self) -> bool:
        return self._enabled

    def nameSetup(self, type, host_info):
        self.backup_type = type
        self.host_info = host_info

    async def create(self, options: CreateOptions) -> DummyBackupSource:
        assert self.enabled
        new_backup = DummyBackupSource(
            self.backup_name.resolve(
                self.backup_type, options.name_template, options.when, self.host_info),
            options.when,
            self._name,
            "{0}slug{1}".format(self._name, self.index))
        self.index += 1
        self.current[new_backup.slug()] = new_backup
        self.created.append(new_backup)
        return new_backup

    async def get(self) -> Dict[str, DummyBackupSource]:
        assert self.enabled
        return self.current

    async def delete(self, backup: Backup):
        assert self.enabled
        assert backup.getSource(self._name) is not None
        assert backup.getSource(self._name).source() is self._name
        assert backup.slug() in self.current
        slug = backup.slug()
        self.deleted.append(backup.getSource(self._name))
        backup.removeSource(self._name)
        del self.current[slug]

    async def save(self, backup: Backup, bytes: IOBase = None) -> DummyBackupSource:
        assert self.enabled
        assert backup.slug() not in self.current
        new_backup = DummyBackupSource(
            backup.name(), backup.date(), self._name, backup.slug())
        backup.addSource(new_backup)
        self.current[new_backup.slug()] = new_backup
        self.saved.append(new_backup)
        return new_backup

    async def read(self, backup: DummyBackupSource) -> IOBase:
        assert self.enabled
        return None

    async def retain(self, backup: DummyBackupSource, retain: bool) -> None:
        assert self.enabled
        backup.getSource(self.name()).setRetained(retain)
