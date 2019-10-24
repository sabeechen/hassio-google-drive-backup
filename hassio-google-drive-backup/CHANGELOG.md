## [0.98.4] 2019-10-24
### Fixes
- Double sync at add-on startup (caused unnecessary traffic to Google Drive)
- Drive folder Id gets cached for a few minutes instead of retried with every sync.

### Changes
- Partially completed uploads will be retried for a while (resuming where they left off) instead of having to start over on transient connection errors.
- Connection errors (write timout, broken pipe, etc) now get rendered in the UI with a helful dialog.

## [0.98.3] 2019-09-10
### Fixes
- Fixed an issue causing the add-on to repeatedly attempt to create snapshots.
- Fixed a race condition that caused snapshtos to be created twice on schedule.
- The addon is now configured to startup after Home Assistant, which fixes some error messages at startup.


## [0.98.2] 2019-08-04
### Fixes
- Restore link now brings up a help dialog, since sometimes it can't resolve the url to the restore page.
- Added documentation detailing how authentication with Google Drive is accomplished and persisted.
- Fixed a potential source of error when parsing timestamps from Google Drive/Hass.io.

### Added
 - Better messaging when a snapshot in progress is blocking the add-on.


## [0.98.1] 2019-07-31
### Added
- Support for Ingress.  When upgrading from an older version, the UI will present a dialog asking if you'd still like to serve the Web UI over another port or just use ingress in the future.  New users will be ingress-only by default (this can be changed form the settings).
- Support for folders and snapshots in Team Drives.
- Settings option to disable uploads to Google Drive, for example if you just want to use the addon to create snapshots.

## [0.97.4] - 2019-05-29
- Fixes an issue where failed logins caused sync to fail.

## [0.97.3] - 2019-05-22
- Fixes a regression in drive_ipv4 override option.

## [0.97.2] - 2019-05-22
- Fixes a bug where "null" hostnames would prevent add-on startup

## [0.97.1] - 2019-05-22
### Added
- Better logging when the addon can't configure itself on startup
- Settings menau makes you confirm the password when you change it

### Fixes
- Some small UI glitches

## [0.97] - 2019-05-18
### Added
- A confrimation dialog to block backups from continuing when it attempts to delete more than one snapshot at a time.  This will help prevent misconfiguration from deleting snapshot history and can be disabled in the add-on settings.
- Add-on fails over to known good DNS servers when Google Drive's IP can't be resolved.
- Network configuration options for a hard coded IP for Google Drive, backup DNS servers, ignoring IPv6 addresses, and a timeout for Google Drive.
- Better error messages for one-off actions in the WebUI (eg changing retention, deleting snapshots)
- Better UI messaging when the snapshot password can't be found in secrets.yaml

### Changes
- Rewrote almost every line of code for the add-on with the goal of adding thorough unit tests.
- Unit tests for nearly every code path.
- Add-on now uses a custom library to reach Google Drive.
- When possible, add-on prints context-relevant log messages instead of raw stack traces.
- Addon starts a sync every time settings are changed.
- Settings are refreshed every time snapshot is taken (so you can change them from outside the settings UI)
- Avoids spamming supervisor logs by backing off attempts to reach Home Assistant when its restarting.

### Fixed
- A configuration issue that caused settings to be reverted when the addon is restarted.
- A broken link in pending snapshot
- Snapshot state sensor wouldn't update for up to an hour after HA is restarted.
- Numerous race conditions that would come up if snapshost got modified while syncing.
- A bug in generational snapshot config that could cause sync looping.

## [0.96.1] - 2019-05-05
- Fixed an issue with google credential caching in the experimental api
- Fixed overlaping top menu entries

## [0.96] - 2019-05-05
### Added
- Snapshot password can be set from your secrets file by setting the snapshot password "!sercet snapshot_password"
- Added an experimental drive backed to help resolves DNS resolution problems. See [the bug](https://github.com/sabeechen/hassio-google-drive-backup/issues/15) for details about turning it on if you're running into that problem.

### Changed
- Log timestamps are more compact now
- Silenced some underlying library INFO logging

### Fixed
- A parsing error in DNS debug info
- Some out of date info in the installation readme
- Some error handling while downloading snapshots

## [0.95] - 2019-05-03
### Added
- Better help messaging when getting errors deleting old snapshots.
### Fixes
- Inaccuracies in the installation readme.
- Could use a cached (old) Hassio/Ha/Supervisor version number for snapshot names.

## [0.94] - 2019-05-02
### Added
- Google API Server DNS info is displayed in the error dialog when you get timeouts or name reolution errors reaching Google.
### Fixes
- New snapshots would sometimes not get noticed in Hassio until an hour after they're created.


## [0.93.2] - 2019-04-28
### Fixes
- A type error when using custom names for users without hassos installed.  

## [0.93.1] - 2019-04-28
### Fixes
- A python error that shows up when you create a snapshot outside of the add-on and try to create a snapshot from within the add-on.  

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
