## v0108.3 [2022-08-16]
* Fixed an error preventing stopped addons form being started if they hit errors while stopping. 
* Fixed many, many, many gramatical errors thanks to [@markvader's](https://github.com/markvader) [#665](https://github.com/sabeechen/hassio-google-drive-backup/pull/665).
* Fixed a missing config option in the addon schema, maximum_upload_chunk_bytes.

## v0.108.2 [2022-06-03]
* Switched to ignoring 'upgrade' backups by default for new users.
* Added a warning for existing users if you're not ignoring upgrade backups.
* Added a warning about google's OOB deprecation for private credential users.

## v0.108.1 [2022-06-02]
* Added commenting on backups, ie you can annotate them before or after creation.
* Fixed layout gaps in the backup details page

## v0.107.3 [2022-05-30]
* Fixed an issue causing ignored backups to get labelled as generational backups.
