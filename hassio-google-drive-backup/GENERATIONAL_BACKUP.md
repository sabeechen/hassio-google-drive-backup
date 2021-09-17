# Generational Backup
Generational backup lets you keep a longer history of backups on daily, weekly, monthly, and yearly cycles.  This is in contrast to the "regular" scheme for keeping history backups, which will always just delete the oldest backup when needed.  This has the effect of keeping older backups around for a longer time, which is particularly useful if you've made a bad configuration change but didn't notice until several days later.

## Configuration
The generational backup will be used when any one of `generational_days`,  `generational_weeks`, `generational_months`, or `generational_years` is greater than zero.  All of the available configuration options are given below, but utes much easier to configure from the Settings dialog accessible from the "Settings" menu at the top of the web UI.
* `generational_days`  (int): The number of days to keep
* `generational_weeks`  (int): The number of weeks to keep
* `generational_months`  (int): The number of months to keep
* `generational_years`  (int): The number of years to keep
* `generational_day_of_week`  (str): The day of the week when weekly backups will be kept.  It can be one of 'mon', 'tue', 'wed', 'thu', 'fri', 'sat' or 'sun'.  The default is 'mon'.
* `generational_day_of_month` (int): The day of the month when monthly backups will be kept, from 1 to 31.  If a month has less than the configured number of days, the latest day of that month is used.
* `generational_day_of_year` (int): The day of the year that yearly backups are kept, from 1 to 365.

## Some Details to Consider
* Generational backup assumes that a backup is available for every day to work properly, so it's recommended that you set `days_between_backups`=1 if you're using the feature.  Otherwise, a backup may not be available to be saved for a given day.
* The backups maintained by generational backup will still never exceed the number you permit to be maintained in Google Drive or Home Assistant.  For example, if `max_backups_in_google_drive`=3 and `generational_weeks`=4, then only 3 weeks of backups will be kept in Google Drive.
* Generational backup will only delete older backups when it has to.  For example, if you've configured it to keep 5 weekly backups on Monday, you've been running it for a week (so you have 7 backups), and `max_backups_in_google_drive`=7, then your backups on Tuesday, Wednesday, etc won't get deleted yet.  They won't get deleted until doing so is necessary to keep older backups around without violating the maximum allowed in Google Drive.
>Note: You can configure the addon to delete backups more aggressively by setting `generational_delete_early`=true.  With this, the addon will delete old backups that don't match a daily, weekly, monthly, or yearly configured cycle even if you aren't yet at risk of exceeding `max_backups_in_ha` or `max_backups_in_google_drive`. Careful though! You can accidentally delete all your backups this way if you don't have all your settings configured just the way you want them. 
* If more than one backup is created for a day (for example if you create one manually) then only the latest backup from that day will be kept.

## Schedule
Figuring out date math in your head is hard, so it's useful to see a concrete example.  Consider you have the following configuration. Two backups for each day, week, month, and year along with a limit in Google drive large enough to accommodate them all:
```json
"days_between_backups": 1,
"generational_days": 2,
"generational_weeks": 2,
"generational_months": 2
"generational_years": 2
"max_backups_in_google_drive": 8
```
Imagine you've been running the add-on for 2 years now, diligently making a backup every day with no interruptions.  On 19 May 2021, you could expect your list of backups in Google Drive to look like this:
- May 19, 2021 <-- 1st Daily backup
- May 18, 2021 <-- 2nd Daily backup
- May 13, 2021 <-- 1st Weekly backup
- May 06, 2021 <-- 2nd Weekly backup
- May 01, 2021 <-- 1st Monthly backup
- April 01, 2021 <-- 2nd Monthly backup
- January 01, 2021 <-- 1st Yearly backup
- January 01, 2020 <-- 2nd Yearly backup

Note that sometimes a day might overlap more than one schedule.  For example, a backup on January 1st could satisfy the constraints for both a yearly and monthly backup.  In this case, the add-on will only delete older backups when it *must* to keep from exceeding `max_backups_in_ha` or `max_backups_in_google_drive`.  Thus, the most recent backup that would otherwise be deleted will be kept until space is needed somewhere else in the schedule.
