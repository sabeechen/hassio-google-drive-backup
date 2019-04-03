# Changelog
## [0.6] - 2019-04-03
### Added
- Adds a config options for generational backup to keep daily, weekly, monthly, and yearly snapshots.  See the [FAQ](https://github.com/sabeechen/hassio-google-drive-backup#can-i-keep-older-backups-for-longer) on GitHub for details.
- Adds the ability to turn off automatic snapshots by setting `"days_between_snapshots": 0`
- Adds uniform logging (timestamps and level) throughout the project.
- Adds a top level menu for viewing the add-on debug logs and "simualting" backup errors.
- Adds better error messaging when Drive runs out of space or credentials are invalidated.

### Fixes
- Fixes a configuration error that caused the defualt configuration options to be invalid.

### Changes
- Delegates Google credential authentication entirely to the domain so project crednetials aren't stored in the add-on.
- Changes the "Manual" authentication workflow to requre users to generate their own client Id and client secret.

## [0.52] - 2019-03-31
### Added
- Adds a config option for fixing setting time of day snapshots should happen, try adding `"snapshot_time_of_day": "13:00"` to your config for example to schedule snapshots at 1pm.

### Fixes
- Fixes occasional error surfacing about "Snapshots already pending".
- Fixes snapshot scheduling bug that caused it to produce new snapshots as fast as it could for a few hours every day.
- Fixes errors about invalid format for timestamps sent to Google Drive.
- Fixes the lack of reporting snapshot state when Home Assistant is restarted. 

### Changes
- Changes the detailed backup sensor name from `snapshot_backup.state` to `sensor.snapshot_backup`.
- Updates the entity class of the `binary_sensor.snapshots_stale` sensor to `problem`
- If there are no snapshots when the add-on first starts up, it will not create one immediatly.

### Dev Stuff
- Smooths out kinks in the dev workflow, add linting and typing throughout the codebase.
- Added configuration examples to the documentation.

## [0.51] - 2019-03-27
- Changes line endings to UNIX format
- Fixes a mislabeled parent container for non-arm builds.

## [0.5] - 2019-03-26
Initial version released for consumption.
### Added
- First release!
- Syncing of backups from Hass.io to Google Drive
- Oauth2 authentication with Google Drive
- Periodic creation of snapshots
- Exposes sensors about backup state through the Home Assistant API
