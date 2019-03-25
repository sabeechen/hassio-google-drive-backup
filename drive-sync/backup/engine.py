import datetime
import threading
import traceback
import pprint


from time import sleep
from dateutil.relativedelta import relativedelta
from threading import Lock
from datetime import timedelta
from datetime import datetime
from pprint import pprint
from oauth2client.client import HttpAccessTokenRefreshError
from .snapshots import Snapshot
from .snapshots import DriveSnapshot
from .snapshots import HASnapshot
from .helpers import nowutc
from .helpers import makeDict
from .helpers import count
from .helpers import take
from .helpers import formatException
from .drive import Drive
from .hassio import Hassio
from .watcher import Watcher

BAD_TOKEN_ERROR_MESSAGE = "Google rejected the credentials we gave it.  Please use the \"Reauthorize\" button on the right to give the Add-on permission to use Google Drive again.  This can happen if you change your account password, you revoke the add-on's access, your Google Account has been inactive for 6 months, or your system's clock is off."

DATE_LAMBDA = lambda s:s.date()
HA_LAMBDA = lambda s:s.isInHA()
DRIVE_LAMBDA = lambda s:s.isInDrive()
NOT_DRIVE_LAMBDA = lambda s:not s.isInDrive()
SLUG_LAMBDA = lambda s:s.slug()

ERROR_BACKOFF_MIN_SECS = 10
ERROR_BACKOFF_MAX_SECS = 60*60
ERROR_BACKOFF_EXP_MUL = 2

class Engine(object):
    """
    TODO: Need to hadnle having mroe hassio snapshots than
    TODO: Test function of disabling drive or hassio cleanup
    """
    def __init__(self, config):
        self.config = config
        self.earliest_backup_time = nowutc() + timedelta(hours = self.config.hoursBeforeSnapshot())
        self.folder_id = None
        self.snapshots = []
        self.drive = Drive(self.config)
        self.lock = Lock()
        self.hassio = Hassio(self.config)
        self.last_error = None
        self.watcher = Watcher(config)
        self.last_refresh = nowutc() + relativedelta(hours = -6)
        self.notified = False
        self.last_success = nowutc()
        self.addon_info = None
        self.host_info = None
        self.sim_error = None
        self.next_error_rety = nowutc()
        self.next_error_backoff = ERROR_BACKOFF_MIN_SECS

    def saveCreds(self, creds):
        self.drive.saveCreds(creds)

    def simulateError(self, error):
        self.sim_error = error


    def driveEnabled(self):
        return self.drive.enabled()


    def driveSnapshotCount(self):
        return count(self.snapshots, DRIVE_LAMBDA)


    def haSnapshotCount(self):
        return count(self.snapshots, HA_LAMBDA)
  

    def doBackupWorkflow(self):
        self.last_refresh = nowutc()
        try:
            self.lock.acquire()
            if self.addon_info is None:
                self.host_info = self.hassio.readHostInfo()
                self.addon_info = self.hassio.readAddonInfo()
            self._checkForBackup()
            self.last_error = None
            self.last_success = nowutc()
            self.next_error_rety = nowutc()
            self.next_error_backoff = ERROR_BACKOFF_MIN_SECS
        except Exception as e:
            print(formatException(e))
            print("A retry will be attempted in {} seconds".format(self.next_error_backoff))
            self.next_error_rety = nowutc() + relativedelta(seconds = self.next_error_backoff)
            self.next_error_backoff = self.next_error_backoff * ERROR_BACKOFF_EXP_MUL
            if self.next_error_backoff > ERROR_BACKOFF_MAX_SECS:
                self.next_error_backoff = ERROR_BACKOFF_MAX_SECS 
            self.last_error = e
            self.maybeSendStalenessNotifications()
            
        finally:
            self.lock.release()


    def maybeSendStalenessNotifications(self):
        try:
            self.hassio.updateSnapshotsSensor("error", self.snapshots)
            if nowutc() >= self.last_success + timedelta(minutes = self.config.snapshotStaleMinutes()):
                self.hassio.updateSnapshotStaleSensor(True)
                if not self.notified:
                    if self.addon_info:
                        url = self.addon_info["webui"].replace("[HOST]", self.host_info["hostname"])
                        self.hassio.sendNotification("Hass.io Google Drive is Having Trouble", "The add-on is having trouble backing up your snapshots and needs attention.  Please visit the [status page](" + url + ") for details.")
                    else:
                        self.hassio.sendNotification("Hass.io Google Drive is Having Trouble", "The add-on is having trouble backing up your snapshots and needs attention.  Please visit the status page for details.")
                    self.notified = True
        except Exception as e:
            # Just eat this error, since we got an error updating status abotu the error
            print(formatException(e))


    def run(self):
        while True:
            backup_stale = ""
            # refresh every once in a while regardless
            needsRefresh = nowutc() > self.last_refresh + relativedelta(seconds = self.config.secondsBetweenRefreshes())

            # Refresh if there are new files in the backup directory
            needsRefresh = needsRefresh or self.watcher.haveFilesChanged()

            # Refresh every 20 seconds if there was an error
            needsRefresh = needsRefresh or (nowutc() > self.last_refresh + relativedelta(seconds = 20) and not self.last_error is None)
            
            if needsRefresh:
                self.doBackupWorkflow()

            sleep(self.config.secondsBetweenDirectoryChecks())


    def deleteSnapshot(self, slug, drive, ha):
        for snapshot in self.snapshots:
                if snapshot.slug() == slug:
                    if ha:
                        if not snapshot.ha:
                            raise Exception("Snapshot isn't present in Hass.io")
                        self.hassio.deleteSnapshot(snapshot)
                    if drive and self.drive:
                        if not snapshot.driveitem:
                            raise Exception("Snapshot isn't present in Google Drive")
                        self.drive.deleteSnapshot(snapshot)
                    if snapshot.isDeleted():
                        self.snapshots.remove(snapshot)
                    return
        raise Exception("Couldn't find this snapshot")


    def startSnapshot(self):
        snapshot = self.hassio.newSnapshot()
        self.snapshots.append(snapshot)
        return snapshot


    def _syncSnapshots(self):
        ha_snapshots = self.hassio.readSnapshots()
        drive_snapshots = []
        if self.drive.enabled():
            self.folder_id = self.drive.getFolderId()
            drive_snapshots = self.drive.readSnapshots(self.folder_id)

        local_map = makeDict(self.snapshots, SLUG_LAMBDA)
        drive_map = makeDict(drive_snapshots, SLUG_LAMBDA)
        ha_map = makeDict(ha_snapshots, SLUG_LAMBDA)
    
        if (self.config.verbose()):
            print("Local map: ")
            pprint(local_map)
            print("Drive map: ")
            pprint(drive_map)
            print("Ha map: ")
            pprint(ha_map)

        for snapshot in drive_snapshots:
            if not snapshot.slug() in local_map:
                snappy_shotty = Snapshot(snapshot)
                self.snapshots.append(snappy_shotty)
                local_map[snappy_shotty.slug()] = snappy_shotty
            else:
                local_map[snapshot.slug()].setDrive(snapshot)
        for snapshot in ha_snapshots:
            if not snapshot.slug() in local_map:
                snappy_shotty = Snapshot(snapshot)
                self.snapshots.append(snappy_shotty)
                local_map[snappy_shotty.slug()] = snappy_shotty
            else:
                local_map[snapshot.slug()].setHA(snapshot)
        for snapshot in self.snapshots:
            if not snapshot.slug() in drive_map:
                snapshot.driveitem = None
            if not snapshot.slug() in ha_map:
                snapshot.ha = None
            if snapshot.isDeleted():
                self.snapshots.remove(snapshot)

        self.snapshots.sort(key=DATE_LAMBDA)
        if (self.config.verbose()):
            print("Final Snapshots:")
            pprint(self.snapshots)


    def _purgeDriveBackups(self):
        while self.drive.enabled() and self.config.maxSnapshotsInGoogleDrive() >= 1 and self.driveSnapshotCount() > self.config.maxSnapshotsInGoogleDrive():
            oldest = min(filter(DRIVE_LAMBDA, self.snapshots), key=DATE_LAMBDA)
            self.drive.deleteSnapshot(oldest)
            if oldest.isDeleted():
                self.snapshots.remove(oldest)


    def _checkForBackup(self):
        # Get the local and remote snapshots available
        self._syncSnapshots()

        while self.config.maxSnapshotsInHassio() >= 1 and self.haSnapshotCount() > self.config.maxSnapshotsInHassio():
            oldest = min(filter(HA_LAMBDA, self.snapshots), key=DATE_LAMBDA)
            self.hassio.deleteSnapshot(oldest)
            if not oldest.isInDrive():
                self.snapshots.remove(oldest)

        self._purgeDriveBackups()

        oldest = None
        if len(self.snapshots) > 0:
            oldest = min(self.snapshots, key=DATE_LAMBDA)

        now = nowutc()
        if (oldest is None or now > (oldest.date() + timedelta(days = self.config.daysBetweenSnapshots()))) and now > self.earliest_backup_time:
            print("Trigger new backup")
            self.snapshots.append(self.hassio.newSnapshot())

        if self.sim_error:
            raise self.sim_error

        # Get the snapshots that should be backed up, which is at most 4 of the oldest 
        # snapshots in home assistant which aren't in Drive.
        should_backup = list(filter(HA_LAMBDA, self.snapshots))
        should_backup.reverse()
        should_backup = take(should_backup, self.config.maxSnapshotsInGoogleDrive())
        should_backup = list(filter(NOT_DRIVE_LAMBDA, should_backup))

        for snapshot in self.snapshots:
            snapshot.setWillBackup(snapshot in should_backup)

        for to_backup in should_backup:
            print("Uploading {}".format(to_backup))
            self.drive.saveSnapshot(to_backup, self.hassio.downloadUrl(to_backup), self.folder_id)

            # purge backups again, since adding one might have put us over the limit 
            self._purgeDriveBackups()
            print("Upload complete")

        self.hassio.updateSnapshotsSensor("backed_up", self.snapshots)
        self.hassio.updateSnapshotStaleSensor(False)
        if self.notified:
            self.hassio.dismissNotification()


