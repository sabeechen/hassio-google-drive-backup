## [0.107.1 2022-05-03]
#### New
* Show which google email is being used for backup in the sidebar.

#### Fixes
* Fix a bug in generational backup that would demand you intervene before it could continue ([#602](https://github.com/sabeechen/hassio-google-drive-backup/issues/602)).
* Add a missing config option to the addon schema.  Sorry for the log spam!


## [0.106.2 2022-3-23]
#### New
* Added "next_backup" to published sensors.
* Added upload chunk size config option to debug connectivity issues. 


## [0.106.1 2022-3-21]
#### Fixes
* Updates the mechanism for using custom/personal Google API credentials to work with Google's newer APIs
* Fixes a problem that prevented loading backups from Google Drive -> Home Assistant through the Nabu Casa remote UI

#### New
* Added the ability to delete any "ignored" snapshots after a certain age.
