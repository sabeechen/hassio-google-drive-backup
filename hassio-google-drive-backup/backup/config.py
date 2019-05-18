import json
import os
import os.path
import os
import re
import uuid
import logging
import yaml

from os.path import abspath, join
from .logbase import LogBase, console_handler
from typing import Dict, List, Any, Optional
from .exceptions import InvalidConfigurationValue, SnapshotPasswordKeyInvalid
from .helpers import strToBool
from .resolver import Resolver
from datetime import datetime

HASSIO_OPTIONS_FILE = '/data/options.json'
MIN_INGRESS_VERSION = [0, 91, 3]
ADDON_OPTIONS_FILE = 'config.json'
SNAPSHOT_NAME_DEFALT = "{type} Snapshot {year}-{month}-{day} {hr24}:{min}:{sec}"

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
    "seconds_between_directory_checks": 1,
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
    "generational_days": 0,
    "generational_weeks": 0,
    "generational_months": 0,
    "generational_years": 0,
    "generational_day_of_week": "mon",
    "generational_day_of_month": 1,
    "generational_day_of_year": 1,
    "expose_extra_server": True,
    "ingress_upgrade_file": "/data/upgrade_ingress",
    "retained_file": "/data/retained.json",
    "snapshot_name": SNAPSHOT_NAME_DEFALT,
    "secrets_file_path": "/config/secrets.yaml",
    "drive_experimental": False,
    "drive_ipv4": "",
    'ignore_ipv6_addresses': False,
    "drive_host": "https://www.googleapis.com",
    "google_drive_timeout_seconds": 180,
    "google_drive_page_size": 100,
    "pending_snapshot_timout_seconds": 60 * 60 * 3,
    "failed_snapshot_timout_seconds": 60 * 30,
    "new_snapshot_pending_timeout_seconds": 5,
    "authenticate_url": "https://philosophyofpen.com/login/backup.py",
    "confirm_multiple_deletes": True,
    "max_seconds_between_syncs": 60 * 60,
    "alternate_dns_servers": "8.8.8.8,8.8.4.4"
}

ALWAYS_KEEP = {
    "days_between_snapshots",
    "max_snapshots_in_hassio",
    "max_snapshots_in_google_drive",
    "use_ssl"
}

GENERATIONAL_ON = {
    "generational_days",
    "generational_weeks",
    "generational_months",
    "generational_years"
}

SNAPSHOT_NAME_KEYS = {
    "{type}": lambda snapshot_type, now_local, host_info: snapshot_type,
    "{year}": lambda snapshot_type, now_local, host_info: now_local.strftime("%Y"),
    "{year_short}": lambda snapshot_type, now_local, host_info: now_local.strftime("%y"),
    "{weekday}": lambda snapshot_type, now_local, host_info: now_local.strftime("%A"),
    "{weekday_short}": lambda snapshot_type, now_local, host_info: now_local.strftime("%a"),
    "{month}": lambda snapshot_type, now_local, host_info: now_local.strftime("%m"),
    "{month_long}": lambda snapshot_type, now_local, host_info: now_local.strftime("%B"),
    "{month_short}": lambda snapshot_type, now_local, host_info: now_local.strftime("%b"),
    "{ms}": lambda snapshot_type, now_local, host_info: now_local.strftime("%f"),
    "{day}": lambda snapshot_type, now_local, host_info: now_local.strftime("%d"),
    "{hr24}": lambda snapshot_type, now_local, host_info: now_local.strftime("%H"),
    "{hr12}": lambda snapshot_type, now_local, host_info: now_local.strftime("%I"),
    "{min}": lambda snapshot_type, now_local, host_info: now_local.strftime("%M"),
    "{sec}": lambda snapshot_type, now_local, host_info: now_local.strftime("%S"),
    "{ampm}": lambda snapshot_type, now_local, host_info: now_local.strftime("%p"),
    "{version_ha}": lambda snapshot_type, now_local, host_info: str(host_info.get('homeassistant', 'None')),
    "{version_hassos}": lambda snapshot_type, now_local, host_info: str(host_info.get('hassos', 'None')),
    "{version_super}": lambda snapshot_type, now_local, host_info: str(host_info.get('supervisor', 'None')),
    "{date}": lambda snapshot_type, now_local, host_info: now_local.strftime("%x"),
    "{time}": lambda snapshot_type, now_local, host_info: now_local.strftime("%X"),
    "{datetime}": lambda snapshot_type, now_local, host_info: now_local.strftime("%c"),
    "{isotime}": lambda snapshot_type, now_local, host_info: now_local.isoformat()
}


class Config(LogBase):
    def __init__(self, extra_config: Dict[str, any] = {}, resolver: Resolver = None):
        self.extra_config = extra_config
        self.config: Dict[str, Any] = DEFAULTS.copy()
        self.config.update(self.extra_config)
        self.ha_version = "unknown"
        self._clientIdentifier = uuid.uuid4()
        self.resolver = resolver
        console_handler.setLevel(logging.DEBUG if self.verbose() else logging.INFO)

        # True when support for ingress urls is enabled.
        self.ingress_enabled = False

        # True if we shoudl wanr the user about upgradint othe lastest verison for ingress support.
        self.warn_ingress = False

        # True if we should watn the user to disable their exposed Web UI
        self.warn_expose_server = False

        self.retained = self._loadRetained()
        self._gen_config_cache = self.getGenerationalConfig()
        self.setIngressInfo()

        # set up resolver
        if self.resolver is not None:
            if len(self.driveIpv4()) > 0:
                self.resolver.addOverride("www.googleapis.com", [self.driveIpv4()])
            self.resolver.addResolveAddress("www.googleapis.com")
            self.resolver.setIgnoreIpv6(self.ignoreIpv6())
            self.resolver.setDnsServers(self.alternateDnsServers().split(","))

    def validateUpdate(self, additions):
        new_config = self.config.copy()
        new_config.update(additions)
        return self.validate(new_config)

    def resolvePassword(self, password=None):
        if password is None:
            password = self.snapshotPassword()
        if len(password) == 0:
            return None
        if password.startswith("!secret "):
            if not os.path.isfile(self.secretsFilePath()):
                raise SnapshotPasswordKeyInvalid()
            with open(self.secretsFilePath()) as f:
                secrets_yaml = yaml.load(f, Loader=yaml.SafeLoader)
            key = password[len("!secret "):]
            if key not in secrets_yaml:
                raise SnapshotPasswordKeyInvalid()
            return str(secrets_yaml[key])
        else:
            return self.snapshotPassword()

    def resolveSnapshotName(self, snapshot_type: str, template: str, now_local: datetime, host_info) -> str:
        for key in SNAPSHOT_NAME_KEYS:
            template = template.replace(key, SNAPSHOT_NAME_KEYS[key](snapshot_type, now_local, host_info))
        return template

    def validate(self, new_config) -> Dict[str, Any]:
        defaults = DEFAULTS.copy()
        defaults.update(self.extra_config)
        # read the add-on configuration file
        path = abspath(join(__file__, "..", "..", "config.json"))
        with open(path) as f:
            addon_config = json.load(f)
        addon_config.copy()
        final_config = {}

        # validate each item
        for key in new_config:
            if key not in addon_config["schema"]:
                # its not in the schema, just ignore it
                pass
            else:
                schema = addon_config["schema"][key]
                final_config[key] = self._validateConfig(key, schema, new_config[key])

        # remove defaulted items
        for key in list(final_config.keys()):
            if final_config[key] == defaults[key]:
                del final_config[key]

        # add defaults
        for key in ALWAYS_KEEP:
            if key not in final_config:
                final_config[key] = defaults[key]

        if not final_config.get('use_ssl', False):
            for key in ['certfile', 'keyfile']:
                if key in final_config:
                    del final_config[key]
        if not final_config.get('send_error_reports', False):
            final_config['send_error_reports'] = False

        if len(final_config.get('snapshot_password', "")) > 0:
            self.resolvePassword(final_config['snapshot_password'])
        return final_config

    def update(self, new_config):
        self.config: Dict[str, Any] = DEFAULTS.copy()
        self.config.update(self.extra_config)
        self.config.update(new_config)
        self._gen_config_cache = self.getGenerationalConfig()
        self.setIngressInfo()
        console_handler.setLevel(logging.DEBUG if self.verbose() else logging.INFO)
        if self.resolver is not None:
            if len(self.driveIpv4()) > 0:
                self.resolver.addOverride("www.googleapis.com", [self.driveIpv4()])
            else:
                self.resolver.clearOverrides()
            self.resolver.addResolveAddress("www.googleapis.com")
            self.resolver.setIgnoreIpv6(self.ignoreIpv6())
            self.resolver.setDnsServers(self.alternateDnsServers().split(","))

    def _validateConfig(self, key, schema: str, value):
        if schema.endswith("?"):
            if len(str(value)) == 0 or value is None:
                return value
            schema = schema[:-1]
        if schema.startswith("int("):
            # its a int
            parts = schema[4:-1]
            minimum = -100000000
            maximum = 1000000000
            if parts.endswith(","):
                minimum = int(parts[0:-1])
            elif parts.startswith(","):
                maximum = int(parts[1:])
            else:
                digits = parts.split(",")
                minimum = int(digits[0])
                maximum = int(digits[1])
            if int(value) > maximum or int(value) < minimum:
                raise InvalidConfigurationValue(key, value)
            return int(value)
        elif schema.startswith("float("):
            # its a float
            parts = schema[6:-1]
            minimum = -100000000
            maximum = 1000000000
            if parts.endswith(","):
                minimum = float(parts[0:-1])
            elif parts.startswith(","):
                maximum = float(parts[1:])
            else:
                digits = parts.split(",")
                minimum = float(digits[0])
                maximum = float(digits[1])
            if float(value) > maximum or float(value) < minimum:
                raise InvalidConfigurationValue(key, value)
            return float(value)
        elif schema.startswith("bool"):
            # its a bool
            return strToBool(value)
        elif schema.startswith("str") or schema.startswith("url"):
            # its a url (treat it just like any string)
            return str(value)
        elif schema.startswith("match("):
            pattern = schema[6:-1]
            if not re.match(pattern, str(value)):
                raise InvalidConfigurationValue(key, value)
            return str(value)

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

    def setIngressInfo(self, host_info=None, force_enable=False):
        # check if the add-on has ingress enabled
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
            self.error("Unable to parse Home Assistant version string: " + version)
            return False

    def driveHost(self) -> str:
        return str(self.config['drive_host'])

    def alternateDnsServers(self) -> str:
        return str(self.config['alternate_dns_servers'])

    def googleDriveTimeoutSeconds(self) -> float:
        return float(self.config["google_drive_timeout_seconds"])

    def googleDrivePageSize(self) -> int:
        return int(self.config["google_drive_page_size"])

    def pendingSnapshotTimeoutSeconds(self) -> float:
        return float(self.config["pending_snapshot_timout_seconds"])

    def failedSnapshotTimeoutSeconds(self) -> float:
        return float(self.config["failed_snapshot_timout_seconds"])

    def newSnapshotTimeoutSeconds(self) -> float:
        return float(self.config["new_snapshot_pending_timeout_seconds"])

    def retainedFile(self) -> str:
        return str(self.config['retained_file'])

    def excludeFolders(self) -> str:
        return str(self.config['exclude_folders'])

    def excludeAddons(self) -> str:
        return str(self.config['exclude_addons'])

    def confirmMultipleDeletes(self) -> bool:
        return bool(self.config['confirm_multiple_deletes'])

    def maxSecondsBetweenSyncs(self) -> bool:
        return int(self.config["max_seconds_between_syncs"])

    def snapshotPassword(self) -> str:
        return str(self.config['snapshot_password'])

    def maxSnapshotsInHassio(self) -> int:
        return int(self.config['max_snapshots_in_hassio'])

    def maxSnapshotsInGoogleDrive(self) -> int:
        return int(self.config['max_snapshots_in_google_drive'])

    def hassioBaseUrl(self) -> str:
        return str(self.config['hassio_base_url'])

    def authenticateUrl(self) -> str:
        return str(self.config['authenticate_url'])

    def haBaseUrl(self) -> str:
        return str(self.config['ha_base_url'])

    def pathSeparator(self) -> str:
        return str(self.config['path_separator'])

    def secretsFilePath(self) -> str:
        return str(self.config['secrets_file_path'])

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

    def driveExperimental(self) -> bool:
        return bool(self.config['drive_experimental'])

    def driveIpv4(self) -> str:
        return str(self.config['drive_ipv4'])

    def clientIdentifier(self) -> str:
        return str(self._clientIdentifier)

    def getHassioHeaders(self):
        if 'hassio_header' in self.config:
            return {
                "X-HASSIO-KEY": self.config['hassio_header'],
                'Client-Identifier': self.clientIdentifier()
            }
        else:
            return {
                "X-HASSIO-KEY": os.environ.get("HASSIO_TOKEN"),
                'Client-Identifier': self.clientIdentifier()
            }

    def getHaHeaders(self):
        if 'hassio_header' in self.config:
            return {
                'Authorization': 'Bearer ' + self.config['hassio_header'],
                'Client-Identifier': self.clientIdentifier()
            }
        else:
            return {
                'Authorization': 'Bearer ' + str(os.environ.get("HASSIO_TOKEN")),
                'Client-Identifier': self.clientIdentifier()
            }

    def snapshotName(self) -> str:
        return self.config["snapshot_name"]

    def getGenerationalConfig(self) -> Optional[Dict[str, Any]]:
        if self.config['generational_days'] == 0 and self.config['generational_weeks'] == 0 and self.config['generational_months'] == 0 and self.config['generational_years'] == 0:
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

        if base['days'] <= 1:
            # must always be >= 1, otherwise we'll just create and delete snapshots constantly.
            base['days'] = 1
        return base

    def notifyForStaleSnapshots(self) -> bool:
        return self.config["notify_for_stale_snapshots"]

    def enableSnapshotStaleSensor(self) -> bool:
        return self.config["enable_snapshot_stale_sensor"]

    def enableSnapshotStateSensor(self) -> bool:
        return self.config["enable_snapshot_state_sensor"]

    def _loadRetained(self) -> List[str]:
        if os.path.exists(self.retainedFile()):
            with open(self.retainedFile()) as f:
                try:
                    return json.load(f)['retained']
                except json.JSONDecodeError:
                    self.error("Unable to parse retained snapshot settings")
                    return []
        return []

    def isRetained(self, slug):
        return slug in self.retained

    def setRetained(self, slug, retain):
        if retain and slug not in self.retained:
            self.retained.append(slug)
            with open(self.retainedFile(), "w") as f:
                json.dump({
                    'retained': self.retained
                }, f)
        elif not retain and slug in self.retained:
            self.retained.remove(slug)
            with open(self.retainedFile(), "w") as f:
                json.dump({
                    'retained': self.retained
                }, f)

    def ignoreIpv6(self) -> bool:
        return bool(self.config['ignore_ipv6_addresses'])
