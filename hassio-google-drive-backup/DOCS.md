# Home Assistant Add-on: Google Assistant SDK

## Installation

To install the add-on, first follow the installation steps from the [README on GitHub](https://github.com/sabeechen/hassio-google-drive-backup#installation).

## Configuration

_Note_: The configuration can be changed easily by starting the add-on and clicking `Settings` in the web UI.
The UI explains what each setting is and you don't need to modify anything before clicking `Start`.
If you would still prefer to modify the settings in yaml, the options are detailed below.

Add-on configuration example. Don't use this directly, the addon has a lot of configuration options that most users don't need or want:

```yaml
# Keep 10 backups in Home Assistant
max_backups_in_ha: 10

# Keep 10 backups in Google Drive
max_backups_in_google_drive: 10

# Ignore backups the add-on hasn't created
ignore_other_backups: True

# Ignore backups that look like they were created by Home Assistant automatic backup option during upgrades
ignore_upgrade_backups: True

# Automatically delete "ignored" snapshots after this many days
delete_ignored_after_days: 7

# Take a backup every 3 days
days_between_backups: 3

# Create backups at 1:30pm exactly
backup_time_of_day: "13:30"

# Delete backups from Home Assistant immediately after uploading them to Google Drive
delete_after_upload: True

# Manually specify the backup folder used in Google Drive
specify_backup_folder: true

# Use a dark and red theme
background_color: "#242424"
accent_color: "#7D0034"

# Use a password for backup archives.  Use "!secret secret_name" to use a password form your secrets file
backup_password: "super_secret"

# Create backup names like 'Full Backup HA 0.92.0'
backup_name: "{type} Backup HA {version_ha}"

# Keep a backup once every day for 3 days and once a week for 4 weeks
generational_days: 3
generational_weeks: 4

# Create partial backups with no folders and no configurator add-on
exclude_folders: "homeassistant,ssl,share,addons/local,media"
exclude_addons: "core_configurator"

# Turn off notifications and staleness sensor
enable_backup_stale_sensor: false
notify_for_stale_backups: false

# Enable server directly on port 1627
expose_extra_server: true

# Allow sending error reports
send_error_reports: true

# Delete backups after they're uploaded to Google Drive
delete_after_upload: true
```

### Option: `max_backups_in_ha` (default: 4)

The number of backups the add-on will allow Home Assistant to store locally before old ones are deleted.

### Option: `max_backups_in_google_drive` (default: 4)

The number of backups the add-on will keep in Google Drive before old ones are deleted. Google Drive gives you 15GB of free storage (at the time of writing) so plan accordingly if you know how big your backups are.

### Option: `ignore_other_backups` (default: False)
Make the addon ignore any backups it didn't directly create.  Any backup already uploaded to Google Drive will not be ignored until you delete it from Google Drive.

### Option: `ignore_upgrade_backups` (default: False)
Ignores backups that look like they were automatically created from updating an add-on or Home Assistant itself.  This will make the add-on ignore any partial backup that has only one add-on or folder in it.

### Option: `days_between_backups` (default: 3)

How often a new backup should be scheduled, eg `1` for daily and `7` for weekly.

### Option: `backup_time_of_day`

The time of day (local time) that new backups should be created in 24-hour ("HH:MM") format. When not specified backups are created at (roughly) the same time of day as the most recent backup.


### Options: `delete_after_upload` (default: False)

Deletes backups from Home Assistant immediately after uploading them to Google Drive.  This is useful if you have very limited space inside Home Assistant since you only need to have available space for a single backup locally.

### Option: `specify_backup_folder` (default: False)

When true, you must select the folder in Google Drive where backups are stored. Once you turn this on, restart the add-on and visit the Web-UI to be prompted to select the backup folder.

### Option: `background_color` and `accent_color`

The background and accent colors for the web UI. You can use this to make the UI fit in with whatever color scheme you use in Home Assistant. When unset, the interface matches Home Assistant's default blue/white style.

### Option: `backup_password`

When set, backups are created with a password. You can use a value from your secrets.yaml by prefixing the password with "!secret". You'll need to remember this password when restoring a backup.

> Example: Use a password for backup archives
>
> ```yaml
> backup_password: "super_secret"
> ```
>
> Example: Use a password from secrets.yaml
>
> ```yaml
> backup_password: "!secret backup_password"
> ```

### Option: `backup_name` (default: "{type} Backup {year}-{month}-{day} {hr24}:{min}:{sec}")

Sets the name for new backups. Variable parameters of the form `{variable_name}` can be used to modify the name to your liking. A list of available variables is available [here](https://github.com/sabeechen/hassio-google-drive-backup#can-i-give-backups-a-different-name).

### Option: `generational_*`

When set, older backups will be kept longer using a [generational backup scheme](https://en.wikipedia.org/wiki/Backup_rotation_scheme). See the [question here](https://github.com/sabeechen/hassio-google-drive-backup#can-i-keep-older-backups-for-longer) for configuration options.

### Option: `exclude_folders`

When set, excludes the comma-separated list of folders by creating a partial backup.

### Option: `exclude_addons`

When set, excludes the comma-separated list of addons by creating a partial backup.

_Note_: Folders and add-ons must be identified by their "slug" name. It is recommended to use the `Settings` dialog within the add-on web UI to configure partial backups since these names are esoteric and hard to find.

### Option: `enable_backup_stale_sensor` (default: True)

When false, the add-on will not publish the [binary_sensor.backups_stale](https://github.com/sabeechen/hassio-google-drive-backup#how-will-i-know-this-will-be-there-when-i-need-it) stale sensor.

### Option: `enable_backup_state_sensor` (default: True)

When false, the add-on will not publish the [sensor.backup_state](https://github.com/sabeechen/hassio-google-drive-backup#how-will-i-know-this-will-be-there-when-i-need-it) sensor.

### Option: `notify_for_stale_backups` (default: True)

When false, the add-on will send a [persistent notification](https://github.com/sabeechen/hassio-google-drive-backup#how-will-i-know-this-will-be-there-when-i-need-it) in Home Assistant when backups are stale.

---

### UI Server Options

The UI is available through Home Assistant [ingress](https://www.home-assistant.io/blog/2019/04/15/hassio-ingress/).

It can also be exposed through a web server on port `1627`, which you can map to an externally visible port from the add-on `Network` panel. You can configure a few more options to add SSL or require your Home Assistant username/password.

#### Option: `expose_extra_server` (default: False)

Expose the webserver on port `1627`. This is optional, as the add-on is already available with Home Assistant ingress.

#### Option: `require_login` (default: False)

When true, requires your home assistant username and password to access the Web UI.

#### Option: `use_ssl` (default: False)

When true, requires your home assistant username and password to access the Web UI.

#### Option: `certfile` (default: `/ssl/certfile.pem`)

Required when `use_ssl: True`. The path to your SSL key file

#### Option: `keyfile` (default: `/ssl/keyfile.pem`)

Required when `use_ssl: True`. The path to your SSL cert file.

#### Option: `verbose` (default: False)

If true, enable additional debug logging. Useful if you start seeing errors and need to file a bug with me.

#### Option: `send_error_reports` (default: False)

When true, the text of unexpected errors will be sent to a database maintained by the developer. This helps identify problems with new releases and provide better context messages when errors come up.

#### Option: `delete_after_upload` (default: False)

When true, backups are always deleted after they've been uploaded to Google Drive.  'max_backups_in_ha' is ignored when this option is True, since a backup is always deleted from Home Assistant after it gets uploaded to Google Drive.  Some find this useful if they only have enough space on their Home Assistant machine for one backup.

## FAQ

Read the [FAQ on GitHub](https://github.com/sabeechen/hassio-google-drive-backup#faq).
