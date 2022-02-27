# 'Snapshot' vs 'Backup'
In August 2021 [the Home Assistant team announced](https://www.home-assistant.io/blog/2021/08/24/supervisor-update/) that 'snapshots' will be called 'backups' moving forward.  This addon exposes a binary sensor to indicate if snapshots are stale and a another sensor that publishes details about backups.  Both of the sensors used 'snapshot' in their names and values, so they had to be changed to match the new language.  To prevent breaking any existing automations you might have, the addon will only start using the new names and values when you upgrade if you tell it to.  

This can be controlled by using the configuration option ```call_backup_snapshot```, which will use the old names and values for sensors when it is true.  If you updated the addon from a version that used to use 'snapshot' in it names, this option will be automatically added when you update to make sure it doesn't break any existing automations.

Here is a breakdown of what the new and old sensor values mean:

## Old sensor name/values
These will be the sensor values used when ```call_backup_snapshot: True``` or if the addon is below version 0.105.1.  The addon sets ```call_backup_snapshot: True``` automatically if you upgrade the addon from an older version.
### Backup Stale Binary Sensor
#### Entity Id: 
```yaml
binary_sensor.snapshots_stale
```
#### Possible states:
```yaml
on
off
```
#### Example Attributes:
```yaml
friendly_name: Snapshots Stale
device_class: problem
```
### Backup State Sensor
#### Entity Id: 
```yaml
sensor.snapshot_backup
```
#### Possible States:
```yaml
error
waiting
backed_up
```
#### Example Attributes:
```yaml
friendly_name: Snapshots State
last_snapshot: 2021-09-01T20:26:49.100376+00:00
snapshots_in_google_drive: 2
snapshots_in_hassio: 2
snapshots_in_home_assistant: 2
size_in_google_drive: 2.5 GB
size_in_home_assistant: 2.5 GB
snapshots:
- name: Full Snapshot 2021-02-06 11:37:00
  date: '2021-02-06T18:37:00.916510+00:00'
  state: Backed Up
  slug: DFG123
- name: Full Snapshot 2021-02-07 11:00:00
  date: '2021-02-07T18:00:00.916510+00:00'
  state: Backed Up
  slug: DFG124
```

## New Sensor Names/Values
These will be the sensor values used when ```call_backup_snapshot: False``` or if the configuration option is un-set.  New installations of the addon will default to this.
### Backup Stale Binary Sensor
#### Entity Id
```yaml
binary_sensor.backups_stale
```
#### Possible States
```yaml
on
off
```
#### Example Attributes:
```yaml
friendly_name: Backups Stale
device_class: problem
```
### Backup State Sensor
#### Entity Id
```yaml
sensor.backup_state
```
#### Possible States
```yaml
error
waiting
backed_up
```
#### Example Attributes:
```yaml
friendly_name: Backup State
last_backup: 2021-09-01T20:26:49.100376+00:00
last_upload: 2021-09-01T20:26:49.100376+00:00
backups_in_google_drive: 2
backups_in_home_assistant: 2
size_in_google_drive: 2.5 GB
size_in_home_assistant: 2.5 GB
backups:
- name: Full Snapshot 2021-02-06 11:37:00
  date: '2021-02-06T18:37:00.916510+00:00
  state: Backed Up
  slug: DFG123
- name: Full Snapshot 2021-02-07 11:00:00
  date: '2021-02-07T18:00:00.916510+00:00'
  state: Backed Up
  slug: DFG124
```

### What do the values mean?
```binary_sensor.backups_stale``` is "on" when backups are stale and "off"" otherwise.  Backups are stale when the addon is 6 hours past a scheduled backup and no new backup has been made.  This delay is in place to avoid triggerring on transient errors (eg internet connectivity problems or one-off problems in Home Assistant).

```sensor.backup_state``` is:
- ```waiting``` when the addon is first booted up or hasn't been connected to Google Drive yet.
- ```error``` immediately after any error is encountered, even transient ones.
- ```backed_up``` when everything is running fine without errors.

It's attributes are:
- ```last_backup``` The UTC ISO-8601 date of the most recent backup in Home Assistant or Google Drive.
-  ```last_upload``` The UTC ISO-8601 date of the most recent backup uploaded to Google Drive.
-  ```backups_in_google_drive``` The number of backups in Google Drive.
-  ```backups_in_home_assistant``` The number of backups in Home Assistant.
-  ```size_in_google_drive``` A string representation of the space used by backups in Google Drive.
-  ```size_in_home_assistant``` A string representation of the space used by backups in Home Assistant.
-  ```backups``` The list of each snapshot in decending order of date.  Each snapshot includes its ```name```, ```date```, ```slug```, and ```state```.  ```state``` can be one of:
    - ```Backed Up``` if its in Home Assistant and Google Drive.
    - ```HA Only``` if its only in Home Assistant.
    - ```Drive Only``` if its only in Google Drive.
    - ```Pending``` if the snapshot was requested but not yet complete.
