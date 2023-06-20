## v0.111.1 [2023-06-19]
- Support for the new network storage features in Home Assistant.  The addon will now create backups in what Home Assistant has configured as its default backup location.  This can be overridden in the addon's settings.
- Raised the addon's required permissions to "Admin" in order to access the supervisor's mount API.
- Fixed a CSS error causing toast messages to render partially off screen on small displays.
- Fixed misreporting of some error codes from Google Drive when a partial upload can't be resumed.

## v0.110.4 [2023-04-28]
- Fix a whitespace error causing authorization to fail.

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
