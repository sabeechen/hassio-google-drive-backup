from ast import Bytes
import json
from enum import Enum, unique
from os.path import abspath, join

from .boolvalidator import BoolValidator
from .floatvalidator import FloatValidator
from .intvalidator import IntValidator
from .regexvalidator import RegexValidator
from .stringvalidator import StringValidator
from .listvalidator import ListValidator
from .durationasstringvalidator import DurationAsStringValidator
from .bytesizeasstringvalidator import BytesizeAsStringValidator
from ..logger import getLogger

logger = getLogger(__name__)


@unique
class Setting(Enum):
    MAX_BACKUPS_IN_HA = "max_backups_in_ha"
    MAX_BACKUPS_IN_GOOGLE_DRIVE = "max_backups_in_google_drive"
    DAYS_BETWEEN_BACKUPS = "days_between_backups"
    IGNORE_OTHER_BACKUPS = "ignore_other_backups"
    IGNORE_UPGRADE_BACKUPS = "ignore_upgrade_backups"
    DELETE_IGNORED_AFTER_DAYS = "delete_ignored_after_days"
    DELETE_BEFORE_NEW_BACKUP = "delete_before_new_backup"
    BACKUP_NAME = "backup_name"
    BACKUP_TIME_OF_DAY = "backup_time_of_day"
    SPECIFY_BACKUP_FOLDER = "specify_backup_folder"
    NOTIFY_FOR_STALE_BACKUPS = "notify_for_stale_backups"
    ENABLE_BACKUP_STALE_SENSOR = "enable_backup_stale_sensor"
    ENABLE_BACKUP_STATE_SENSOR = "enable_backup_state_sensor"
    BACKUP_PASSWORD = "backup_password"
    CALL_BACKUP_SNAPSHOT = "call_backup_snapshot"

    # Basic backup settings
    WARN_FOR_LOW_SPACE = "warn_for_low_space"
    LOW_SPACE_THRESHOLD = "low_space_threshold"
    DELETE_AFTER_UPLOAD = "delete_after_upload"

    # generational settings
    GENERATIONAL_DAYS = "generational_days"
    GENERATIONAL_WEEKS = "generational_weeks"
    GENERATIONAL_MONTHS = "generational_months"
    GENERATIONAL_YEARS = "generational_years"
    GENERATIONAL_DAY_OF_WEEK = "generational_day_of_week"
    GENERATIONAL_DAY_OF_MONTH = "generational_day_of_month"
    GENERATIONAL_DAY_OF_YEAR = "generational_day_of_year"
    GENERATIONAL_DELETE_EARLY = "generational_delete_early"

    # Partial backups
    EXCLUDE_FOLDERS = "exclude_folders"
    EXCLUDE_ADDONS = "exclude_addons"

    STOP_ADDONS = "stop_addons"
    DISABLE_WATCHDOG_WHEN_STOPPING = "disable_watchdog_when_stopping"

    # UI Server Options
    USE_SSL = "use_ssl"
    CERTFILE = "certfile"
    KEYFILE = "keyfile"
    INGRESS_PORT = "ingress_port"
    PORT = "port"
    REQUIRE_LOGIN = "require_login"
    EXPOSE_EXTRA_SERVER = "expose_extra_server"

    # Add-on options
    VERBOSE = "verbose"
    SEND_ERROR_REPORTS = "send_error_reports"
    CONFIRM_MULTIPLE_DELETES = "confirm_multiple_deletes"
    ENABLE_DRIVE_UPLOAD = "enable_drive_upload"

    # Theme Settings
    BACKGROUND_COLOR = "background_color"
    ACCENT_COLOR = "accent_color"

    # Network and dns stuff
    DRIVE_EXPERIMENTAL = "drive_experimental"
    DRIVE_IPV4 = "drive_ipv4"
    IGNORE_IPV6_ADDRESSES = "ignore_ipv6_addresses"
    GOOGLE_DRIVE_TIMEOUT_SECONDS = "google_drive_timeout_seconds"
    GOOGLE_DRIVE_PAGE_SIZE = "google_drive_page_size"
    ALTERNATE_DNS_SERVERS = "alternate_dns_servers"
    DEFAULT_DRIVE_CLIENT_ID = "default_drive_client_id"
    DEFAULT_DRIVE_CLIENT_SECRET = "default_drive_client_secret"
    DRIVE_PICKER_API_KEY = "drive_picker_api_key"
    MAXIMUM_UPLOAD_CHUNK_BYTES = "maximum_upload_chunk_bytes"

    # Files and folders
    FOLDER_FILE_PATH = "folder_file_path"
    CREDENTIALS_FILE_PATH = "credentials_file_path"
    RETAINED_FILE_PATH = "retained_file_path"
    SECRETS_FILE_PATH = "secrets_file_path"
    BACKUP_DIRECTORY_PATH = "backup_directory_path"
    INGRESS_TOKEN_FILE_PATH = "ingress_token_file_path"
    CONFIG_FILE_PATH = "config_file_path"
    ID_FILE_PATH = "id_file_path"
    DATA_CACHE_FILE_PATH = "data_cache_file_path"

    # endpoints
    AUTHORIZATION_HOST = "authorization_host"
    TOKEN_SERVER_HOSTS = "token_server_hosts"
    SUPERVISOR_URL = "supervisor_url"
    DRIVE_URL = "drive_url"
    SUPERVISOR_TOKEN = "hassio_header"
    DRIVE_HOST_NAME = "drive_host_name"
    DRIVE_REFRESH_URL = "drive_refresh_url"
    DRIVE_AUTHORIZE_URL = "drive_authorize_url"
    DRIVE_DEVICE_CODE_URL = "drive_device_code_url"
    DRIVE_TOKEN_URL = "drive_token_url"
    SAVE_DRIVE_CREDS_PATH = "save_drive_creds_path"
    STOP_ADDON_STATE_PATH = "stop_addon_state_path"

    # Timing and timeouts
    MAX_SYNC_INTERVAL_SECONDS = "max_sync_interval_seconds"
    BACKUP_STALE_SECONDS = "backup_stale_seconds"
    PENDING_BACKUP_TIMEOUT_SECONDS = "pending_backup_timeout_seconds"
    FAILED_BACKUP_TIMEOUT_SECONDS = "failed_backup_timeout_seconds"
    NEW_BACKUP_TIMEOUT_SECONDS = "new_backup_timeout_seconds"
    DOWNLOAD_TIMEOUT_SECONDS = "download_timeout_seconds"
    DEFAULT_CHUNK_SIZE = "default_chunk_size"
    DEBUGGER_PORT = "debugger_port"
    SERVER_PROJECT_ID = "server_project_id"
    LOG_LEVEL = "log_level"
    CONSOLE_LOG_LEVEL = "console_log_level"
    BACKUP_STARTUP_DELAY_MINUTES = "backup_startup_delay_minutes"
    EXCHANGER_TIMEOUT_SECONDS = "exchanger_timeout_seconds"

    # Old, deprecated settings
    DEPRECTAED_MAX_BACKUPS_IN_HA = "max_snapshots_in_hassio"
    DEPRECTAED_MAX_BACKUPS_IN_GOOGLE_DRIVE = "max_snapshots_in_google_drive"
    DEPRECATED_DAYS_BETWEEN_BACKUPS = "days_between_snapshots"
    DEPRECTAED_IGNORE_OTHER_BACKUPS = "ignore_other_snapshots"
    DEPRECTAED_IGNORE_UPGRADE_BACKUPS = "ignore_upgrade_snapshots"
    DEPRECTAED_BACKUP_NAME = "snapshot_name"
    DEPRECTAED_BACKUP_TIME_OF_DAY = "snapshot_time_of_day"
    DEPRECATED_BACKUP_PASSWORD = "snapshot_password"
    DEPRECTAED_SPECIFY_BACKUP_FOLDER = "specify_snapshot_folder"
    DEPRECTAED_DELETE_BEFORE_NEW_BACKUP = "delete_before_new_snapshot"
    DEPRECTAED_NOTIFY_FOR_STALE_BACKUPS = "notify_for_stale_snapshots"
    DEPRECTAED_ENABLE_BACKUP_STALE_SENSOR = "enable_snapshot_stale_sensor"
    DEPRECTAED_ENABLE_BACKUP_STATE_SENSOR = "enable_snapshot_state_sensor"

    def default(self):
        if "staging" in VERSION and self in _STAGING_DEFAULTS:
            return _STAGING_DEFAULTS[self]
        return _DEFAULTS[self]

    def validator(self):
        return _VALIDATORS[self]

    def key(self):
        return self.value


_DEFAULTS = {
    Setting.MAX_BACKUPS_IN_HA: 4,
    Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE: 4,
    Setting.DAYS_BETWEEN_BACKUPS: 3,
    Setting.IGNORE_OTHER_BACKUPS: False,
    Setting.IGNORE_UPGRADE_BACKUPS: False,
    Setting.DELETE_IGNORED_AFTER_DAYS: 0,
    Setting.DELETE_BEFORE_NEW_BACKUP: False,
    Setting.BACKUP_NAME: "{type} Backup {year}-{month}-{day} {hr24}:{min}:{sec}",
    Setting.BACKUP_TIME_OF_DAY: "",
    Setting.SPECIFY_BACKUP_FOLDER: False,
    Setting.NOTIFY_FOR_STALE_BACKUPS: True,
    Setting.ENABLE_BACKUP_STALE_SENSOR: True,
    Setting.ENABLE_BACKUP_STATE_SENSOR: True,
    Setting.BACKUP_PASSWORD: "",

    # Basic backup settings
    Setting.DEPRECTAED_MAX_BACKUPS_IN_HA: 4,
    Setting.DEPRECTAED_MAX_BACKUPS_IN_GOOGLE_DRIVE: 4,
    Setting.DEPRECATED_DAYS_BETWEEN_BACKUPS: 3,
    Setting.DEPRECTAED_IGNORE_OTHER_BACKUPS: False,
    Setting.DEPRECTAED_IGNORE_UPGRADE_BACKUPS: False,
    Setting.DEPRECTAED_BACKUP_TIME_OF_DAY: "",
    Setting.DEPRECTAED_BACKUP_NAME: "{type} Snapshot {year}-{month}-{day} {hr24}:{min}:{sec}",
    Setting.DEPRECATED_BACKUP_PASSWORD: "",
    Setting.DEPRECTAED_SPECIFY_BACKUP_FOLDER: False,
    Setting.WARN_FOR_LOW_SPACE: True,
    Setting.LOW_SPACE_THRESHOLD: 1024 * 1024 * 1024,
    Setting.DELETE_AFTER_UPLOAD: False,
    Setting.DEPRECTAED_DELETE_BEFORE_NEW_BACKUP: False,
    Setting.CALL_BACKUP_SNAPSHOT: False,

    # Generational backup settings
    Setting.GENERATIONAL_DAYS: 0,
    Setting.GENERATIONAL_WEEKS: 0,
    Setting.GENERATIONAL_MONTHS: 0,
    Setting.GENERATIONAL_YEARS: 0,
    Setting.GENERATIONAL_DAY_OF_WEEK: "mon",
    Setting.GENERATIONAL_DAY_OF_MONTH: 1,
    Setting.GENERATIONAL_DAY_OF_YEAR: 1,
    Setting.GENERATIONAL_DELETE_EARLY: False,

    # Partial backup settings
    Setting.EXCLUDE_FOLDERS: "",
    Setting.EXCLUDE_ADDONS: "",

    Setting.STOP_ADDONS: "",
    Setting.DISABLE_WATCHDOG_WHEN_STOPPING: False,

    # UI Server settings
    Setting.USE_SSL: False,
    Setting.REQUIRE_LOGIN: False,
    Setting.EXPOSE_EXTRA_SERVER: False,
    Setting.CERTFILE: "/ssl/fullchain.pem",
    Setting.KEYFILE: "/ssl/privkey.pem",
    Setting.INGRESS_PORT: 8099,
    Setting.PORT: 1627,

    # Add-on options
    Setting.DEPRECTAED_NOTIFY_FOR_STALE_BACKUPS: True,
    Setting.DEPRECTAED_ENABLE_BACKUP_STALE_SENSOR: True,
    Setting.DEPRECTAED_ENABLE_BACKUP_STATE_SENSOR: True,
    Setting.SEND_ERROR_REPORTS: False,
    Setting.VERBOSE: False,
    Setting.CONFIRM_MULTIPLE_DELETES: True,
    Setting.ENABLE_DRIVE_UPLOAD: True,

    # Theme Settings
    Setting.BACKGROUND_COLOR: "#ffffff",
    Setting.ACCENT_COLOR: "#03a9f4",

    # Network and DNS settings
    Setting.ALTERNATE_DNS_SERVERS: "8.8.8.8,8.8.4.4",
    Setting.DRIVE_EXPERIMENTAL: False,
    Setting.DRIVE_IPV4: "",
    Setting.IGNORE_IPV6_ADDRESSES: False,
    Setting.GOOGLE_DRIVE_TIMEOUT_SECONDS: 180,
    Setting.GOOGLE_DRIVE_PAGE_SIZE: 100,
    Setting.MAXIMUM_UPLOAD_CHUNK_BYTES: 10 * 1024 * 1024,

    # Remote endpoints
    Setting.AUTHORIZATION_HOST: "https://habackup.io",
    Setting.TOKEN_SERVER_HOSTS: "https://token1.habackup.io,https://habackup.io",
    Setting.SUPERVISOR_URL: "",
    Setting.SUPERVISOR_TOKEN: "",
    Setting.DRIVE_URL: "https://www.googleapis.com",
    Setting.DRIVE_REFRESH_URL: "https://www.googleapis.com/oauth2/v4/token",
    Setting.DRIVE_AUTHORIZE_URL: "https://accounts.google.com/o/oauth2/v2/auth",
    Setting.DRIVE_DEVICE_CODE_URL: "https://oauth2.googleapis.com/device/code",
    Setting.DRIVE_TOKEN_URL: "https://oauth2.googleapis.com/token",
    Setting.DRIVE_HOST_NAME: "www.googleapis.com",
    Setting.SAVE_DRIVE_CREDS_PATH: "token",

    # File locations used to store things
    Setting.FOLDER_FILE_PATH: "/data/folder.dat",
    Setting.CREDENTIALS_FILE_PATH: "/data/credentials.dat",
    Setting.BACKUP_DIRECTORY_PATH: "/backup",
    Setting.RETAINED_FILE_PATH: "/data/retained.json",
    Setting.SECRETS_FILE_PATH: "/config/secrets.yaml",
    Setting.INGRESS_TOKEN_FILE_PATH: "/data/ingress.dat",
    Setting.CONFIG_FILE_PATH: "/data/options.json",
    Setting.ID_FILE_PATH: "/data/id.json",
    Setting.STOP_ADDON_STATE_PATH: '/data/stop_addon_state.json',
    Setting.DATA_CACHE_FILE_PATH: '/data/data_cache.json',

    # Various timeouts and intervals
    Setting.BACKUP_STALE_SECONDS: 60 * 60 * 3,
    Setting.PENDING_BACKUP_TIMEOUT_SECONDS: 60 * 60 * 5,
    Setting.FAILED_BACKUP_TIMEOUT_SECONDS: 60 * 15,
    Setting.NEW_BACKUP_TIMEOUT_SECONDS: 5,
    Setting.MAX_SYNC_INTERVAL_SECONDS: 60 * 60,
    Setting.DEFAULT_DRIVE_CLIENT_ID: "933944288016-n35gnn2juc76ub7u5326ls0iaq9dgjgu.apps.googleusercontent.com",
    Setting.DEFAULT_DRIVE_CLIENT_SECRET: "",
    Setting.DRIVE_PICKER_API_KEY: "",
    Setting.DEFAULT_CHUNK_SIZE: 1024 * 1024 * 5,
    Setting.DOWNLOAD_TIMEOUT_SECONDS: 60,
    Setting.DEBUGGER_PORT: None,
    Setting.SERVER_PROJECT_ID: "",
    Setting.LOG_LEVEL: 'DEBUG',
    Setting.CONSOLE_LOG_LEVEL: 'INFO',
    Setting.BACKUP_STARTUP_DELAY_MINUTES: 10,
    Setting.EXCHANGER_TIMEOUT_SECONDS: 10
}

_STAGING_DEFAULTS = {
    Setting.AUTHORIZATION_HOST: "https://dev.habackup.io",
    Setting.TOKEN_SERVER_HOSTS: "https://token1.dev.habackup.io,https://dev.habackup.io",
    Setting.DEFAULT_DRIVE_CLIENT_ID: "795575624694-jcdhoh1jr1ngccfsbi2f44arr4jupl79.apps.googleusercontent.com",
}

_CONFIG = {
    Setting.MAX_BACKUPS_IN_HA: "int(0,)?",
    Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE: "int(0,)?",
    Setting.DAYS_BETWEEN_BACKUPS: "float(0,)?",
    Setting.IGNORE_OTHER_BACKUPS: "bool?",
    Setting.IGNORE_UPGRADE_BACKUPS: "bool?",
    Setting.DELETE_IGNORED_AFTER_DAYS: "float(0,)?",
    Setting.DELETE_BEFORE_NEW_BACKUP: "bool?",
    Setting.BACKUP_NAME: "str?",
    Setting.BACKUP_TIME_OF_DAY: "match(^[0-2]\\d:[0-5]\\d$)?",
    Setting.SPECIFY_BACKUP_FOLDER: "bool?",
    Setting.NOTIFY_FOR_STALE_BACKUPS: "bool?",
    Setting.ENABLE_BACKUP_STALE_SENSOR: "bool?",
    Setting.ENABLE_BACKUP_STATE_SENSOR: "bool?",
    Setting.BACKUP_PASSWORD: "str?",

    # Basic backup settings
    Setting.DEPRECTAED_MAX_BACKUPS_IN_HA: "int(0,)?",
    Setting.DEPRECTAED_MAX_BACKUPS_IN_GOOGLE_DRIVE: "int(0,)?",
    Setting.DEPRECATED_DAYS_BETWEEN_BACKUPS: "float(0,)?",
    Setting.DEPRECTAED_IGNORE_OTHER_BACKUPS: "bool?",
    Setting.DEPRECTAED_IGNORE_UPGRADE_BACKUPS: "bool?",
    Setting.DEPRECTAED_BACKUP_TIME_OF_DAY: "match(^[0-2]\\d:[0-5]\\d$)?",
    Setting.DEPRECTAED_BACKUP_NAME: "str?",
    Setting.DEPRECATED_BACKUP_PASSWORD: "str?",
    Setting.DEPRECTAED_SPECIFY_BACKUP_FOLDER: "bool?",
    Setting.WARN_FOR_LOW_SPACE: "bool?",
    Setting.LOW_SPACE_THRESHOLD: "int(0,)?",
    Setting.DELETE_AFTER_UPLOAD: "bool?",
    Setting.DEPRECTAED_DELETE_BEFORE_NEW_BACKUP: "bool?",
    Setting.CALL_BACKUP_SNAPSHOT: "bool?",

    # Generational backup settings
    Setting.GENERATIONAL_DAYS: "int(0,)?",
    Setting.GENERATIONAL_WEEKS: "int(0,)?",
    Setting.GENERATIONAL_MONTHS: "int(0,)?",
    Setting.GENERATIONAL_YEARS: "int(0,)?",
    Setting.GENERATIONAL_DAY_OF_WEEK: "match(^(mon|tue|wed|thu|fri|sat|sun)$)?",
    Setting.GENERATIONAL_DAY_OF_MONTH: "int(1,31)?",
    Setting.GENERATIONAL_DAY_OF_YEAR: "int(1,365)?",
    Setting.GENERATIONAL_DELETE_EARLY: "bool?",

    # Partial backup settings
    Setting.EXCLUDE_FOLDERS: "str?",
    Setting.EXCLUDE_ADDONS: "str?",

    Setting.STOP_ADDONS: "str?",
    Setting.DISABLE_WATCHDOG_WHEN_STOPPING: "bool?",

    # UI Server settings
    Setting.USE_SSL: "bool?",
    Setting.REQUIRE_LOGIN: "bool?",
    Setting.EXPOSE_EXTRA_SERVER: "bool?",
    Setting.CERTFILE: "str?",
    Setting.KEYFILE: "str?",
    Setting.INGRESS_PORT: "int(0,)?",
    Setting.PORT: "int(0,)?",

    # Add-on options
    Setting.DEPRECTAED_NOTIFY_FOR_STALE_BACKUPS: "bool?",
    Setting.DEPRECTAED_ENABLE_BACKUP_STALE_SENSOR: "bool?",
    Setting.DEPRECTAED_ENABLE_BACKUP_STATE_SENSOR: "bool?",
    Setting.SEND_ERROR_REPORTS: "bool?",
    Setting.VERBOSE: "bool?",
    Setting.CONFIRM_MULTIPLE_DELETES: "bool?",
    Setting.ENABLE_DRIVE_UPLOAD: "bool?",

    # Theme Settings
    Setting.BACKGROUND_COLOR: "match(^(#[0-9ABCDEFabcdef]{6}|)$)?",
    Setting.ACCENT_COLOR: "match(^(#[0-9ABCDEFabcdef]{6}|)$)?",

    # Network and DNS settings
    Setting.ALTERNATE_DNS_SERVERS: "match(^([0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3})(,[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3})*$)?",
    Setting.DRIVE_EXPERIMENTAL: "bool?",
    Setting.DRIVE_IPV4: "match(^[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}$)?",
    Setting.IGNORE_IPV6_ADDRESSES: "bool?",
    Setting.GOOGLE_DRIVE_TIMEOUT_SECONDS: "float(1,)?",
    Setting.GOOGLE_DRIVE_PAGE_SIZE: "int(1,)?",
    Setting.MAXIMUM_UPLOAD_CHUNK_BYTES: f"float({1024 * 256},)?",

    # Remote endpoints
    Setting.AUTHORIZATION_HOST: "url?",
    Setting.TOKEN_SERVER_HOSTS: "str?",
    Setting.SUPERVISOR_URL: "url?",
    Setting.SUPERVISOR_TOKEN: "str?",
    Setting.DRIVE_URL: "url?",
    Setting.DRIVE_REFRESH_URL: "url?",
    Setting.DRIVE_AUTHORIZE_URL: "url?",
    Setting.DRIVE_DEVICE_CODE_URL: "url?",
    Setting.DRIVE_TOKEN_URL: "url?",
    Setting.DRIVE_HOST_NAME: "str?",
    Setting.SAVE_DRIVE_CREDS_PATH: "str?",

    # File locations used to store things
    Setting.FOLDER_FILE_PATH: "str?",
    Setting.CREDENTIALS_FILE_PATH: "str?",
    Setting.BACKUP_DIRECTORY_PATH: "str?",
    Setting.RETAINED_FILE_PATH: "str?",
    Setting.SECRETS_FILE_PATH: "str?",
    Setting.INGRESS_TOKEN_FILE_PATH: "str?",
    Setting.CONFIG_FILE_PATH: "str?",
    Setting.ID_FILE_PATH: "str?",
    Setting.STOP_ADDON_STATE_PATH: "str?",
    Setting.DATA_CACHE_FILE_PATH: "str?",

    # Various timeouts and intervals
    Setting.BACKUP_STALE_SECONDS: "float(0,)?",
    Setting.PENDING_BACKUP_TIMEOUT_SECONDS: "float(0,)?",
    Setting.FAILED_BACKUP_TIMEOUT_SECONDS: "float(0,)?",
    Setting.NEW_BACKUP_TIMEOUT_SECONDS: "float(0,)?",
    Setting.MAX_SYNC_INTERVAL_SECONDS: "float(300,)?",
    Setting.DEFAULT_DRIVE_CLIENT_ID: "str?",
    Setting.DEFAULT_DRIVE_CLIENT_SECRET: "str?",
    Setting.DRIVE_PICKER_API_KEY: "str?",
    Setting.DEFAULT_CHUNK_SIZE: "int(1,)?",
    Setting.DOWNLOAD_TIMEOUT_SECONDS: "float(0,)?",
    Setting.DEBUGGER_PORT: "int(100,)?",
    Setting.SERVER_PROJECT_ID: "str?",
    Setting.LOG_LEVEL: "list(DEBUG|TRACE|INFO|WARN|CRITICAL|WARNING)?",
    Setting.CONSOLE_LOG_LEVEL: "list(DEBUG|TRACE|INFO|WARN|CRITICAL|WARNING)?",
    Setting.BACKUP_STARTUP_DELAY_MINUTES: "float(0,)?",
    Setting.EXCHANGER_TIMEOUT_SECONDS: "float(0,)?"
}

PRIVATE = [
    Setting.DEPRECATED_BACKUP_PASSWORD,
    Setting.DEPRECTAED_BACKUP_NAME,
    Setting.BACKUP_PASSWORD,
    Setting.BACKUP_NAME
]

_LOOKUP = {}
_VALIDATORS = {}


def getValidator(name, schema):
    if schema.endswith("?"):
        schema = schema[:-1]
    if schema.startswith("int("):
        # its a int
        parts = schema[4:-1]
        minimum = None
        maximum = None
        if parts.endswith(","):
            minimum = int(parts[0:-1])
        elif parts.startswith(","):
            maximum = int(parts[1:])
        else:
            digits = parts.split(",")
            minimum = int(digits[0])
            maximum = int(digits[1])
        return IntValidator(name, minimum, maximum)
    elif schema.startswith("float("):
        # its a float
        parts = schema[6:-1]
        minimum = None
        maximum = None
        if parts.endswith(","):
            minimum = float(parts[0:-1])
        elif parts.startswith(","):
            maximum = float(parts[1:])
        else:
            digits = parts.split(",")
            minimum = float(digits[0])
            maximum = float(digits[1])
        return FloatValidator(name, minimum, maximum)
    elif schema.startswith("bool"):
        # its a bool
        return BoolValidator(name)
    elif schema.startswith("str") or schema.startswith("url"):
        # its a url (treat it just like any string)
        return StringValidator(name)
    elif schema.startswith("match("):
        return RegexValidator(name, schema[6:-1])
    elif schema.startswith("list("):
        return ListValidator(name, schema[5:-1].split("|"))
    else:
        raise Exception("Invalid schema: " + schema)


# initalize validators
for setting in Setting:
    _LOOKUP[setting.value] = setting

with open(abspath(join(__file__, "..", "..", "..", "config.json"))) as f:
    addon_config = json.load(f)

for setting in Setting:
    _VALIDATORS[setting] = getValidator(setting.value, _CONFIG[setting])
# for key in addon_config["schema"]:
#     _VALIDATORS[_LOOKUP[key]] = getValidator(key, addon_config["schema"][key])

_VALIDATORS[Setting.MAX_SYNC_INTERVAL_SECONDS] = DurationAsStringValidator("max_sync_interval_seconds", minimum=1, maximum=None)
_VALIDATORS[Setting.DELETE_IGNORED_AFTER_DAYS] = DurationAsStringValidator("delete_ignored_after_days", minimum=0, maximum=None, base_seconds=60 * 60 * 24, default_as_empty=0)
_VALIDATORS[Setting.MAXIMUM_UPLOAD_CHUNK_BYTES] = BytesizeAsStringValidator("maximum_upload_chunk_bytes", minimum=256 * 1024)
VERSION = addon_config["version"]


def isStaging():
    return "staging" in VERSION
