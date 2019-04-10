import os.path
import json
import logging
from .logbase import LogBase
from typing import Dict, List, Any, Optional

HASSIO_OPTIONS_FILE = '/data/options.json'

DEFAULTS = {
    "max_snapshots_in_hassio": 4,
    "max_snapshots_in_google_drive": 4,
    "hassio_base_url": "http://hassio/",
    "ha_base_url": "http://hassio/homeassistant/api/",
    "path_separator": "/",
    "port": 1627,
    "days_between_snapshots": 3,

    # how many hours after startup the server will wait before starting a new snapshot automatically
    "hours_before_snapshot": 1,
    "folder_file_path": "/data/folder.dat",
    "credentials_file_path": "/data/credentials.dat",
    "seconds_between_refreshes": 60 * 60,  # once per hour, refresh everythin regardless
    "seconds_between_directory_checks": 10,
    "verbose": False,
    "use_ssl": False,
    "certfile": "/ssl/fullchain.pem",
    "keyfile": "/ssl/privkey.pem",
    "require_login": False,
    "backup_directory": "/backup",
    "snapshot_stale_minutes": 60 * 3,
    "ha_bearer": "",
    "snapshot_time_of_day": "",
    "notify_for_stale_snapshots": True,
    "enable_snapshot_stale_sensor": True,
    "enable_snapshot_state_sensor": True
}


class Config(LogBase):

    def __init__(self, file_paths: List[str] = [], extra_config: Dict[str, any] = {}):
        self.config_path = ""
        self.config: Dict[str, Any] = DEFAULTS.copy()
        for config_file in [HASSIO_OPTIONS_FILE, ""]:
            if os.path.isfile(config_file):
                with open(config_file) as file_handle:
                    self.config_path = config_file
                    self.config.update(json.load(file_handle))
        for config_file in file_paths:
            if os.path.isfile(config_file):
                with open(config_file) as file_handle:
                    self.info("Loading config from " + config_file)
                    self.config_path = config_file
                    self.config.update(json.load(file_handle))

        self.config.update(extra_config)
        self.info("Loaded config:")
        self.info(json.dumps(self.config, sort_keys=True, indent=4))
        if self.verbose():
            self.setConsoleLevel(logging.DEBUG)
        else:
            self.setConsoleLevel(logging.INFO)
        gen_config = self.getGenerationalConfig()
        if gen_config:
            self.info("Generationl backup config:")
            self.info(json.dumps(gen_config, sort_keys=True, indent=4))

    def maxSnapshotsInHassio(self) -> int:
        return int(self.config['max_snapshots_in_hassio'])

    def maxSnapshotsInGoogleDrive(self) -> int:
        return int(self.config['max_snapshots_in_google_drive'])

    def hassioBaseUrl(self) -> str:
        return str(self.config['hassio_base_url'])

    def haBaseUrl(self) -> str:
        return str(self.config['ha_base_url'])

    def pathSeparator(self) -> str:
        return str(self.config['path_separator'])

    def port(self) -> int:
        return int(self.config['port'])

    def daysBetweenSnapshots(self) -> float:
        return float(self.config['days_between_snapshots'])

    def hoursBeforeSnapshot(self) -> float:
        return float(self.config['hours_before_snapshot'])

    def folderFilePath(self) -> str:
        return str(self.config['folder_file_path'])

    def credentialsFilePath(self) -> str:
        return str(self.config['credentials_file_path'])

    def secondsBetweenRefreshes(self) -> int:
        return int(self.config['seconds_between_refreshes'])

    def secondsBetweenDirectoryChecks(self) -> float:
        return float(self.config['seconds_between_directory_checks'])

    def verbose(self) -> bool:
        return bool(self.config['verbose'])

    def useSsl(self) -> bool:
        return bool(self.config['use_ssl'])

    def certFile(self) -> str:
        return str(self.config['certfile'])

    def keyFile(self) -> str:
        return str(self.config['keyfile'])

    def requireLogin(self) -> bool:
        return bool(self.config['require_login'])

    def backupDirectory(self) -> str:
        return str(self.config['backup_directory'])

    def snapshotStaleMinutes(self) -> float:
        return float(self.config['snapshot_stale_minutes'])

    def haBearer(self) -> str:
        return str(self.config['ha_bearer'])

    def snapshotTimeOfDay(self) -> Optional[str]:
        if len(str(self.config['snapshot_time_of_day'])) > 0:
            return str(self.config['snapshot_time_of_day'])
        return None

    def getGenerationalConfig(self) -> Optional[Dict[str, Any]]:
        if 'generational_days' not in self.config and 'generational_weeks' not in self.config and 'generational_months' not in self.config and 'generational_years' not in self.config:
            return None
        base = {
            'days': 0,
            'weeks': 0,
            'months': 0,
            'years': 0,
            'day_of_week': 'mon',
            'day_of_month': 1,
            'day_of_year': 1
        }
        if 'generational_days' in self.config:
            base['days'] = self.config['generational_days']
        if 'generational_weeks' in self.config:
            base['weeks'] = self.config['generational_weeks']
        if 'generational_months' in self.config:
            base['months'] = self.config['generational_months']
        if 'generational_years' in self.config:
            base['years'] = self.config['generational_years']
        if 'generational_day_of_week' in self.config:
            base['day_of_week'] = self.config['generational_day_of_week']
        if 'generational_day_of_month' in self.config:
            base['day_of_month'] = self.config['generational_day_of_month']
        if 'generational_day_of_year' in self.config:
            base['day_of_year'] = self.config['generational_day_of_year']
        return base

    def notifyForStaleSnapshots(self) -> bool:
        return self.config["notify_for_stale_snapshots"]

    def enableSnapshotStaleSensor(self) -> bool:
        return self.config["enable_snapshot_stale_sensor"]

    def enableSnapshotStateSensor(self) -> bool:
        return self.config["enable_snapshot_state_sensor"]

    def update(self, **kwargs) -> None:
        # load the existing config
        old_config: Dict[str, Any] = None
        with open(self.config_path) as file_handle:
            old_config = json.load(file_handle)

        # Required options
        if 'max_snapshots_in_hassio' in kwargs and len(kwargs['max_snapshots_in_hassio']) > 0:
            old_config['max_snapshots_in_hassio'] = int(kwargs['max_snapshots_in_hassio'])

        if 'max_snapshots_in_google_drive' in kwargs and len(kwargs['max_snapshots_in_google_drive']) > 0:
            old_config['max_snapshots_in_google_drive'] = int(kwargs['max_snapshots_in_google_drive'])

        if 'use_ssl' in kwargs and kwargs['use_ssl'] == 'on':
            old_config['use_ssl'] = True
            if 'certfile' in kwargs and len(kwargs['certfile']) > 0:
                old_config['certfile'] = kwargs['certfile']
            if 'keyfile' in kwargs and len(kwargs['keyfile']) > 0:
                old_config['keyfile'] = kwargs['keyfile']
        else:
            old_config['use_ssl'] = False
            if 'certfile' in old_config:
                del old_config['certfile']
            if 'keyfile' in old_config:
                del old_config['keyfile']

        # optional boolean config
        if 'require_login' in kwargs and kwargs['require_login'] == 'on':
            old_config['require_login'] = True
        elif 'require_login' in old_config:
            del old_config['require_login']

        if 'notify_for_stale_snapshots' not in kwargs:
            old_config['notify_for_stale_snapshots'] = False
        elif 'notify_for_stale_snapshots' in old_config:
            del old_config['notify_for_stale_snapshots']

        if 'enable_snapshot_stale_sensor' not in kwargs:
            old_config['enable_snapshot_stale_sensor'] = False
        elif 'enable_snapshot_stale_sensor' in old_config:
            del old_config['enable_snapshot_stale_sensor']

        if 'enable_snapshot_state_sensor' not in kwargs:
            old_config['enable_snapshot_state_sensor'] = False
        elif 'enable_snapshot_state_sensor' in old_config:
            del old_config['enable_snapshot_state_sensor']

        if 'snapshot_time_of_day' in kwargs and len(kwargs['snapshot_time_of_day']) > 0:
            old_config['snapshot_time_of_day'] = kwargs['snapshot_time_of_day']
        elif 'snapshot_time_of_day' in old_config:
            del old_config['snapshot_time_of_day']

        if 'generational_enabled' not in kwargs or kwargs['generational_enabled'] == 'off':
            if 'generational_days' in old_config:
                del old_config['generational_days']
            if 'generational_weeks' in old_config:
                del old_config['generational_weeks']
            if 'generational_months' in old_config:
                del old_config['generational_months']
            if 'generational_years' in old_config:
                del old_config['generational_years']
        else:
            if 'generational_days' in kwargs and len(kwargs['generational_days']) > 0:
                old_config['generational_days'] = int(kwargs['generational_days'])
            else:
                old_config['generational_weeks'] = 0

            if 'generational_weeks' in kwargs and len(kwargs['generational_weeks']) > 0:
                old_config['generational_weeks'] = int(kwargs['generational_weeks'])
            else:
                old_config['generational_weeks'] = 0

            if 'generational_months' in kwargs and len(kwargs['generational_months']) > 0:
                old_config['generational_months'] = int(kwargs['generational_months'])
            else:
                old_config['generational_months'] = 0

            if 'generational_years' in kwargs and len(kwargs['generational_years']) > 0:
                old_config['generational_years'] = int(kwargs['generational_years'])
            else:
                old_config['generational_years'] = 0

            if 'generational_day_of_week' in kwargs and len(kwargs['generational_day_of_week']) > 0:
                old_config['generational_day_of_week'] = kwargs['generational_day_of_week']
            else:
                old_config['generational_day_of_week'] = 'mon'

            if 'generational_day_of_month' in kwargs and len(kwargs['generational_day_of_month']) > 0:
                old_config['generational_day_of_month'] = int(kwargs['generational_day_of_month'])
            else:
                old_config['generational_day_of_month'] = 1

            if 'generational_day_of_year' in kwargs and len(kwargs['generational_day_of_year']) > 0:
                old_config['generational_day_of_year'] = int(kwargs['generational_day_of_year'])
            else:
                old_config['generational_day_of_year'] = 1
        self.info(str(kwargs))

        with open(self.config_path, "w") as file_handle:
            json.dump(old_config, file_handle, indent=4)

        self.config = DEFAULTS.copy()
        self.config.update(old_config)
