from backup.config import Config, Setting
from injector import inject, singleton
import json
import os

KEY_SNPASHOTS = "snapshots"
KEY_I_MADE_THIS = "i_made_this"
KEY_PENDING = "pending"
KEY_CREATED = "created"


@singleton
class DataCache:
    @inject
    def __init__(self, config: Config):
        self._config = config
        self._data = {}
        self._dirty = {}
        self._load()

    def _load(self):
        if not os.path.isfile(self._config.get(Setting.DATA_CACHE_FILE_PATH)):
            self._data = {KEY_SNPASHOTS: {}}
            return
        with open(self._config.get(Setting.DATA_CACHE_FILE_PATH)) as f:
            self._data = json.load(f)

    def save(self, data=None):
        if data is None:
            data = self._date
        with open(self._config.get(Setting.RETAINED_FILE_PATH), "w") as f:
            data = json.dump(f, data, indent=4)
        self._dirty = False

    def update(self, slug, key, value):
        if slug not in self._data[KEY_SNPASHOTS]:
            self._data[KEY_SNPASHOTS][slug] = {}

        self._data[KEY_SNPASHOTS][slug][key] = value
        self._dirty = True

    def get(self, slug, property):
        if slug not in self._data[KEY_SNPASHOTS]:
            return
        return self._data[KEY_SNPASHOTS][slug].get(property, None)

    def saveIfDirty(self):
        if self._dirty:
            self.save()
