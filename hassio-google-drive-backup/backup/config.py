import json
import os
import logging
from .logbase import LogBase
from .helpers import formatException
from typing import Dict, List, Any, Optional

HASSIO_OPTIONS_FILE = '/data/options.json'
MIN_INGRESS_VERSION = [0, 91, 3]
ADDON_OPTIONS_FILE = 'config.json'
DEFAULTS = {
    "max_snapshots_in_hassio": 4,
    "max_snapshots_in_google_drive": 4,
    "hassio_base_url": "http://hassio/",
    "ha_base_url": "http://hassio/homeassistant/api/",
    "path_separator": "/",
    "ingress_port": 8099,
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
    "enable_snapshot_state_sensor": True,
    "snapshot_password": "",
    "send_error_reports": None,
    "exclude_folders": "",
    "exclude_addons": "",
    "expose_extra_server": False,
    "ingress_upgrade_file": "/data/upgrade_ingress",
    "retained_file": "/data/retained.json"
}


class Config(LogBase):
    def __init__(self, file_paths: List[str] = [], extra_config: Dict[str, any] = {}):
        self.config_path = ""
        self.config: Dict[str, Any] = DEFAULTS.copy()
        for config_file in file_paths:
            with open(config_file) as file_handle:
                self.info("Loading config from " + config_file)
                self.config_path = config_file
                self.config.update(json.load(file_handle))

        self.default: Dict[str, Any] = DEFAULTS.copy()
        for config_file in file_paths[:-1]:
            with open(config_file) as file_handle:
                self.default.update(json.load(file_handle))

        if self.verbose():
            self.setConsoleLevel(logging.DEBUG)
        else:
            self.setConsoleLevel(logging.INFO)

        self.config.update(extra_config)
        self.debug("Loaded config:")
        self.debug(json.dumps(self.config, sort_keys=True, indent=4))

        gen_config = self.getGenerationalConfig()
        if gen_config:
            self.debug("Generationl backup config:")
            self.debug(json.dumps(gen_config, sort_keys=True, indent=4))

        self.ha_version = "unknown"

        # True when support for ingress urls is enabled.
        self.ingress_enabled = False

        # True if we shoudl wanr the user about upgradint othe lastest verison for ingress support.
        self.warn_ingress = False

        # True if we should watnt he user to disable their exposed Web UI
        self.warn_expose_server = False

        self.retained = self._loadRetained()

    def setSendErrorReports(self, handler, send: bool) -> None:
        self.config['send_error_reports'] = send

        old_config: Dict[str, Any] = None
        with open(self.config_path) as file_handle:
            old_config = json.load(file_handle)
        old_config['send_error_reports'] = send
        self.warn_expose_server = False
        handler(old_config)

    def setExposeAdditionalServer(self, handler, expose) -> None:
        self.config['expose_extra_server'] = expose

        old_config: Dict[str, Any] = None
        with open(self.config_path) as file_handle:
            old_config = json.load(file_handle)
        if expose:
            old_config['expose_extra_server'] = expose
        elif 'expose_extra_server' in old_config:
            del old_config['expose_extra_server']

        if not expose and 'require_login' in old_config:
            del old_config['require_login']
        handler(old_config)
        if not os.path.exists(self.ingressUpgradeFile()):
            with open(self.ingressUpgradeFile(), 'x'):
                pass

    def setIngressInfo(self, host_info, force_enable=False):
        # check if the add-on has ingress enabled
        try:
            with open(ADDON_OPTIONS_FILE) as handle:
                addon_config = json.load(handle)
                supports_ingress = "ingress" in addon_config and addon_config['ingress']
        except Exception as e:
            self.error(formatException(e))
            supports_ingress = False

        if not supports_ingress and not force_enable:
            self.ingress_enabled = False
            self.warn_ingress = False
            self.warn_expose_server = False
            self.config['expose_extra_server'] = True
            return

        self.warn_expose_server = False
        if 'homeassistant' in host_info:
            self.ingress_enabled = self._isGreaterOrEqualVersion(host_info['homeassistant'])
            self.warn_ingress = not self.ingress_enabled
        else:
            self.ingress_enabled = False
            self.warn_ingress = True
            self.warn_expose_server = False
        if not self.ingress_enabled:
            # we must expose this server if ingress isn't enabled
            self.config['expose_extra_server'] = True

        # Handle upgrading from a previous version
        if not os.path.exists(self.ingressUpgradeFile()) and self.ingress_enabled:
            if os.path.exists(self.credentialsFilePath()):
                # we've upgraded, so warn about ingress but expose the additional server.
                self.warn_expose_server = True
                self.config['expose_extra_server'] = True
            elif not force_enable:
                # its a new install, so just default to using ingress in the future.
                with open(self.ingressUpgradeFile(), 'x'):
                    pass

    def warnExposeIngressUpgrade(self):
        return self.warn_expose_server

    def ingressUpgradeFile(self):
        return self.config['ingress_upgrade_file']

    def useIngress(self):
        return self.ingress_enabled

    def warnIngress(self):
        return self.warn_ingress

    def _isGreaterOrEqualVersion(self, version):
        try:
            version_parts = version.split(".")
            for i in range(len(MIN_INGRESS_VERSION)):
                version = int(version_parts[i])
                if version < MIN_INGRESS_VERSION[i]:
                    return False
                if version > MIN_INGRESS_VERSION[i]:
                    return True
            # Version string is longer than the min verison, so we'll just assume its newer
            return True
        except ValueError:
            self.error("Unable to parse Hoem Assistant version string: " + version)
            return False

    def retainedFile(self) -> str:
        return str(self.config['retained_file'])

    def excludeFolders(self) -> str:
        return str(self.config['exclude_folders'])

    def excludeAddons(self) -> str:
        return str(self.config['exclude_addons'])

    def snapshotPassword(self) -> str:
        return str(self.config['snapshot_password'])

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

    def ingressPort(self) -> int:
        return int(self.config['ingress_port'])

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

    def sendErrorReports(self) -> Optional[bool]:
        return self.config['send_error_reports']

    def certFile(self) -> str:
        return str(self.config['certfile'])

    def keyFile(self) -> str:
        return str(self.config['keyfile'])

    def exposeExtraServer(self) -> bool:
        return bool(self.config['expose_extra_server'])

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

    def getHassioHeaders(self):
        if 'hassio_header' in self.config:
            return {"X-HASSIO-KEY": self.config['hassio_header']}
        else:
            return {"X-HASSIO-KEY": os.environ.get("HASSIO_TOKEN")}

    def getHaHeaders(self):
        if 'hassio_header' in self.config:
            return {'Authorization': 'Bearer ' + self.config['hassio_header']}
        else:
            return {'Authorization': 'Bearer ' + str(os.environ.get("HASSIO_TOKEN"))}

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

    def update(self, handler, **kwargs: Dict[str, Any]) -> None:
        # load the existing config
        old_config: Dict[str, Any] = None
        with open(self.config_path) as file_handle:
            old_config = json.load(file_handle)

        # Required options
        if 'max_snapshots_in_hassio' in kwargs and len(kwargs['max_snapshots_in_hassio']) > 0:
            old_config['max_snapshots_in_hassio'] = int(kwargs['max_snapshots_in_hassio'])

        if 'max_snapshots_in_google_drive' in kwargs and len(kwargs['max_snapshots_in_google_drive']) > 0:
            old_config['max_snapshots_in_google_drive'] = int(kwargs['max_snapshots_in_google_drive'])

        if 'days_between_snapshots' in kwargs and len(kwargs['days_between_snapshots']) > 0:
            old_config['days_between_snapshots'] = int(kwargs['days_between_snapshots'])

        if 'snapshot_password' in kwargs:
            if len(kwargs['snapshot_password']) > 0:
                old_config['snapshot_password'] = kwargs['snapshot_password']
            elif 'snapshot_password' in old_config:
                del old_config['snapshot_password']

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

        if 'send_error_reports' in kwargs and kwargs['send_error_reports'] == 'on':
            old_config['send_error_reports'] = True
        else:
            old_config['send_error_reports'] = False

        if 'verbose' in kwargs and kwargs['verbose'] == 'on':
            old_config['verbose'] = True
        elif 'verbose' in old_config:
            del old_config['verbose']

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

        if 'expose_extra_server' in kwargs:
            old_config['expose_extra_server'] = True
        elif 'expose_extra_server' in old_config:
            del old_config['expose_extra_server']

        if 'snapshot_time_of_day' in kwargs and len(kwargs['snapshot_time_of_day']) > 0:
            old_config['snapshot_time_of_day'] = kwargs['snapshot_time_of_day']
        elif 'snapshot_time_of_day' in old_config:
            del old_config['snapshot_time_of_day']

        if 'partial_snapshots' not in kwargs or kwargs['partial_snapshots'] == 'off':
            if 'exclude_folders' in old_config:
                del old_config['exclude_folders']
            if 'exclude_addons' in old_config:
                del old_config['exclude_addons']
            if 'exclude_homeassistant' in old_config:
                del old_config['exclude_homeassistant']
        else:
            if 'exclude_folders' in kwargs and len(kwargs['exclude_folders']) > 0:
                old_config['exclude_folders'] = kwargs['exclude_folders']
            elif 'exclude_folders' in old_config:
                del old_config['exclude_folders']

            if 'exclude_addons' in kwargs and len(kwargs['exclude_addons']) > 0:
                old_config['exclude_addons'] = kwargs['exclude_addons']
            elif 'exclude_addons' in old_config:
                del old_config['exclude_addons']

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

        if 'generational_day_of_week' in old_config and old_config['generational_day_of_week'] == "mon":
            del old_config['generational_day_of_week']

        if 'generational_day_of_month' in kwargs and len(kwargs['generational_day_of_month']) > 0:
            old_config['generational_day_of_month'] = int(kwargs['generational_day_of_month'])

        if 'generational_day_of_month' in old_config and old_config['generational_day_of_month'] == 1:
            del old_config['generational_day_of_month']

        if 'generational_day_of_year' in kwargs and len(kwargs['generational_day_of_year']) > 0:
            old_config['generational_day_of_year'] = int(kwargs['generational_day_of_year'])

        if 'generational_day_of_year' in old_config and old_config['generational_day_of_year'] == 1:
            del old_config['generational_day_of_year']

        handler(old_config)

        self.config = self.default.copy()
        self.config.update(old_config)

    def _loadRetained(self) -> List[str]:
        if os.path.exists(self.retainedFile()):
            with open(self.retainedFile()) as f:
                return json.load(f)['retained']
        return []

    def saveRetained(self, list) -> None:
        with open(self.retainedFile(), "w") as f:
            json.dump({
                'retained': list
            }, f)
        self.retained = self._loadRetained()

    def isRetained(self, slug):
        return slug in self.retained
