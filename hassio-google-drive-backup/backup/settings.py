import json
from enum import Enum, unique
from .validation import BoolValidator, FloatValidator, IntValidator, StringValidator, RegexValidator
from os.path import join, abspath


@unique
class Setting(Enum):
    # Basic snapshot settings
    MAX_SNAPSHOTS_IN_HASSIO = "max_snapshots_in_hassio"
    MAX_SNAPSHOTS_IN_GOOGLE_DRIVE = "max_snapshots_in_google_drive"
    DAYS_BETWEEN_SNAPSHOTS = "days_between_snapshots"
    SNAPSHOT_NAME = "snapshot_name"
    SNAPSHOT_TIME_OF_DAY = "snapshot_time_of_day"
    SNAPSHOT_PASSWORD = "snapshot_password"

    # generational settings
    GENERATIONAL_DAYS = "generational_days"
    GENERATIONAL_WEEKS = "generational_weeks"
    GENERATIONAL_MONTHS = "generational_months"
    GENERATIONAL_YEARS = "generational_years"
    GENERATIONAL_DAY_OF_WEEK = "generational_day_of_week"
    GENERATIONAL_DAY_OF_MONTH = "generational_day_of_month"
    GENERATIONAL_DAY_OF_YEAR = "generational_day_of_year"
    GENERATIONAL_DELETE_EARLY = "generational_delete_early"

    # Partial snapshots
    EXCLUDE_FOLDERS = "exclude_folders"
    EXCLUDE_ADDONS = "exclude_addons"

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
    NOTIFY_FOR_STALE_SNAPSHOTS = "notify_for_stale_snapshots"
    ENABLE_SNAPSHOT_STALE_SENSOR = "enable_snapshot_stale_sensor"
    ENABLE_SNAPSHOT_STATE_SENSOR = "enable_snapshot_state_sensor"
    SEND_ERROR_REPORTS = "send_error_reports"
    CONFIRM_MULTIPLE_DELETES = "confirm_multiple_deletes"

    # Network and dns stuff
    DRIVE_EXPERIMENTAL = "drive_experimental"
    DRIVE_IPV4 = "drive_ipv4"
    IGNORE_IPV6_ADDRESSES = "ignore_ipv6_addresses"
    GOOGLE_DRIVE_TIMEOUT_SECONDS = "google_drive_timeout_seconds"
    GOOGLE_DRIVE_PAGE_SIZE = "google_drive_page_size"
    ALTERNATE_DNS_SERVERS = "alternate_dns_servers"

    # Files and folders
    FOLDER_FILE_PATH = "folder_file_path"
    CREDENTIALS_FILE_PATH = "credentials_file_path"
    RETAINED_FILE_PATH = "retained_file_path"
    SECRETS_FILE_PATH = "secrets_file_path"
    BACKUP_DIRECTORY_PATH = "backup_directory_path"

    # enpoints
    HASSIO_URL = "hassio_url"
    DRIVE_URL = "drive_url"
    HOME_ASSISTANT_URL = "home_assistant_url"
    HASSIO_TOKEN = "hassio_header"
    AUTHENTICATE_URL = "authenticate_url"

    # Timing and timeouts
    MAX_SYNC_INTERVAL_SECONDS = "max_sync_interval_seconds"
    SNAPSHOT_STALE_SECONDS = "snapshot_stale_seconds"
    PENDING_SNAPSHOT_TIMEOUT_SECONDS = "pending_snapshot_timeout_seconds"
    FAILED_SNAPSHOT_TIMEOUT_SECONDS = "failed_snapshot_timeout_seconds"
    NEW_SNAPSHOT_TIMEOUT_SECONDS = "new_snapshot_timeout_seconds"

    def default(self):
        return _DEFAULTS[self]

    def validator(self):
        return _VALIDATORS[self]

    def key(self):
        return self.value


_DEFAULTS = {
    # Basic snapshot settings
    Setting.MAX_SNAPSHOTS_IN_HASSIO: 4,
    Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE: 4,
    Setting.DAYS_BETWEEN_SNAPSHOTS: 3,
    Setting.SNAPSHOT_TIME_OF_DAY: "",
    Setting.SNAPSHOT_NAME: "{type} Snapshot {year}-{month}-{day} {hr24}:{min}:{sec}",
    Setting.SNAPSHOT_PASSWORD: "",

    # Generational backup settings
    Setting.GENERATIONAL_DAYS: 0,
    Setting.GENERATIONAL_WEEKS: 0,
    Setting.GENERATIONAL_MONTHS: 0,
    Setting.GENERATIONAL_YEARS: 0,
    Setting.GENERATIONAL_DAY_OF_WEEK: "mon",
    Setting.GENERATIONAL_DAY_OF_MONTH: 1,
    Setting.GENERATIONAL_DAY_OF_YEAR: 1,
    Setting.GENERATIONAL_DELETE_EARLY: False,

    # Partial snapshot settings
    Setting.EXCLUDE_FOLDERS: "",
    Setting.EXCLUDE_ADDONS: "",

    # UI Server settings
    Setting.USE_SSL: False,
    Setting.REQUIRE_LOGIN: False,
    Setting.EXPOSE_EXTRA_SERVER: True,
    Setting.CERTFILE: "/ssl/fullchain.pem",
    Setting.KEYFILE: "/ssl/privkey.pem",
    Setting.INGRESS_PORT: 8099,
    Setting.PORT: 1627,

    # Add-on options
    Setting.NOTIFY_FOR_STALE_SNAPSHOTS: True,
    Setting.ENABLE_SNAPSHOT_STALE_SENSOR: True,
    Setting.ENABLE_SNAPSHOT_STATE_SENSOR: True,
    Setting.SEND_ERROR_REPORTS: False,
    Setting.VERBOSE: False,
    Setting.CONFIRM_MULTIPLE_DELETES: True,

    # Network and DNS settings
    Setting.ALTERNATE_DNS_SERVERS: "8.8.8.8,8.8.4.4",
    Setting.DRIVE_EXPERIMENTAL: False,
    Setting.DRIVE_IPV4: "",
    Setting.IGNORE_IPV6_ADDRESSES: False,
    Setting.GOOGLE_DRIVE_TIMEOUT_SECONDS: 180,
    Setting.GOOGLE_DRIVE_PAGE_SIZE: 100,

    # Remote endpoints
    Setting.HASSIO_URL: "http://hassio/",
    Setting.HASSIO_TOKEN: "",
    Setting.HOME_ASSISTANT_URL: "http://hassio/homeassistant/api/",
    Setting.DRIVE_URL: "https://www.googleapis.com",
    Setting.AUTHENTICATE_URL: "https://philosophyofpen.com/login/backup.py",

    # File locations used to store things
    Setting.FOLDER_FILE_PATH: "/data/folder.dat",
    Setting.CREDENTIALS_FILE_PATH: "/data/credentials.dat",
    Setting.BACKUP_DIRECTORY_PATH: "/backup",
    Setting.RETAINED_FILE_PATH: "/data/retained.json",
    Setting.SECRETS_FILE_PATH: "/config/secrets.yaml",

    # Various timeouts and intervals
    Setting.SNAPSHOT_STALE_SECONDS: 60 * 60 * 3,
    Setting.PENDING_SNAPSHOT_TIMEOUT_SECONDS: 60 * 60 * 3,
    Setting.FAILED_SNAPSHOT_TIMEOUT_SECONDS: 60 * 30,
    Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS: 5,
    Setting.MAX_SYNC_INTERVAL_SECONDS: 60 * 60,
}

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
    else:
        raise Exception("Invalid schema: " + schema)


# initalize validators
for setting in Setting:
    _LOOKUP[setting.value] = setting

with open(abspath(join(__file__, "..", "..", "config.json"))) as f:
    addon_config = json.load(f)
for key in addon_config["schema"]:
    _VALIDATORS[_LOOKUP[key]] = getValidator(key, addon_config["schema"][key])
