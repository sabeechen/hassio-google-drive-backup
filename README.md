# Hass.io Google Drive Backup
![](images/screenshot.png)
## About
A complete and easy to configure solution for backing up your snapshots to Google Drive
* Automatically creates new snapshots on a configurable schedule.
* Uploads any snapshots it finds to Google Drive.
* Automatically cleans up old snapshots in Home Assistant and Google drive so you don't run out of space.
* Integrates with Home Assistant Notifications, and provides sensors you can trigger off of.

This is for you if you want to quickly set up a backup strategy without having to do much work.

Particularly, most of the existing solutions for back I've found for Hass.io:
* Provide no mechanism for taking action when they fail
* Provide no mechanism for seeing what they're actually doing
* Don't come with an easy way to clean up old snapshots
* Require truly <i>arcane</i> knowledge of of the Google Drive, Hass.io or Dropbox API 

I made this to avoid these complications.  Install the add-on, click the button that authenticates with Google Drive, and you're backed up from then on.   If you don't have a Google account already, its pretty easy to [create one](https://www.google.com/intl/en/drive/) and Google gives you 15GB of free storage (at the time of writing), which should be enough for as many backups as you want. 

## Installation
The add-on is installed like any other.
1.   Go to you Hass.io > "Add-on" page in Home Assistant and add this repository: [https://github.com/sabeechen/hassio-google-drive-backup](https://github.com/sabeechen/hassio-google-drive-backup)
  
     ![Add Repo Screenshot](images/add_ss.png)
2.   Scroll down the page to find the new repository, and click the new add-on named "Hass.io Google Drive Backup"

     ![Repo Screenshot](images/repo_ss.png)
3.   Click "Install" and give it a few minutes to finish downloading.
4.   Take note of the default configuration options.  For most people the default settings are sufficient:
     *   **max_snapshots_in_hassio**: is the number of snapshots the add-on will allow Hass.io to store locally before old ones are deleted.  
     *   **max_snapshots_in_google_drive**: is the number of snapshots the add-on will keep in Google Drive before old ones are deleted.
     *   **days_between_snapshots**: How often a new snapshot should be scheduled, eg "1" for daily and "7" for weekly.
     *   **use_ssl**: determines if the add-on's webpage should only expose its interface over ssl.  If you use the [Duck DNS Add-on](https://www.home-assistant.io/addons/duckdns/) with the default settings then `"use_ssl": true`setting this to true should just work, if not [see below](#configuration-options).
     
     Other less common config options are explained [below](#configuration-options).
     > Be aware that once you start the Add-on, it will start cleaning up old snapshots immediately.  If you have 5 snapshots and you start the add-on with **max_snapshots_in_hassio**=4 then the oldest one will get deleted.
5.   Click "Start", give it a few seconds to spin up, and then click the "Open Web UI" button that appears.  For the majority of users this should take you to [https://hassio.local:1627/](https://hassio.local:1627/).
6.   Log in to the webpage with your Home Assistant username and password.
6.   Follow the instruction on-screen to link the Add-on with your Google Drive account.  Two methods of doing this are provided, since authenticating with Google's servers can be tempermental while this Add-on is still under development.
7.   You should be redirected automatically to the backup status page.  Here you can make a new snapshot, see the progress of uploading to Google Drive, etc.  You're done!

## Configuration Options
You can modify the add-ons setting by changing its config json file (like any add-on) or by opening the settings menu from the top right of the web UI.  In addition to the options described in the instructions above you can set:
*  **snapshot_time_of_day** (default: None): The time of day (local time) that new snapshots should be created in 24 hour "HH:MM" format.  When not specified (the default), snapshots are created at the same time of day of the most recent snapshot.
    > #### Example: Create snapshots at 1:30pm
    > `"snapshot_time_of_day": "13:30"`
*   **snapshot_stale_minutes** (default: 180):  How long to wait after a snapshot should have been created to consider snapshots stale and in need of attention.  Setting this too low can cause you to be notified of transient errors, ie the internet, Google Drive, or Home Assistant being offline briefly.
    > #### Example: Notify after 12 hours of staleness
    > `"snapshot_stale_minutes": "500"`
*   **snapshot_password** (default: None):  When set, snapshots are created witha password.  You'll need to remember this password when restoring snapshots.
    > #### Example: Use a password for snapshot archives
    > `"snapshot_password": "super_secret"`
*   **send_error_reports** (default: False):  When true, the text of unexpected errors will be sent to database maintained by the developer.  This helps idenfity problems with new releases and provide better context messages when errors come up.
    > #### Example: Allow sending error reports
    > `"send_error_reports": True`
*   **require_login** (default: true): When true, requires your home assistant username and password to access the backpup status page.  Turning this off isn't recommended.
    > #### Example: Don't require login
    > `"require_login": false`
*   **certfile** (default: /ssl/certfile.pem): The path to your ssl keyfile
*   **keyfile** (default: /ssl/keyfile.pem): the path to your ssl certfile
    > #### Example: Use certs you keep in a weird place
    > ```json
    >   "certfile": "/ssl/weird/path/cert.pem",
    >   "keyfile": "/ssl/weird/path/key.pem"
    > ```
*   **verbose** (default: false): If true, enable additional debug logging.  Useful if you start seeing errors and need to file a bug with me.
    > #### Example: Turn on verbose logging
    > `"verbose": true`
*   **generational_*** (default: None): When set, older snapshots will be kept longer using a [generational backup scheme](https://en.wikipedia.org/wiki/Backup_rotation_scheme). See the [question below](#can-i-keep-older-backups-for-longer) for configuration options.
    > #### Example: Keep a snapshot once every day 3 days and once a week for 4 weeks
    > ```json
    >   "generational_days": 3,
    >   "generational_weeks": 4
    > ```

## FAQ
### How will I know this will be there when I need it?
Home Assistant is notorious for failing silently, and your backups aren't something you want to find is broken after an erroneous comma makes you unable to turn on any of the lights in your house.  Thats why I've added some functionality to keep you informed if things start to break.  If the add-on runs into trouble and gets more than 12 hours behind its schedule, you'll know in two ways:
* Notifications in Home Assistant UI

  ![Notification](images/notification_error.png)

* A [binary_sensor](#lovelace-card) you can use to trigger additional actions.
  
   ![Binary Sensor](images/binary_sensor.png)

Redundancy is the foundation of reliability.  With local snapshots, Google Drive's backups, and two flavors of notification I think you're covered.


### I never look at HA notifications.  Can I show information about backups in my Home Assistant Interface?
The add-on creates a few sensors that show the status of snapshots that you could trigger automations off of.  `binary_sensor.snapshots_stale` becomes true when the add-on has trouble backing up or creating snapshots.  For example the lovelace card below only shows up in the UI when snapshots go stale:
#### Lovelace Card

    type: conditional
    conditions:
      - entity: binary_sensor.snapshots_stale
        state_not: 'False'
    card:
      type: markdown
      content: >-
        Snapshots are stale! Please visit the "Hass.io Google Drive Backup" add-on
        status page for details.
      title: Stale Snapshots!`
#### Mobile Notifications
If you have [android](https://github.com/Crewski/HANotify) or [iOS](https://www.home-assistant.io/docs/ecosystem/ios/), [other notifications](https://www.home-assistant.io/components/notify/) set up, this automation would let you know if things go stale:


    - alias: Snapshots went stale
      id: 'snapshots_went_stale'
      trigger:
      - platform: state
        entity_id: binary_sensor.snapshots_stale
        from: 'False'
        to: 'True'
      condition: []
      action:
      - data:
        service: notify.android
          title: Snapshots are Stale
          message: Please visit the 'Hass.io Google Drive Backup ' add-on status page
            for details.

You could automate anything off of this binary sensor.  The add-on also exposes a sensor `sensor.snapshot_backup` that exposes the details of each snapshot.  I'm working on a custom lovelace component to expose that information.

### Can I put a link to the web UI in home assistant?
You can use [panel_iframe](https://www.home-assistant.io/components/panel_iframe/) to add a link to the Web UI from Home Assistant's side panel.  Try adding snippet below to your configuration.yaml file.
```yaml
panel_iframe:
  backup:
    title: 'Snapshots'
    icon: mdi:cloud-upload
    url: 'http://hassio.local:1627'
```
You might need to change the `url:` if you use ssl or access Home Assistant through a different hostname.

### Can I specify what time of day snapshots should be created?
You can add `"snapshot_time_of_day": "13:00"` to your add-on configuration to make snapshots always happen at 1pm.  Specify the time in 24 hour format of `"HH:MM"`.  When unspecified, the next snapshot will be created at the same time of day as the last one.

### Can I keep older backups for longer?
The add-on can be configured to keep [generational backups](https://en.wikipedia.org/wiki/Backup_rotation_scheme) on daily, weekly, monthly, and yearly intervals instead of just deleting the oldest snapshot.  This can be useful if, for example, you've made an erroneous change but haven't noticed for several days and all the backups before the change are gone.  With a configuration setting like this...
```json
  "generational_days": 3,
  "generational_weeks": 4,
  "generational_months": 12,
  "generational_years": 5
 ```
 ... a snapshot will be kept for the last 3 days, the last 4 weeks, the last 12 months, and the last 5 years.  Additionally you may configure the day of the week, day of the month, and day of the year that weekly, monthly, and yearly snapshots are maintained.
  ```json
    "generational_days": 3,
    
    "generational_weeks": 4,
    "generational_day_of_week": "mon",  // Can be 'mon', 'tue', 'wed', 'thu', 'fri', 'sat' or 'sun' (defaults to 'mon')

    "generational_months": 12,
    "generational_day_of_month": 1, // Can be 1 through 31 (defaults to 1) 

    "generational_years": 5,
    "generational_day_of_year": 1, // can be 1 through 365 (defaults to 1)
 ```
 * Any combination of days, weeks, months, and years can be used.  They all default to 0.
 * Its highly reccommended to set '`"days_between_snapshots": 1`' to ensure a snapshot is available for each day.
 * Ensure you've set `max_snapshots_in_drive` appropriatly high to keep enough snapshots (24 in the example above).
 * Once this option is enabled, it may take several days or weeks to see older snapshots get cleaned up.  Old snapshots will only get deleted when the number present exceeds `max_snapshots_in_drive` or `max_snapshots_in_hassio`
 
### I already have something that creates snapshots on a schedule.  Can I use this just to backup to Google Drive?
If you set '`"days_between_snapshots": 0`', then the add-on won't try to create new snapshots but will still back up any it finds to Google Drive and clean up old snapshots in both Home Assistant and Google Drive.  This can be useful if you already  have for example an automation that creates snapshots on a schedule. 

### Does this store any personal information?
On a matter of principle, I only keep track of and store information necessary for the add-on to function.  To the best of my knowledge the scope of this is:
* Once authenticated with Google, your Google credentials are only stored locally on your Home Assistant instance.  This isn't your actual username and password, only an opaque token returned from Google used to verify that you previously gave the Add-on permission to access your Google Drive.  Your password is never seen by me or the add-on.
* The add-on has access to the files in Google Drive it created, which is the 'Hass.io Snapshots' folder and any snapshots it uploads.  See the https://www.googleapis.com/auth/drive.file scope in the [Drive REST API v3 Documentation](https://developers.google.com/drive/api/v3/about-auth) for details, this is the only scope the add-on requests for your account.
* Google stores a history of information about the number of requests, number of errors, and latency of requests made by this Add-on and makes a graph of that visible to me.  This is needed because Google only gives me a certain quota for requests shared between all users of the add-on, so I need to be aware if someone is abusing it.
* The Add-on is distributed as a Docker container hosted on Docker Hub, which his how almost all add-ons work.  Docker keeps track of how many people have requested an image and makes that information publicly visible.

This invariably means that I have a very limited ability to see how many people are using the add-on or if it is functioning well.  If you do like it, feel free to shoot me an email at [sabeechen@gmail.com](mailto:sabeechen@gmail.com) or star this repo on GitHub, it really helps keep me motivated.  If you run into problems or think a new feature would be nice, file an issue on GitHub.

### Can I permanently save a snapshot so it doesn't get cleaned up?
The Add-on will only ever look at snapshots in the folder in Google Drive it created.  If you move the snapshots anywhere else in Google Drive, they will be ignored.  Just don't move them back in accidentally since they'll get "cleaned up" like any old snapshot after a while :)

### I already have something that backs up my snapshots.  Can I just use this to trigger new ones?
Yes, though I'll point out that Google Gives you a lot of free storage, 15GB at the time of this writing, and their infrastructure is a lot more resiliant than any of your hard drives.  If you set the configuration option:
`"max_snapshots_in_google_drive": 0`
Then it won't try to upload anything to Google Drive.

### What do I do if I've found an error?
If the add-on runs into trouble and can't back up, you should see a big red box with the text of the error on the status webpage.  This should include a link to pre-populate a new issue in github, which I'd encourage you to do.  Additioanlly you can set the add-on config option `"verbose" : true` to get information from the add-on's logs to help me with debugging.

### Will this fill up my Google Drive?  Why are my snapshots so big?
You'll need tot take care to ensure you don't configure this to blow up your Google Drive.  You might want to consider:
*   If your snapshots are HUGE, its probably because Home Assistant by defaults keeps 10 days of sensor history.  Consider setting `purge_keep_days: N` in your [recorder confiuration](https://www.home-assistant.io/components/recorder/) to trim it down to something more manageable, like 1 day of history.
*   If you use the Google Drive Desktop sync client, you'll porbably want to tell it not to sync this folder (its available in the options).

### I want my snapshots to sync to my Desktop computer too
Thats not a question but you can use [Google Drive Backup & Sync]([https://www.google.com/drive/download/) to download anything in your Google Drive to your desktop computer.

### I configured this to only keep 4 snapshots in Drive and Hass.io, but sometimes I can see there are 5?
The add-on will only delete an old snapshot if a new one exists to replace it, so it will create a 5th one before deleting the first.  This is a reliability/disk usage compromise that favors reliability, because otherwise it would have to delete an old snapshot (leaving only 3) before it could guarantee the 4th one actually exists.

