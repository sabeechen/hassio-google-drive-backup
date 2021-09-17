## [0.105.2 2021-9-7]
### Fixes
* Include addon version number in the path component of static resources in an attempt to resolve [issue #466](https://github.com/sabeechen/hassio-google-drive-backup/issues/466)

### New
* Snapshot slug id is now included in the backup state sensor. 

## [0.105.1 2021-9-7]
This version will automatically update your addon's configuration to reference "backups" in its configuration keys instead of "snapshots".  It will also, with your permission, start publishing its sensor values with the word "backup" instead of "snapshot".  Visit the addon Web-UI after updating for details. 

### New
* Updated the addon to reference "backups" instead of "snapshots":
   * UI no longer refers to "snapshots"
   * Published sensor now refer to "backups" (this is configurable).
   * Use the supervisor's new "/backups" endpoints.
   * Configuration options now refer only to "backups".
* Add config option "call_backup_snapshot" for if you still want published sensors to refer to "snapshots"
* Improved error messaging when Google credentials expire.
* Added an option to pre-emptively delete the oldest backup before creating a new one.  See "Delete oldest backup before making a new one" in the settings.

### Fixes
* A bug causing an error when using generational backups and no backups are present ([#447](https://github.com/sabeechen/hassio-google-drive-backup/issues/447))
* A bug causing the reported addon sizes in backups to be way too small.
* A bug causing in-progress backup to always show up as "partial" ([#437](https://github.com/sabeechen/hassio-google-drive-backup/issues/437))
* Published sensors included ignored backups in heir dates ([#431](https://github.com/sabeechen/hassio-google-drive-backup/issues/431))
* Numerous spelling errors.

### Dev/Cleanup
* Configured a devcontainer for code contributions.
* Moved generating Google's refresh tokens primarily to a new domain, https://token1.habackup.io, for cost and reliability reasons.

## [0.104.3 2021-4-28]
### Fixes
- A config error that made an optional config parameter mandatory


## [0.104.2 2021-4-22]
### Fixes
- An issue parsing Google Drive's free space that prevents the web-ui from loading.

