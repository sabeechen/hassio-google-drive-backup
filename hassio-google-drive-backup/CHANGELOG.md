## [0.104.2 2021-4-22]
### Fixes
- An issue parsing Google Drive's free space that prevents the web-ui from loading.

## [0.104.1 2021-4-21]
### Overview
This is probably the biggest update to the addon so far.  Here are the highlights:
- The UI has been completely rewritten by [@ericmatte](https://github.com/ericmatte) to be more clean, space efficient, and visially streamlined.  Thanks a ton for the contribution!
- New options have been added to ignore snapshots the addon didn't create and snapshots created form the supervisor's new "snapshot on upgrade" feature.  If you turn it on, snapshots already backed up to Google Drive won't be "ignored" until you delete the snapshot in Google Drive but it will apply to all future snapshots it sees.
- A bunch of unused options were removed form the addon's configuration to make it work correctly with the supervisor's new visual addon configuration editor.  Its still reommended to change addon settings from thin the addon's web-UI because this addon has a lot of configuration options! 
- A bunch of quality-of-life improvements were made to how the andle handles flaky connections to Google Drive. 

### New Stuff Details
- Thanks to tremendous effort by [@ericmatte](https://github.com/ericmatte), the interface has been completely restyled.
- Added the option "ignore_other_snapshots" which will make the addon ignore any snapshot it didn't create.
- Added the option "ignore_upgrade_snapshots" which makes the addon ignore snapshots containing a single folder or addon, such as those created automatically during HA/addon upgrades.
- Added the option "delete_after_uploaded" which deletes snapshots in Home Assistant immediately after they're uploaded.
- Added a display for the space available in Google Drive.
- Added visual indication of which snapshots are being stored for what when using generational backups.
- Auth structure changes now allow the "Content Manager" role to be used on folders in Shared Drives. 
- The addon now waits a few minutes before creating snapshots on startup to avoid resource contention issues when Home Assistant is booting up.
- Improved the handling of upload retrys on flaky connections.
- The web-UI now shows upload speed, progress, duration, etc when uploading to Google Drive.
- Removed a number of debugging options from the addon configuration, now that they're visible within the new addon config editor UI in Home Assistant.

## Fixes
- Updated the custom auth guide to reflect Google's new authentication workflow.

## Technical/Cleanup
- Automated the deployment of addon's "dev" branch to a staging instances.
- Unit tests now run automatically as GitHub actions.
- CSS styling in the web-ui is now _mostly_ uniform.

## [0.103.1 2020-1-23]
### Fixes
- Thanks to intestigation by [@jhampson-dbre](https://github.com/jhampson-dbre), fixes a long standing issue that caused the "Snapshot time of day" to be ignored ([#166](https://github.com/sabeechen/hassio-google-drive-backup/issues/166)).
- A confguration error caused old docker images from the addon to stick around after an upgrade ([#328](https://github.com/sabeechen/hassio-google-drive-backup/issues/328)).

### Technical/Cleanup
- Significantly reduced the size of the addon image. 

## [0.103.0 2020-12-31]
### Added
 - Logging in to Drive is no longer required if you have disabled upload to Google Drive
 - A help dialog now comes up if the addon has trouble writing to the filesystem (this is sometimes an issue after supervisor upgrades)

### Fixes
 - Long snapshot names could cause problems uploading to Google Drive.
 - Specifying the snapshot folder manually failed sometimes if you didn't use the "Choose Folder" link.
 - The oldest snapshot could be prematurely deleted from Home Assistant before a one new is finished.

## [0.102.0 2020-10-29]
### Added
 - Updated the addon's logos, thanks to [@pizzakid25](https://github.com/pizzakid25)
 - Added support for the new /media folder.

### Fixes
 - Addons that take a long time to stop are more reliably restarted if they're stopped to take a snapshot.
 - Addons with a watchdog have the watchdog temporarily disabled when they are stopped for a snapshot. 
 - An issue preventing Home Assistant username/password auth from functioning.
 - An issue preventing snapshot from being uploaded from Google Drive.
 - An issue preventing addon version numbers from showing up in the settings dialog.
 - Snapshot name template preview now updates to "Full" or "Partial" depending on your settings.
 - An issue that redirected users to the wrong address to restore snapshots.

## [0.101.3 2020-09-16]
Note: A breaking change was made in a previous version, the binary_sensor.snapshots_stale sensor now reports its state as "on/off" instead of "true/false".  If you have automations that depend on this state, please update them.  I'll be including this notice with every changelog entry for a while.

### Added
- You can select addons to stop while a snapshot is being taken, since some addons dump corrupt data into snapshots if they aren't stopped (eg MariaDB).

### Fixes
- Added a workaround to the "401: Unauthorized" error some users are seeing on some browsers.  You can now copy Google Drive credentials from the authorization page instead of depending on a redirect.  Same goes for choosing a folder.
- Fixed an issue causing some textbox labels to overlap with the textbox contents.
- Fixed an issue causing some users to get redirected to the wrong endpoint during authorization.
- Fixed a transient bug that displayed a string conversion error whent the backup folder became unavailable.
- Fixed numerous spelling errors, all over the place.
- Fixed an issue when using a custom sync interval that landed on day, hour, or minute boundaries.
- Fixed some version numbers not showing up in error reports.

### Technical/Cleanup
- Thanks to [@ericmatte](https://github.com/ericmatte/) for a massive cleanup of the project's HTML templates, namely:
  - Remove tons of duplicated HTML
  - Unformly templating all pages
  - Generating the style sheet on the fly.

## [0.101.2 2020-08-24]
Note: A breaking change was made in a previous version, the binary_sensor.snapshots_stale sensor now reports its state as "on/off" instead of "true/false".  If you have automations that depend on this state, please update them.  I'll be including this notice with every changelog entry for a while.

### Added
- Error reports now contain the hassos, docker, and machine version.
- Log level for the addon can be controlled with the 'log_level' and 'console_log_level' config options.
- Added 'TRACE' level logging for all requests, which may help with debugging some current bugs.


### Fixes
- The addon sometimes printed a "Please Wait" error message when nothign was wrong.
- The addon was using a deprecated autho token to authorize itself with the sueprvisor.

## [0.101.1 2020-08-15]
### BREAKING CHANGE
- The state of the binary_sensor.snapshots_stale sensor has been changed from publishing "true/false" to "on/off".  This is regratable, because automations you may have written for this sensor to malfunction with the new values.  Unfortunately, this change must be made to comply with Home Assistant's datamodel.  I appologize for any confusion this causes.

### Fixes
- A bug in writing files that prevents the selected drive folder from getting saved.
- Added error dialogs for a bunch of new error conditions.

## [0.101.0 2020-08-14]
This is a very large update.  The addon has been mostly rewritten to support some additional features in the present and accomodate some better planned features in the future.  Hopefully this is the last time I'll need to rewrite the whole damn thing!
Because there is a lot of new code, please don't hesitate to notify me if you see something working incorrectly.  I do pretty extensive automated and manual testing, but I can't catch everything.  You can report bugs through the new "Action" -> "Report a bug" to level menu item.
### Added
- When syncing, a persistant notification pops up in the UI indicating that the sync is taking place.
- A sync in progress can be cancelled, which briefly pauses it (you can choose to resume immediately).
- Better messaging when a user needs to log into Drive at least once for the addon to work (a common first time user problem).
- "Next Snapshot" and "Last Snapshot" UI elements now show the exact time in a tooltip.
- Error dialogs now clear immadiately after an attempted resync or after the first chunk of data is uploaded to Google Drive.
- A top level menu item for submitting detailed preformatted bug reports on GitHub.
- The addon now handles authentication with Google Drive through a dedicated domain, habackup.io, instead fo the confusingly named philosophyofpen.com.  I'll have you know that ".io" domains don't come cheap!  Don't worry, those of you using your own Google Drive authentication credentials are unaffected by this. 


### Changed
- Automatic error reports now contain a lot more information to help in debugging (version number, snapshot count, etc).
- Bug report links now pre-fill a lot of help debugging information, especially supervisor and addon logs.
- sensor.snapshots_stale sensor includes the "device_class: problem" attribute again.
- Some UTC datetimes have been localized for display.
- Updated many strings to reflect the "Hass.io" - "Supervisor" and "Home Assistant" -> "Home Assistant Core" rebrandings.
- Changing settings now cancels the current sync and syncs again (so the changed settings get reflected immediately).
- The addon now considers snapshots in the "Trash" as deleted.

### Fixed
- A bug that maded the addon sync over and over at install time if you disable upload to Google Drive.
- Numerous spelling errors.

### Technical
- Everything now runs asynchronously (non blocking) using the aiohttp framework.  This should help the UI be more responsive, and is the same API that Home assistant uses to run code asynchronously.
- The addon uses a new domain hosted on reliable infrastructure, habackup.io, to handle authentication with Google drive.
- Exposed local python debugger through config options for debugging.
- Merged server and client repositories.
- Migrated deployment process to run through Google Cloud Build
- Project now uses dependency injection to resolve code dependencies.
- Recorganized the project into different packages.

## [0.100.0 2020-01-18]
### Added
- Option to select the snapshot folder.  Now you can sync multiple instances to a single Google Drive account. See settings to try it out.
- Web UI now shows total disk usage in Google Drive and Home Assistant.
- Web UI now shows disk space available in the backup folder.
- Addon stops and asks for help if it thinks you're going to run out of space.
- Config options for the above features.
- A link to my [Buy Me a Coffee](https://www.buymeacoffee.com/sabeechen) page if you'd like to support.
### Changes
- Got rid of "jank" in various places.  The fight against jank is never truly won.
- If an existing snapshot folder is found on installation, the addon will ask before using it.
### Fixes
- Lots of spelling errors.

## [0.99.0] 2019-11-01
### Added
- Colors for the interface can now be choosen from the Setting Menu or through addon options.  Try it from the settings menu, you'll like it.
- Added a config option 'delete_generational_early', which deletes older unused snapshots more aggressively ([see here](https://github.com/sabeechen/hassio-google-drive-backup/blob/master/hassio-google-drive-backup/GENERATIONAL_BACKUP.md) for an explanation).
- '{hostname}' can now be used as an option in snapshot names. 

### Changes
- Snapshot staleness sensor now has the 'generic' device class, since the 'problem' device class was removed from HA's documentation.

### Fixes
- Fixed a bug causing generational snapshots closer to noon to be saved over those later in the day.
- Fixed a bug in generational snapshots that caused users far from GMT to save snapshots on the wrong day.
