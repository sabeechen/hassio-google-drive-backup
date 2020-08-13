
SOURCE_GOOGLE_DRIVE = "GoogleDrive"
SOURCE_HA = "HomeAssistant"

ERROR_PLEASE_WAIT = "please_wait"
ERROR_NOT_UPLOADABLE = "not_uploadable"
ERROR_NO_SNAPSHOT = "invalid_slug"
ERROR_CREDS_EXPIRED = "creds_bad"
ERROR_UPLOAD_FAILED = "upload_failed"
ERROR_BAD_PASSWORD_KEY = "password_key_invalid"
ERROR_SNAPSHOT_IN_PROGRESS = "snapshot_in_progress"
ERROR_PROTOCOL = "protocol_error"
ERROR_LOGIC = "logic_error"
ERROR_INVALID_CONFIG = "illegal_config"
ERROR_DRIVE_FULL = "drive_full"
ERROR_GOOGLE_DNS = "google_dns"
ERROR_GOOGLE_CONNECT = "google_cant_connect"
ERROR_GOOGLE_INTERNAL = "google_server_error"
ERROR_GOOGLE_SESSION = "google_session_expired"
ERROR_GOOGLE_TIMEOUT = "google_timeout"
ERROR_HA_DELETE_ERROR = "delete_error"
ERROR_MULTIPLE_DELETES = "multiple_deletes"

ERROR_EXISTING_FOLDER = "existing_backup_folder"
ERROR_BACKUP_FOLDER_MISSING = "backup_folder_missing"
CHOOSE_BACKUP_FOLDER = "choose_backup_folder"
ERROR_BACKUP_FOLDER_INACCESSIBLE = "backup_folder_inaccessible"
ERROR_LOW_SPACE = "low_space"
LOG_IN_TO_DRIVE = "log_in_to_drive"

DRIVE_FOLDER_URL_FORMAT = "https://drive.google.com/drive/u/0/folders/{0}"
GITHUB_ISSUE_URL = "https://github.com/sabeechen/hassio-google-drive-backup/issues/new?labels[]=People%20Management&labels[]=[Type]%20Bug&title={title}&assignee=sabeechen&body={body}"
GITHUB_BUG_TEMPLATE = """
###### Description:
```
If you have anything else that could help explain what happened, click "Markdown" above and write it here.
```

 Addon version: `{version}`
 Home Assistant Version: `{ha_version}`
 Supervisor Version: `{super_version}`
 Architecture: `{arch}`
 Date: `{time}`
 Timezone: `{timezone}`
 Failure Time: `{failure_time}`
 Last Good Sync: `{sync_last_start}`
 ###### Exception:
 ```
 {error}
 ```
 Snapshots:
 ```
 {snapshots}
 ```
 ###### Config:
 ```
 {config}
 ```
 ###### Addon Logs:
 ```
 {addon_logs}
 ```
 ###### Supervisor Logs:
 ```
 {super_logs}
 ```
 ###### Home Assistant Core Logs:
 ```
 {core_logs}
 ```
 """
