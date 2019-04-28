## [0.93] - 2019-04-28
### Added
- Ability to choose the name for snapshots along with a bunch of template variables.
- Added the ability to give one-off snapshots a custom name and choose wether to retain them permanently in Google Drive or Home Assistant at the time of creation.
- Added some better message for some more common errors (Google Drive server errors and timeouts).

### Changes
- Error reports now contain Hassio version, Home Assistantversion , Hassos version, metrics about how long an update takes, and information abotu the DNS resolution of Google's Servers.  These are the assist in debugging outstanding issues seen in error reports.  

## [0.92] - 2019-04-26
### Added
- Ability to save snapshots indefinitely (ie protect from automatic cleanup), try it from the "ACTIONS" menu.
### Changes
- Better messaging for most common errors (Home Assistant offline, Google servers unavailable, etc)

## [0.91] - 2019-04-21

### Changes
- Snapshots now present the newest up top (ie. reverse chronologically).
- A warning icon shows up on a snapshot if its the next to be deleted when a new snapshot is created.
- Settings menu asks for confirmation if you try to leave it after making unsaved changes.
- "Getting Started" screen now tells you what is going to do after you authenticate with Google Drive with your configured settings, eg delete N old snapshots and backup M newest snapshots.  Also changed up the page's formatting to be more readable.

## [0.9] - 2019-04-19
## When updating, press CTRL+F5 on the add-on Web UI to ensure your browser sees the latest version of the add-ons scripts and style.  Otherwise the UI may render incorrectly.  This will be fixed in the next version.
### Added
- Future support for ingress has been implemented but is currently disabled for compatibility reasons.  See [this issue](https://github.com/sabeechen/hassio-google-drive-backup/issues/19) for details. 
- Added a help menu item.

### Changes
- Themed the interface in line with the default Home assistant colors.  I hope you like blue! Everything is blue.
- The UI renders with a collapsed header when embedded in an iframe.  When used with ui-panel, it looks like a native part of the home assistant interface.
- Collapsed right-side action items into a dropdown menu at the top of the page.
- Redirects now occur through javascript, which will be necessary once ingress is enabled. 
- Makes the manual authentication method a little less visible (its just behind a link)

### Fixes
- Add-on would delete and re-upload snapshots if you had a lot of newer ones sitting around in Drive and older ones sitting in Home Assistant.

## [0.8] - 2019-04-16
### Added
- Partial snapshot support.  Chose the folders and add-ons you want included in snapshots from the settings menu.
- Download snapshots form the new "Actions" menu.
- Upload snapshots directly from Google Drive with one click!
- Direct link to the restore web UI in Hass.io

### Changes
- Numerous UI tweaks.  The web-UI now renders well on any size screen (mobile-device sized included).
- Log screen now updates dynamically.

### Fixes
- A memory error for uploading very large snapshots (previously they were held in RAM).
- Snapshot status sensor displayed a convoluted string for the last snapshot, now it shows the date. 


# Changelog
## [0.7] - 2019-04-11

### Added
- Config option `snapshot_password` for password protecting snapshots.
- A settings menu within the web interface, which lets you modify the add-on's settings without having to touch json.  Try in from the upper right menu of the web-UI.
- Created an opt-in setting to allow sending error reports.  Add `"send_error_reports": true` to your config to help me out, or just clock "YES" in the dialog you see in the web UI after installing the latest version.

## [0.61] - 2019-04-03

### Fixes
- Fixes an issue the prevents Google Drive credentials from being saved during reauthentication.

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
