from typing import Any, Dict

from backup.const import SOURCE_HA
from backup.exceptions import ensureKey
from backup.time import Time
from .backups import AbstractBackup
from backup.logger import getLogger
from backup.util import DataCache, KEY_I_MADE_THIS, KEY_IGNORE
from backup.config import Config, Setting

logger = getLogger(__name__)

HA_KEY_TEXT = "Home Assistant's backup metadata"


class HABackup(AbstractBackup):
    """
    Represents a Home Assistant backup stored locally in Home Assistant
    """

    def __init__(self, data: Dict[str, Any], data_cache: DataCache, config: Config, retained=False):
        super().__init__(
            name=ensureKey('name', data, HA_KEY_TEXT),
            slug=ensureKey('slug', data, HA_KEY_TEXT),
            date=Time.parse(ensureKey('date', data, HA_KEY_TEXT)),
            size=float(ensureKey("size", data, HA_KEY_TEXT)) * 1024 * 1024,
            source=SOURCE_HA,
            backupType=ensureKey('type', data, HA_KEY_TEXT),
            version=ensureKey('homeassistant', data, HA_KEY_TEXT),
            protected=ensureKey('protected', data, HA_KEY_TEXT),
            retained=retained,
            uploadable=True,
            details=data)
        self._data_cache = data_cache
        self._config = config

    def madeByTheAddon(self):
        return self._data_cache.backup(self.slug()).get(KEY_I_MADE_THIS, False)

    def ignore(self):
        override = self._data_cache.backup(self.slug()).get(KEY_IGNORE, None)
        if override is not None:
            return override
        if self.madeByTheAddon():
            return False
        if self._config.get(Setting.IGNORE_OTHER_BACKUPS):
            return True
        single_backup = len(self.details().get("addons", [])) + len(self.details().get("folders", [])) == 1
        if single_backup and self._config.get(Setting.IGNORE_UPGRADE_BACKUPS):
            return True
        return super().ignore()

    def __str__(self) -> str:
        return "<HA: {0} Name: {1} {2}>".format(self.slug(), self.name(), self.date().isoformat())

    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def __repr__(self) -> str:
        return self.__str__()
