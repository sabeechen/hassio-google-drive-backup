## [0.107.2 2022-05-07]
The "ignore" config options get some love today
* Fixed a bug causing any "core" backup to uploaded to Drive even if you told the addon to ignore it.
* Fixed a bug cuasing very long running backups (anything over 4 hours) to get ignored by the addon.

## [0.107.1 2022-05-03]
#### New
* Show which google email is being used for backup in the sidebar.

#### Fixes
* Fix a bug in generational backup that would demand you intervene before it could continue ([#602](https://github.com/sabeechen/hassio-google-drive-backup/issues/602)).
* Add a missing config option to the addon schema.  Sorry for the log spam!

