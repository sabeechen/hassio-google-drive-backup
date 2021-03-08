# Home Assistant Add-on: Google Assistant SDK

## Installation

To install the add-on, first follow the installation steps from the [README on GitHub](https://github.com/sabeechen/hassio-google-drive-backup#installation).

## Configuration

_Note_: The configuration can be changed easily by starting the add-on and clicking `Settings` in the web UI.
The UI explains what each setting is and you don't need to modify anything before clicking `Start`.
If you would still prefer to modify the settings in yaml, the options are detailed below.

Add-on configuration example (do not use directly):

```yaml
# Keep 10 snapshots in Home Assistant
max_snapshots_in_hassio: 10
# Keep 10 snapshots in Google Drive
max_snapshots_in_google_drive: 10
# Take a snapshot every 3 days
days_between_snapshots: 3
# Create snapshots at 1:30pm
snapshot_time_of_day: "13:30"
# Specify the snapshot folder
specify_snapshot_folder: true
# Use a dark and red theme
background_color: "#242424"
accent_color: "#7D0034"
# Use a password for snapshot archives
snapshot_password: "super_secret"
# Create snapshot names like 'Full Snapshot HA 0.92.0'
snapshot_name: "{type} Snapshot HA {version_ha}"
# Keep a snapshot once every day for 3 days and once a week for 4 weeks
generational_days: 3
generational_weeks: 4
# Create partial snapshots with no folders and no configurator add-on
exclude_folders: "homeassistant,ssl,share,addons/local,media"
exclude_addons: "core_configurator"
# Turn off notifications and staleness sensor
enable_snapshot_stale_sensor: false
notify_for_stale_snapshots: false
# Enable server directly on port port 1627
expose_extra_server: true
# Allow sending error reports
send_error_reports: true
# Delete snapshots after they're uploaded to Google Drive
delete_after_upload: true
```

### Option: `max_snapshots_in_hassio` (default: 4)

The number of snapshots the add-on will allow Home Assistant to store locally before old ones are deleted.

### Option: `max_snapshots_in_google_drive` (default: 4)

The number of snapshots the add-on will keep in Google Drive before old ones are deleted. Google Drive gives you 15GB of free storage (at the time of writing) so plan accordingly if you know how big your snapshots are.

### Option: `days_between_snapshots` (default: 3)

How often a new snapshot should be scheduled, eg `1` for daily and `7` for weekly.

### Option: `snapshot_time_of_day`

The time of day (local time) that new snapshots should be created in 24 hour "HH:MM" format. When not specified (the default), snapshots are created at the same time of day of the most recent snapshot.

### Option: `specify_snapshot_folder` (default: False)

When true, you must select the folder in Google Drive where snapshots are stored. Once you turn this on, restart the add-on and visit the web-ui to be prompted to select the snapshot folder.

### Option: `background_color` and `accent_color`

The background and accent colors for the web UI. You can use this to make the UI fit in with whatever color scheme you use in Home Assistant. When unset, the interface matches Home Assistant's default blue/white style.

### Option: `snapshot_password`

When set, snapshots are created with a password. You can use a value from your secrets.yaml by prefixing the password with "!secret". You'll need to remember this password when restoring snapshots.

> Example: Use a password for snapshot archives
>
> ```yaml
> snapshot_password: "super_secret"
> ```
>
> Example: Use a password from secrets.yaml
>
> ```yaml
> snapshot_password: "!secret snapshot_password"
> ```

### Option: `snapshot_name` (default: "{type} Snapshot {year}-{month}-{day} {hr24}:{min}:{sec}")

Sets the name for new snapshots. Variable parameters of the form `{variable_name}` can be used to modify the name to your liking. A list of available variables are given [here](https://github.com/sabeechen/hassio-google-drive-backup#can-i-give-snapshots-a-different-name).

### Option: `generational_*`

When set, older snapshots will be kept longer using a [generational backup scheme](https://en.wikipedia.org/wiki/Backup_rotation_scheme). See the [question here](https://github.com/sabeechen/hassio-google-drive-backup#can-i-keep-older-backups-for-longer) for configuration options.

### Option: `exclude_folders`

When set, excludes the comma separated list of folders by creating a partial snapshot.

### Option: `exclude_addons`

When set, excludes the comma separated list of addons by creating a partial snapshot.

_Note_: Folders and add-ons must be identified by their "slug" name. It is recommended to use the `Settings` dialog within the add-on web UI to configure partial snapshots since these names are esoteric and hard to find.

### Option: `enable_snapshot_stale_sensor` (default: True)

When false, the add-on will not publish the [binary_sensor.snapshots](https://github.com/sabeechen/hassio-google-drive-backup#how-will-i-know-this-will-be-there-when-i-need-it) stale sensor.

### Option: `enable_snapshot_state_sensor` (default: True)

When false, the add-on will not publish the [sensor.snapshot_state](https://github.com/sabeechen/hassio-google-drive-backup#how-will-i-know-this-will-be-there-when-i-need-it) sensor.

### Option: `notify_for_stale_snapshots` (default: True)

When false, the add-on will send a [persistent notification](https://github.com/sabeechen/hassio-google-drive-backup#how-will-i-know-this-will-be-there-when-i-need-it) in Home Assistant when snapshots are stale.

---

### UI Server Options

The UI is available through Home Assistant [ingress](https://www.home-assistant.io/blog/2019/04/15/hassio-ingress/).

It can also be exposed through a webserver on port `1627`, which you can map to an externally visible port from the add-on `Network` panel. You can configure a few more options to add SSL or require your Home Assistant username/password.

#### Option: `expose_extra_server` (default: False)

Expose the webserver on port `1627`. This is optional, as the add-on is already available with Home Assistant ingress.

#### Option: `require_login` (default: False)

When true, requires your home assistant username and password to access the Web UI.

#### Option: `use_ssl` (default: False)

When true, requires your home assistant username and password to access the Web UI.

#### Option: `certfile` (default: `/ssl/certfile.pem`)

Required when `use_ssl: True`. The path to your ssl keyfile

#### Option: `keyfile` (default: `/ssl/keyfile.pem`)

Required when `use_ssl: True`. The path to your ssl certfile.

#### Option: `verbose` (default: False)

If true, enable additional debug logging. Useful if you start seeing errors and need to file a bug with me.

#### Option: `send_error_reports` (default: False)

When true, the text of unexpected errors will be sent to database maintained by the developer. This helps identify problems with new releases and provide better context messages when errors come up.

#### Option: `delete_after_upload` (default: False)

When true, snapshots are always deleted after they've been uploaded to Google Drive.  'snapshots_in_hassio' is ignored when this option is True, since a snapshot is always deleted from Home Assistant after it gets backed up to Google Drive.  Some find this useful if they only have enough space on their Home Assistant machine for one snapshot.

## FAQ

Read the [FAQ on GitHub](https://github.com/sabeechen/hassio-google-drive-backup#faq).
