## v0.109.1 [2022-11-07]
* If configured from the browser, defaults to a "dark" theme if haven't already configured custom colors
* Makes the interval at which the addon publishes sensors to Home Assistant configurable (see the "Uncommon Options" settings)
* "Free space in Google Drive" is now published as an attribute of the "sensor.backup_state" sensor.
* The "sensors.backups_stale" sensor will now report a problem if creating a backup hangs for more than a day.
* Fixes potential whitespace errors when copy-pasting Google Drive credentials.
* Fixes an exception when using generational backup and no backups are present.

## v0.108.4 [2022-08-22]
* Fixed an error causing "Undefined" to show up for addon descriptions.
* Fixed an error preventing addon thumbnails from showing up.
* Fixed an error causing username/password authentication to fail.

## v0.108.3 [2022-08-16]
* Fixed an error preventing stopped addons form being started if they hit errors while stopping. 
* Fixed many, many, many gramatical errors thanks to [@markvader's](https://github.com/markvader) [#665](https://github.com/sabeechen/hassio-google-drive-backup/pull/665).
* Fixed a missing config option in the addon schema, maximum_upload_chunk_bytes.

## v0.108.2 [2022-06-03]
* Switched to ignoring 'upgrade' backups by default for new users.
* Added a warning for existing users if you're not ignoring upgrade backups.
* Added a warning about google's OOB deprecation for private credential users.
