import json
import os
import os.path
import uuid
from typing import Any, Dict, List, Optional
from yarl import URL

from .settings import _LOOKUP, Setting, _VALIDATORS
from ..logger import getLogger

logger = getLogger(__name__)

ALWAYS_KEEP = {
    Setting.DAYS_BETWEEN_BACKUPS,
    Setting.MAX_BACKUPS_IN_HA,
    Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE,
}

KEEP_DEFAULT = {
    Setting.SEND_ERROR_REPORTS
}

# these are the options that should trigger a restart of the server
SERVER_OPTIONS = {
    Setting.USE_SSL,
    Setting.REQUIRE_LOGIN,
    Setting.CERTFILE,
    Setting.KEYFILE,
    Setting.EXPOSE_EXTRA_SERVER
}

NON_UI_SETTING = {
    Setting.SUPERVISOR_URL,
    Setting.TOKEN_SERVER_HOSTS,
    Setting.DRIVE_AUTHORIZE_URL,
    Setting.DRIVE_DEVICE_CODE_URL,
    Setting.DEFAULT_DRIVE_CLIENT_ID,
    Setting.NEW_BACKUP_TIMEOUT_SECONDS,
    Setting.LOG_LEVEL,
    Setting.CONSOLE_LOG_LEVEL
}

UPGRADE_OPTIONS = {
    Setting.DEPRECTAED_MAX_BACKUPS_IN_HA: Setting.MAX_BACKUPS_IN_HA,
    Setting.DEPRECTAED_MAX_BACKUPS_IN_GOOGLE_DRIVE: Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE,
    Setting.DEPRECATED_DAYS_BETWEEN_BACKUPS: Setting.DAYS_BETWEEN_BACKUPS,
    Setting.DEPRECTAED_IGNORE_OTHER_BACKUPS: Setting.IGNORE_OTHER_BACKUPS,
    Setting.DEPRECTAED_IGNORE_UPGRADE_BACKUPS: Setting.IGNORE_UPGRADE_BACKUPS,
    Setting.DEPRECTAED_DELETE_BEFORE_NEW_BACKUP: Setting.DELETE_BEFORE_NEW_BACKUP,
    Setting.DEPRECTAED_BACKUP_NAME: Setting.BACKUP_NAME,
    Setting.DEPRECTAED_BACKUP_TIME_OF_DAY: Setting.BACKUP_TIME_OF_DAY,
    Setting.DEPRECTAED_SPECIFY_BACKUP_FOLDER: Setting.SPECIFY_BACKUP_FOLDER,
    Setting.DEPRECTAED_NOTIFY_FOR_STALE_BACKUPS: Setting.NOTIFY_FOR_STALE_BACKUPS,
    Setting.DEPRECTAED_ENABLE_BACKUP_STALE_SENSOR: Setting.ENABLE_BACKUP_STALE_SENSOR,
    Setting.DEPRECTAED_ENABLE_BACKUP_STATE_SENSOR: Setting.ENABLE_BACKUP_STATE_SENSOR,
    Setting.DEPRECATED_BACKUP_PASSWORD: Setting.BACKUP_PASSWORD
}

EMPTY_IS_DEFAULT = {
    Setting.ACCENT_COLOR,
    Setting.BACKGROUND_COLOR,
}


class GenConfig():
    def __init__(self, days=0, weeks=0, months=0, years=0, day_of_week='mon', day_of_month=1, day_of_year=1, aggressive=False):
        self.days = days
        self.weeks = weeks
        self.months = months
        self.years = years
        self.day_of_week = day_of_week
        self.day_of_month = day_of_month
        self.day_of_year = day_of_year
        self.aggressive = aggressive
        self._config_was_upgraded = False

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, GenConfig):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __hash__(self):
        """Overrides the default implementation"""
        return hash(tuple(sorted(self.__dict__.items())))


class Config():
    @classmethod
    def fromFile(cls, config_path):
        with open(config_path, "r") as f:
            data = json.load(f)
        return Config(data)

    @classmethod
    def withOverrides(cls, overrides):
        config = Config()
        for key in overrides.keys():
            config.override(key, overrides[key])
        return config

    @classmethod
    def withFileOverrides(cls, override_path):
        with open(override_path, "r") as f:
            data = json.load(f)
        overrides = {}
        for key in data.keys():
            overrides[_LOOKUP[key]] = data[key]
        return Config.withOverrides(overrides)

    @classmethod
    def fromEnvironment(cls):
        config = {}
        for key in os.environ:
            if key in _LOOKUP:
                config[_LOOKUP[key]] = _VALIDATORS[_LOOKUP[key]].validate(os.environ[key])
            elif str.lower(key) in _LOOKUP:
                config[_LOOKUP[str.lower(key)]] = _VALIDATORS[_LOOKUP[str.lower(key)]].validate(os.environ[key])
        return Config(config)

    def __init__(self, data=None):
        self.overrides = {}
        if data is None:
            self.config = {}
        else:
            self.config = data
        self._subscriptions = []
        self._clientIdentifier = None
        self.retained = self._loadRetained()
        self._gen_config_cache = self.getGenerationalConfig()

        # Tracks when hosts have been seen to be offline to retry on different hosts.
        self._commFailure = {}

    def getConfigFor(self, options):
        new_config = Config()
        new_config.overrides = self.overrides.copy()
        new_config.update(options)
        return new_config

    def validateUpdate(self, additions):
        new_config = self.config.copy()
        new_config.update(additions)
        validated, upgraded = self.validate(new_config)
        return validated

    def validate(self, new_config) -> Dict[str, Any]:
        final_config = {}

        upgraded = False
        # validate each item
        for key in new_config:
            if type(key) == str:
                if key not in _LOOKUP:
                    # its not in the schema, just ignore it
                    continue
                setting = _LOOKUP[key]
            else:
                setting = key

            value = setting.validator().validate(new_config[key])
            if setting in UPGRADE_OPTIONS:
                upgraded = True
            if isinstance(value, str) and len(value) == 0 and setting in EMPTY_IS_DEFAULT:
                value = setting.default()
            if value is not None and (setting in KEEP_DEFAULT or value != setting.default()):
                if setting in UPGRADE_OPTIONS and (UPGRADE_OPTIONS[setting] not in new_config or new_config[UPGRADE_OPTIONS[setting]] == UPGRADE_OPTIONS[setting].default()):
                    upgraded = True
                    final_config[UPGRADE_OPTIONS[setting]] = value
                elif setting not in UPGRADE_OPTIONS:
                    final_config[setting] = value

        if upgraded:
            final_config[Setting.CALL_BACKUP_SNAPSHOT] = True

        # add in non-ui settings
        for setting in NON_UI_SETTING:
            if self.get(setting) != setting.default() and not (setting in new_config or setting.key in new_config) and setting not in self.overrides:
                final_config[setting] = self.get(setting)

        # add defaults
        for key in ALWAYS_KEEP:
            if key not in final_config:
                final_config[key] = key.default()

        if not final_config.get(Setting.USE_SSL, False):
            for key in [Setting.CERTFILE, Setting.KEYFILE]:
                if key in final_config:
                    del final_config[key]

        return final_config, upgraded

    def update(self, new_config):
        validated, upgraded = self.validate(new_config)
        self._config_was_upgraded = upgraded
        self.config = validated
        self._gen_config_cache = self.getGenerationalConfig()
        for sub in self._subscriptions:
            sub()

    def getServerOptions(self):
        ret = {}
        for setting in SERVER_OPTIONS:
            ret[setting] = self.get(setting)
        return ret

    def subscribe(self, func):
        self._subscriptions.append(func)

    def clientIdentifier(self) -> str:
        if self._clientIdentifier is None:
            try:
                if os.path.exists(self.get(Setting.ID_FILE_PATH)):
                    with open(self.get(Setting.ID_FILE_PATH)) as f:
                        self._clientIdentifier = json.load(f)['id']
                else:
                    self._clientIdentifier = str(uuid.uuid4())
                    with open(self.get(Setting.ID_FILE_PATH), "w") as f:
                        json.dump({'id': self._clientIdentifier}, f)
            except Exception:
                self._clientIdentifier = str(uuid.uuid4())
        return self._clientIdentifier

    def getGenerationalConfig(self) -> Optional[Dict[str, Any]]:
        days = self.get(Setting.GENERATIONAL_DAYS)
        weeks = self.get(Setting.GENERATIONAL_WEEKS)
        months = self.get(Setting.GENERATIONAL_MONTHS)
        years = self.get(Setting.GENERATIONAL_YEARS)
        if days + weeks + months + years == 0:
            return None
        base = GenConfig(
            days=days,
            weeks=weeks,
            months=months,
            years=years,
            day_of_week=self.get(Setting.GENERATIONAL_DAY_OF_WEEK),
            day_of_month=self.get(Setting.GENERATIONAL_DAY_OF_MONTH),
            day_of_year=self.get(Setting.GENERATIONAL_DAY_OF_YEAR),
            aggressive=self.get(Setting.GENERATIONAL_DELETE_EARLY)
        )
        if base.days <= 1:
            # must always be >= 1, otherwise we'll just create and delete backups constantly.
            base.days = 1
        return base

    def _loadRetained(self) -> List[str]:
        if os.path.exists(self.get(Setting.RETAINED_FILE_PATH)):
            with open(self.get(Setting.RETAINED_FILE_PATH)) as f:
                try:
                    return json.load(f)['retained']
                except json.JSONDecodeError:
                    logger.error("Unable to parse retained backup settings")
                    return []
        return []

    def isRetained(self, slug):
        return slug in self.retained

    def setRetained(self, slug, retain):
        if retain and slug not in self.retained:
            self.retained.append(slug)
            with open(self.get(Setting.RETAINED_FILE_PATH), "w") as f:
                json.dump({
                    'retained': self.retained
                }, f)
        elif not retain and slug in self.retained:
            self.retained.remove(slug)
            with open(self.get(Setting.RETAINED_FILE_PATH), "w") as f:
                json.dump({
                    'retained': self.retained
                }, f)

    def isExplicit(self, setting):
        return setting in self.config

    def override(self, setting: Setting, value):
        self.overrides[setting] = value
        return self

    def get(self, setting: Setting):
        if setting in self.overrides:
            return self.overrides[setting]
        if setting in self.config:
            return self.config[setting]
        if setting.key() in self.config:
            return self.config[setting.key()]
        else:
            return setting.default()

    def getForUi(self, setting: Setting):
        return _VALIDATORS[setting].formatForUi(self.get(setting))

    def getTokenServers(self, path: str = "") -> List[URL]:
        return list(map(lambda s: URL(s).with_path(path), self.get(Setting.TOKEN_SERVER_HOSTS).split(",")))

    def mustSaveUpgradeChanges(self):
        return self._config_was_upgraded

    def getAllConfig(self) -> Dict[Setting, Any]:
        return self.config.copy()

    def persistedChanges(self):
        self._config_was_upgraded = False
