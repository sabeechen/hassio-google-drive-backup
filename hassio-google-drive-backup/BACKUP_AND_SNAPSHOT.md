In August 2021 [the Home Assistant team announced](https://www.home-assistant.io/blog/2021/08/24/supervisor-update/) that 'snapshots' will be called 'backups' moving forward.  This addon exposes a binary sensor to indicate if snapshots are stale and a another sensor that publishes details about backups.  Both of the sensors used 'snapshot' in their names and values, so they had to be changed to match the new language.  To prevent breaking any existing auotmations you might have, the addon will only start using the new names and values when you upgrade if you tell it to.  

This can be controlled by using the configuration option ```call_backup_snapshot```, which will use the old names and values for sensors when it is true.  If you updated the addon from a version that used to use 'snapshot' in it names, this option will be automatically added when you update to make sure it doesn't break any existing automations.

Here is a breakdown of what the new and old sensor values mean:

## Old sensor name/values
These will be the sensor values used when ```call_backup_snapshot: True``` or if the addon is below version 0.105.1.  The addon sets ```call_backup_snapshot: True``` automatically if you upgrade the addon from an older version. 
Entity Id                      | States         | Example Attributes
------------------------------ | -------------- |-----------------
binary_sensor.snapshots_stale   | ```on```<br/>```off``` | ```friendly_name: Snapshots Stale```<br/>```device_class: problem```
sensor.snapshot_backup         |```error```<br/>```waiting```<br/>```backed_up```|```friendly_name: Snapshots State```<br/>```last_snapshot: 2021-09-01T20:26:49.100376+00:00```<br/>```snapshots_in_google_drive: 2```<br/>```snapshots_in_hassio: 2```<br/>```snapshots_in_home_assistant: 2```<br/>```size_in_google_drive: 2.5 GB```<br/>```size_in_home_assistant: 2.5 GB```<br/>```snapshots:```<br/>```- name: Full Snapshot 2021-02-06 11:37:00```<br/>```  date: '2021-02-06T18:37:00.916510+00:00'```<br/>```  state: Backed Up```<br/>```- name: Full Snapshot 2021-02-07 11:00:00```<br/>```  date: '2021-02-07T18:00:00.916510+00:00'```<br/>```  state: Backed Up```

## New Sensor Names/Values
These will be the sensor values used when ```call_backup_snapshot: False``` or if the configuration option is un-set.  New installations of the addon will default to this.  
Entity Id                      | States         | Example Attributes
------------------------------ | -------------- |-----------------
binary_sensor.backups_stale   | ```on```<br/>```off``` | ```friendly_name: Backups Stale```<br/>```device_class: problem```
sensor.backup_state         |```error```<br/>```waiting```<br/>```backed_up```|```friendly_name: Backup State```<br/>```last_backup: 2021-09-01T20:26:49.100376+00:00```<br/>```last_upload: 2021-09-01T20:26:49.100376+00:00```<br/>```backups_in_google_drive: 2```<br/>```backups_in_home_assistant: 2```<br/>```size_in_google_drive: 2.5 GB```<br/>```size_in_home_assistant: 2.5 GB```<br/>```backups:```<br/>```- name: Full Snapshot 2021-02-06 11:37:00```<br/>```  date: '2021-02-06T18:37:00.916510+00:00'```<br/>```  state: Backed Up```<br/>```- name: Full Snapshot 2021-02-07 11:00:00```<br/>```  date: '2021-02-07T18:00:00.916510+00:00'```<br/>```  state: Backed Up```

### What do the values mean?
```binary_sensor.backups_stale``` is "on" when backups are stale and "off"" otherwise.  Backups are stale when the addon is 6 hours past a scheduled backup and no new backup has been made.  This delay is in place to avoid triggerring on transient errors (eg internet connectivity problems or one-off problems in Home Assistant).

```sensor.backup_state``` is:
- ```waiting``` when the addon is first booted up or hasn't been connected to Google Drive yet
- ```error``` immediately after any error is encountered, even transient ones.
- ```backed_up``` when everything is running fine withotu errors.

It's attributes are:
- ```last_backup``` The UTC ISO-8601 date of the most recent backup in Home Assistant or Google Drive.
-  ```last_upload``` The UTC ISO-8601 date of the most recent backup uploaded to Google Drive.
-  ```backups_in_google_drive``` The number of backups in Google Drive.
-  ```backups_in_home_ssistant``` The number of backups in Home Assistant.
-  ```size_in_google_drive``` A string representation of the space used by backups in Google Drive.
-  ```size_in_home_assistant``` A string representation of the space used by backups in Home Assistant.
-  ```backups``` The list of each snapshot in decending order of date.  Each snapshot includes its ```name```, ```date``` and ```state```.  ```state``` can be one of:
    - ```Backed Up``` if its in Home Assistant and Google Drive.
    - ```HA Only``` if its only in Home Assistant
    - ```Drive Only``` if its only in Google Drive
    - ```Pending``` if the snapshot was requested but not yet complete.