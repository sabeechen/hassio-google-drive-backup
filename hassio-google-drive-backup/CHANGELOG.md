## v0.110.3 [2023-03-24]
- Fix an error causing "Days Between Backups" to be ignored when "Time of Day" for a backup is set.
- Fix a bug causing some timezones to make the addon to fail to start.

## v0.110.2 [2023-03-24]
- Fix a potential cause of SSL errors when communicating with Google Drive
- Fix a bug causing backups to be requested indefinitely if scheduled during DST transitions.

## v0.110.1 [2023-01-09]
- Adds some additional options for donating
- Mitgigates SD card corruption by redundantly storing config files needed for addon startup.
- Avoid global throttling of Google Drive API calls by:
  - Making sync intervals more spread out and a little random.
  - Syncing more selectively when there are modifications to the /backup directory.
  - Caching data from Google Drive for short periods during periodic syncing.
  - Backing off for a longer time (2 hours) when the addon hits permanent errors.
- Fixes CSS issues that made the logs page hard to use.

## v0.109.2 [2022-11-15]
* Fixed a bug where disabling deletion from Google Drive and enabling deltes after upload could cause backups in Google Drive to be deleted.

## v0.109.1 [2022-11-07]
* If configured from the browser, defaults to a "dark" theme if haven't already configured custom colors
* Makes the interval at which the addon publishes sensors to Home Assistant configurable (see the "Uncommon Options" settings)
* "Free space in Google Drive" is now published as an attribute of the "sensor.backup_state" sensor.
* The "binary_sensor.backups_stale" sensor will now report a problem if creating a backup hangs for more than a day.
* Fixes potential whitespace errors when copy-pasting Google Drive credentials.
* Fixes an exception when using generational backup and no backups are present.

## v0.108.4 [2022-08-22]
* Fixed an error causing "Undefined" to show up for addon descriptions.
* Fixed an error preventing addon thumbnails from showing up.
* Fixed an error causing username/password authentication to fail.
