from datetime import timedelta
from enum import Enum, unique
from backup.config import Config, Setting, VERSION, Version
from backup.file import JsonFileSaver
from backup.const import NECESSARY_OLD_BACKUP_PLURAL_NAME
from injector import inject, singleton
from ..time import Time
from typing import Dict
import json
import os

KEY_I_MADE_THIS = "i_made_this"
KEY_PENDING = "pending"
KEY_CREATED = "created"
KEY_IGNORE = "ignore"
KEY_LAST_SEEN = "last_seen"
KEY_NAME = "name"
KEY_LAST_VERSION = "last_verison"
KEY_UPGRADES = "upgrades"
KEY_FLAGS = "flags"
KEY_NOTE = "note"

CACHE_EXPIRATION_DAYS = 30

VERSION_DEFUALT_IGNORE_UPGRADES = Version.parse("0.108.2")


@unique
class UpgradeFlags(Enum):
    NOTIFIED_ABOUT_BACKUP_RENAME = "notified_backup_rename"
    NOTIFIED_ABOUT_IGNORED_BACKUPS = "notified_ignored_backups"
    NOTIFIED_ABOUT_OOB_FLOW = "notified_about_oob_flow"
    TESTING_FLAG = "testing_flag"


@singleton
class DataCache:
    @inject
    def __init__(self, config: Config, time: Time):
        self._config = config
        self._data = {}
        self._dirty = {}
        self._time = time
        self._last_version = Version.default()
        self._first_version = Version.default()
        self._flags = set()
        self._load()

    def _load(self):
        path = self._config.get(Setting.DATA_CACHE_FILE_PATH)
        if not JsonFileSaver.exists(path):
            self._data = {NECESSARY_OLD_BACKUP_PLURAL_NAME: {}}
        else:
            self._data = JsonFileSaver.read(path)

        # Check for an upgrade.
        if KEY_LAST_VERSION in self._data:
            self._last_version = Version.parse(self._data[KEY_LAST_VERSION])
        if self.previousVersion != self.currentVersion:
            # add an upgrade marker
            if KEY_UPGRADES not in self._data:
                self._data[KEY_UPGRADES] = []
            self._data[KEY_UPGRADES].append({
                'prev_version': str(self.previousVersion),
                'new_version': str(self.currentVersion),
                'date': self._time.now().isoformat()
            })
            self._data[KEY_LAST_VERSION] = str(self.currentVersion)
            self.makeDirty()
        if KEY_UPGRADES not in self._data or len(self._data[KEY_UPGRADES]) == 0:
            self._first_version = self.currentVersion
        else:
            self._first_version = Version.parse(self._data[KEY_UPGRADES][0]['new_version'])

        if self._config.isExplicit(Setting.IGNORE_OTHER_BACKUPS) or self._config.isExplicit(Setting.IGNORE_UPGRADE_BACKUPS):
            self.addFlag(UpgradeFlags.NOTIFIED_ABOUT_IGNORED_BACKUPS)

        if self.notifyForIgnoreUpgrades:
            self._config.useLegacyIgnoredBehavior(True)

        self.saveIfDirty()

    def save(self, data=None):
        if data is None:
            data = self._data
        path = self._config.get(Setting.DATA_CACHE_FILE_PATH)
        JsonFileSaver.write(path, data)
        self._dirty = False

    def makeDirty(self):
        self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def backups(self) -> Dict[str, Dict[str, str]]:
        if NECESSARY_OLD_BACKUP_PLURAL_NAME not in self._data:
            self._data[NECESSARY_OLD_BACKUP_PLURAL_NAME] = {}
        return self._data[NECESSARY_OLD_BACKUP_PLURAL_NAME]

    def backup(self, slug) -> Dict[str, str]:
        if slug not in self.backups:
            self.backups[slug] = {}
        return self.backups[slug]

    def saveIfDirty(self):
        if self._dirty:
            # See if we need to remove any old entries
            for slug in list(self.backups.keys()):
                data = self.backups[slug].get(KEY_LAST_SEEN)
                if data is not None and self._time.now() > self._time.parse(data) + timedelta(days=CACHE_EXPIRATION_DAYS):
                    del self.backups[slug]
            self.save()

    @property
    def previousVersion(self):
        return self._last_version

    @property
    def firstVersion(self):
        return self._first_version

    @property
    def currentVersion(self):
        return Version.parse(VERSION)

    @property
    def notifyForIgnoreUpgrades(self):
        return self.firstVersion < VERSION_DEFUALT_IGNORE_UPGRADES and not self.checkFlag(UpgradeFlags.NOTIFIED_ABOUT_IGNORED_BACKUPS) and not self._config.isExplicit(Setting.IGNORE_OTHER_BACKUPS) and not self._config.isExplicit(Setting.IGNORE_UPGRADE_BACKUPS)

    def checkFlag(self, flag: UpgradeFlags):
        return flag.value in self._data.get(KEY_FLAGS, [])

    def TESTS_ONLY_clearFlags(self):
        self._data[KEY_FLAGS] = []

    def addFlag(self, flag: UpgradeFlags):
        all_flags = set(self._data.get(KEY_FLAGS, []))
        all_flags.add(flag.value)
        self._data[KEY_FLAGS] = list(all_flags)
        self.makeDirty()

    def getUpgradeTime(self, version: Version):
        for upgrade in self._data[KEY_UPGRADES]:
            if Version.parse(upgrade['new_version']) >= version:
                return self._time.parse(upgrade['date'])
        return self._time.now()
