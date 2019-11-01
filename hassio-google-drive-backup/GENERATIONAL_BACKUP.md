# Generational Backup
Generational backup lets you keep a longer history of snapshots on daily, weekly, monthly, and yearly cycles.  This is in contrast to the "regular" scheme for keeping a history snapshots, which will always just delete the oldest snapshot when needed.  This has the effect of keeping older snapshots around for a longer time, which is particularly useful if you've made a bad configuration change but didn't actually notice until several days later.

## Configuration
Generational backup will be used when any one of `generational_days`,  `generational_weeks`, `generational_months` or `generational_years` is greater than zero.  All of the available cofiguration options are given below, but utes much easier to configure from the Settings dialog accessible from the "Settings" menu at the top of the web UI.
* `generational_days`  (int): The number of days to keep
* `generational_weeks`  (int): The number of weeks to keep
* `generational_months`  (int): The number of months to keep
* `generational_years`  (int): The number of years to keep
* `generational_day_of_week`  (str): The day of the week when weekly snapshots will be kept.  It can be one of 'mon', 'tue', 'wed', 'thu', 'fri', 'sat' or 'sun'.  The default is 'mon'.
* `generational_day_of_month` (int): The day of the month when monthly snapshots will be kept, from 1 to 31.  If a month has less than the configured number of days, the latest daya of that month is used.
* `generaitonal_day_of_year` (int): The day of the year that yearly snapshots are kept, from 1 to 365.

## Some Details to Consider
* Generational backup assumes that a snapshot is available for every day to work properly, so its recommended that you set `days_between_snapshots`=1 if you're using the feature.  Otherwise a snapshot may not be available to be saved for a given day.
* The snapshots maintained by generational backup will still never exceed the numebr you permit to be maintained in Google drive or Hassio.  For example if `max_snapshots_in_google_drive`=3 and `generational_weeks`=4, then only 3 weeks of snapshots will actually be kept in Google Drive.
* Generational backup will only delete older snapshots when it has to.  For example if you've configured it to keep 5 weekly snapshots on Monday, you've been running it for a week for a week (so you have 7 snapshots), and `max_snapshot_in_google_drive`=7, then your snpashots on Tuesday, Wednesday, etc won't get deleted yet.  They won't get deleted until doing so is necessary to keep older snapshots around without violatin the maximum allowed in Google Drive.
>Note: You can configure the addon to delete snapshots more aggressively by setting `generational_delete_early`=true.  With this, the addon will delete old snapshots that don't match a daily, weekly, monthly, or yearly configured cycle even if you aren't yet at risk of exceeding `max_snapshots_in_hassio` or `max_snapshots_in_google_drive`. Careful though! You can accidentally delete all your snapshots this way if you don't have all your settings configured just the way you want them. 
* If more than one snapshot is created for a day (for example if you create one manually) then only the latest snapshot from that day will be kept.

## Schedule
Figuring out date math in your head is hard, so its useful to see a concrete example.  Consider you have the following configuration. 2 snapshots for each day, week, month, and year along with a max in Google drive large anough to accomodate them all:
```json
"days_between_snapshots": 1,
"generational_days": 2,
"generational_weeks": 2,
"generational_months": 2
"generational_years": 2
"max_snapshots_in_google_drive": 8
```
Imagine you've been running the add-on for 2 years now, dilligently making a snapshot every day with no interruptions.  On 19 May 2019, you could expect your list of snapshots in Google Drive to look like this:
- May 19, 2019 <-- 1st Daily snapshot
- May 18, 2019 <-- 2nd Daily snapshot
- May 13, 2019 <-- 1st Weekly snapshot
- May 06, 2019 <-- 2nd Weekly snapshot
- May 01, 2019 <-- 1st Monthly snapshot
- April 01, 2019 <-- 2nd Monthly snapshot
- January 01, 2019 <-- 1st Yearly snapshot
- January 01, 2018 <-- 2nd Yearly snapshot

Note that sometimes a day might overlap more than one schedule.  For example a snapshot on January 1st could satisfy the constraints for both a yearly and monthly snapshot.  In this case the add-on will only delete older snapshots when it *must* to keep from exceeding `max_snapshots_in_hassio` or `max_snapshots_in_google_drive`.  Thus, most recent snapshot that would otherwise get deleted will be kept until the space is needed somewhere else in the schedule.
