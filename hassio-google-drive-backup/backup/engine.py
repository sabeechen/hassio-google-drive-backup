from .snapshots import Snapshot
from .snapshots import DriveSnapshot
from .snapshots import HASnapshot
from .helpers import makeDict
from .helpers import count
from .helpers import take
from .helpers import formatException
from .helpers import resolveHostname
from .helpers import formatTimeSince
from .drive import Drive
from .hassio import Hassio, SnapshotInProgress
from oauth2client.client import HttpAccessTokenRefreshError
from .watcher import Watcher
from .config import Config
from .time import Time
from pprint import pformat
from dateutil.relativedelta import relativedelta
from threading import Lock
from datetime import timedelta
from datetime import datetime
from typing import Dict, List, Optional, Callable
from oauth2client.client import Credentials
from .backupscheme import GenerationalScheme, OldestScheme
from .logbase import LogBase
from .knownerror import KnownError
from .seekablerequest import WrappedException
from urllib.parse import quote
from requests import get
import os
import json

BAD_TOKEN_ERROR_MESSAGE: str = "Google rejected the credentials we gave it.  Please use the \"Reauthorize\" button on the right to give the Add-on permission to use Google Drive again.  This can happen if you change your account password, you revoke the add-on's access, your Google Account has been inactive for 6 months, or your system's clock is off."
DRIVE_FULL_MESSAGE = "The user's Drive storage quota has been exceeded"
CANT_REACH_GOOGLE_MESSAGE = "Unable to find the server at www.googleapis.com"
CANT_REACH_GOOGLE_AUTH_MESSAGE = "Unable to find the server at oauth2.googleapis.com"
CANT_REACH_GOOGLE_UNAVAILABLE_MESSAGE = "OSError: [Errno 99] Address not available"
GOOGLE_TIMEOUT_1_MESSAGE = "socket.timeout: The read operation timed out"
GOOGLE_TIMEOUT_2_MESSAGE = "socket.timeout: timed out"
GOOGLE_SESSION_EXPIRED = "googleapiclient.errors.ResumableUploadError: <HttpError 404"
GOOGLE_500_ERROR = "urllib.error.HTTPError: HTTP Error 500: Internal Server Error"

DATE_LAMBDA: Callable[[Snapshot], datetime] = lambda s: s.date()
HA_LAMBDA: Callable[[Snapshot], bool] = lambda s: s.isInHA()
DRIVE_LAMBDA: Callable[[Snapshot], bool] = lambda s: s.isInDrive()
NOT_DRIVE_LAMBDA: Callable[[Snapshot], bool] = lambda s: not s.isInDrive()
SLUG_LAMBDA: Callable[[Snapshot], str] = lambda s: s.slug()
DRIVE_SLUG_LAMBDA: Callable[[DriveSnapshot], str] = lambda s: s.slug()
HA_SLUG_LAMBDA: Callable[[HASnapshot], str] = lambda s: s.slug()
RETAINED_LAMBDA: Callable[[Snapshot], str] = lambda s: s.haRetained()

DRIVE_DELETABLE_LAMBDA: Callable[[Snapshot], str] = lambda s: s.isInDrive() and not s.driveRetained()
HA_DELETABLE_LAMBDA: Callable[[Snapshot], str] = lambda s: s.isInHA() and not s.haRetained()

ERROR_BACKOFF_MIN_SECS = 10
ERROR_BACKOFF_MAX_SECS = 60 * 60
ERROR_BACKOFF_EXP_MUL = 2


class Engine(LogBase):
    def __init__(self, config: Config, drive: Drive, hassio: Hassio, time: Time):
        self.time: Time = time
        self.config: Config = config
        self.folder_id: Optional[str] = None
        self.snapshots: List[Snapshot] = []
        self.drive: Drive = drive
        self.lock: Lock = Lock()
        self.hassio: Hassio = hassio
        self.last_error: Optional[Exception] = None
        self.watcher: Watcher = Watcher(config)
        self.last_refresh: datetime = self.time.now() + relativedelta(hours=-6)
        self.notified: bool = False
        self.last_success: datetime = self.time.now()
        self.sim_error: Optional[str] = None
        self.next_error_rety: datetime = self.time.now()
        self.next_error_backoff: int = ERROR_BACKOFF_MIN_SECS
        self.one_shot: bool = False
        self.snapshots_stale: bool = False
        self.last_error_reported = False
        self.firstSync = True
        self.cred_version = 0
        self.successes = 0
        self.failures = 0
        self.uploads = 0
        self.start_time = self.time.now()
        self.lastUploadSize = 0

    def getDeleteScheme(self):
        gen_config = self.config.getGenerationalConfig()
        if gen_config:
            return GenerationalScheme(self.time, gen_config)
        else:
            return OldestScheme()

    def credentialsVersion(self):
        return self.cred_version

    def saveCreds(self, creds: Credentials) -> None:
        self.drive.saveCreds(creds)
        self.cred_version += 1
        self.one_shot = True

    def simulateError(self, error: Optional[str]) -> None:
        self.sim_error = error

    def driveEnabled(self) -> bool:
        return self.drive.enabled()

    def driveSnapshotCount(self) -> int:
        return count(self.snapshots, DRIVE_LAMBDA)

    def haSnapshotCount(self) -> int:
        return count(self.snapshots, HA_LAMBDA)

    def driveDeletableSnapshotCount(self) -> int:
        return count(self.snapshots, DRIVE_DELETABLE_LAMBDA)

    def haDeletableSnapshotCount(self) -> int:
        return count(self.snapshots, HA_DELETABLE_LAMBDA)

    def setRetention(self, snapshot: Snapshot, retainDrive: bool, retainHa: bool) -> None:
        if snapshot.isInDrive() and snapshot.driveitem.retained() != retainDrive and self.driveEnabled():
            self.drive.setRetain(snapshot, retainDrive)
        if snapshot.isInHA() and snapshot.ha.retained() != retainHa:
            snapshot.ha._retained = retainHa
            self._saveHaRetention()

        snapshot._pending_retain_drive = retainDrive
        snapshot._pending_retain_ha = retainHa
        self._updateFreshness()

    def doUpload(self, snapshot: Snapshot):
        path = os.path.join(self.config.backupDirectory(), snapshot.slug() + ".tar")
        self.drive.downloadToFile(snapshot.driveitem.id(), path, snapshot)
        self.hassio.refreshSnapshots()
        self.doBackupWorkflow()

        if snapshot.isInHA() and not snapshot.ha.retained():
            snapshot.ha._retained = True
            self.config.saveRetained(list(map(HA_SLUG_LAMBDA, filter(RETAINED_LAMBDA, filter(HA_LAMBDA, self.snapshots)))))
            self._saveHaRetention()
        self._updateFreshness()

    def _saveHaRetention(self):
        self.config.saveRetained(list(map(HA_SLUG_LAMBDA, filter(RETAINED_LAMBDA, filter(HA_LAMBDA, self.snapshots)))))

    def doBackupWorkflow(self) -> None:
        self.last_refresh = self.time.now()
        try:
            self.lock.acquire()
            self._checkForBackup()
            self.snapshots_stale = False

            if self.last_error is not None:
                self.info("Looks like the error resolved itself, snapshots are synced")
            self.last_error = None
            self.last_success = self.time.now()
            self.next_error_rety = self.time.now()
            self.next_error_backoff = ERROR_BACKOFF_MIN_SECS
            self.last_error_reported = False
            self.successes += 1
        except Exception as e:
            self.failures += 1
            self.error(formatException(e))
            self.error("A retry will be attempted in {} seconds".format(self.next_error_backoff))
            self.next_error_rety = self.time.now() + relativedelta(seconds=self.next_error_backoff)
            self.next_error_backoff = self.next_error_backoff * ERROR_BACKOFF_EXP_MUL
            if self.next_error_backoff > ERROR_BACKOFF_MAX_SECS:
                self.next_error_backoff = ERROR_BACKOFF_MAX_SECS
            self.last_error = e
            if not self.last_error_reported:
                self.last_error_reported = True
                if self.config.sendErrorReports():
                    self.sendErrorReport()
            self.maybeSendStalenessNotifications()
        finally:
            self.lock.release()

    def sendErrorReport(self) -> None:
        message = self.getError()
        if message == "default_error":
            message = self.getExceptionInfo()
        self.info("Sending error report (see settings to disable)")
        try:
            version = json.dumps(self.getDebugInfo(), indent=4)
        except Exception as e:
            version = "Debug info failed: " + str(e)
        url: str = "https://philosophyofpen.com/login/error.py?error={0}&version={1}".format(quote(message), quote(version))
        try:
            get(url, timeout=5)
        except Exception:
            # just eat any error
            pass

    def getNextSnapshotTime(self) -> Optional[datetime]:
        if self.config.daysBetweenSnapshots() <= 0:
            return None
        if len(self.snapshots) == 0:
            return self.time.now() - timedelta(days=1)
        newest: datetime = max(self.snapshots, key=DATE_LAMBDA).date()

        if self.config.snapshotTimeOfDay() is None:
            return newest + timedelta(days=self.config.daysBetweenSnapshots())
        parts = self.config.snapshotTimeOfDay().split(":")
        if len(parts) != 2:
            return newest + timedelta(days=self.config.daysBetweenSnapshots())
        hour: int = int(parts[0])
        minute: int = int(parts[1])
        if hour >= 24 or minute >= 60:
            return newest + timedelta(days=self.config.daysBetweenSnapshots())

        newest_local: datetime = self.time.toLocal(newest)
        time_that_day_local = datetime(newest_local.year, newest_local.month, newest_local.day, hour, minute, 0).astimezone(self.time.local_tz)
        if newest_local < time_that_day_local:
            # Latest snapshot is before the snapshot time for that day
            return self.time.toUtc(time_that_day_local)
        else:
            # return the next snapshot after the delta
            return self.time.toUtc(time_that_day_local + timedelta(days=self.config.daysBetweenSnapshots()))

    def maybeSendStalenessNotifications(self) -> None:
        try:
            self.hassio.updateSnapshotsSensor("error", self.snapshots)
            if self.time.now() >= self.last_success + timedelta(minutes=self.config.snapshotStaleMinutes()):
                self.snapshots_stale = True
                if not self.notified:
                    if self.config.useIngress():
                        url = "/hassio/ingress/" + self.hassio.self_info['slug']
                    else:
                        url = self.hassio.self_info["webui"].replace("[HOST]", self.hassio.host_info["hostname"])
                    self.hassio.sendNotification("Hass.io Google Drive Backup is Having Trouble", "The add-on is having trouble backing up your snapshots and needs attention.  Please visit the [status page](" + url + ") for details.")
                    self.notified = True
        except Exception as e:
            # Just eat this error, since we got an error updating status abotu the error
            self.error(formatException(e))

    def needsRefresh(self) -> bool:
        # refresh every once in a while regardless
        needsRefresh: bool = self.time.now() > self.last_refresh + relativedelta(seconds=self.config.secondsBetweenRefreshes())

        # We need a refresh if we need a new snapshot
        next_snapshot = self.getNextSnapshotTime()
        if next_snapshot:
            needsRefresh = needsRefresh or (self.time.now() > next_snapshot)

        # Don't refresh if we haven't passed the error bakcoff time.
        if self.time.now() < self.next_error_rety:
            needsRefresh = False

        # Refresh if there are new files in the backup directory
        needsRefresh = needsRefresh or self.watcher.haveFilesChanged()

        if self.one_shot:
            self.one_shot = False
            needsRefresh = True

        return needsRefresh

    def run(self) -> None:
        while True:
            if self.needsRefresh():
                self.doBackupWorkflow()
            try:
                self.hassio.updateSnapshotStaleSensor(self.snapshots_stale)
            except Exception:
                # Just eat the error, we'll keep retrying.
                pass
            self.time.sleep(self.config.secondsBetweenDirectoryChecks())

    def deleteSnapshot(self, slug: str, drive: bool, ha: bool) -> None:
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
                self._updateFreshness()
                return
        raise Exception("Couldn't find this snapshot")

    def startSnapshot(self, custom_name=None, retain_drive=False, retain_ha=False) -> Snapshot:
        self.info("Creating new snapshot")
        for snapshot in self.snapshots:
            if snapshot.isPending():
                raise SnapshotInProgress()
        snapshot = self.hassio.newSnapshot(custom_name=custom_name, retain_drive=retain_drive, retain_ha=retain_ha)
        self.snapshots.append(snapshot)
        self._updateFreshness()
        return snapshot

    def _syncSnapshots(self) -> None:
        ha_snapshots: List[HASnapshot] = self.hassio.readSnapshots()
        drive_snapshots: List[DriveSnapshot] = []
        if self.drive.enabled():
            self.folder_id = self.drive.getFolderId()
            drive_snapshots = self.drive.readSnapshots(self.folder_id)

        local_map: Dict[str, Snapshot] = makeDict(self.snapshots, SLUG_LAMBDA)
        drive_map: Dict[str, DriveSnapshot] = makeDict(drive_snapshots, DRIVE_SLUG_LAMBDA)
        ha_map: Dict[str, HASnapshot] = makeDict(ha_snapshots, HA_SLUG_LAMBDA)

        self.debug("Local map: ")
        self.debug(pformat(local_map))
        self.debug("Drive map: ")
        self.debug(pformat(drive_map))
        self.debug("Ha map: ")
        self.debug(pformat(ha_map))
        for snapshot_from_drive in drive_snapshots:
            if not snapshot_from_drive.slug() in local_map:
                drive_snapshot: Snapshot = Snapshot(snapshot_from_drive)
                self.snapshots.append(drive_snapshot)
                local_map[drive_snapshot.slug()] = drive_snapshot
            else:
                local_map[snapshot_from_drive.slug()].setDrive(snapshot_from_drive)

        added_from_ha: Snapshot = None
        for snapshot_from_ha in ha_snapshots:
            if not snapshot_from_ha.slug() in local_map:
                ha_snapshot: Snapshot = Snapshot(snapshot_from_ha)
                self.snapshots.append(ha_snapshot)
                local_map[ha_snapshot.slug()] = ha_snapshot
                added_from_ha = ha_snapshot
            else:
                local_map[snapshot_from_ha.slug()].setHA(snapshot_from_ha)
        for snapshot in self.snapshots:
            if not snapshot.slug() in drive_map:
                snapshot.driveitem = None
            if not snapshot.slug() in ha_map:
                snapshot.ha = None
            if snapshot.isDeleted():
                self.snapshots.remove(snapshot)
            if added_from_ha and snapshot.isPending():
                self.snapshots.remove(snapshot)
                self.hassio.killPending()
                added_from_ha._pending_retain_drive = snapshot._pending_retain_drive
                added_from_ha._pending_retain_ha = snapshot._pending_retain_ha

        self.snapshots.sort(key=DATE_LAMBDA)
        if (self.config.verbose()):
            self.debug("Final Snapshots:")
            self.debug(pformat(self.snapshots))
        self._saveHaRetention()
        self.firstSync = False

    def _purgeDriveBackups(self) -> None:
        while self.drive.enabled() and self.config.maxSnapshotsInGoogleDrive() > 0 and self.driveDeletableSnapshotCount() > self.config.maxSnapshotsInGoogleDrive():
            oldest: Snapshot = self.getDeleteScheme().getOldest(filter(DRIVE_DELETABLE_LAMBDA, self.snapshots))
            self.drive.deleteSnapshot(oldest)
            if oldest.isDeleted():
                self.snapshots.remove(oldest)
        self._updateFreshness()

    def _purgeHaSnapshots(self) -> None:
        while self.config.maxSnapshotsInHassio() > 0 and self.haDeletableSnapshotCount() > self.config.maxSnapshotsInHassio():
            oldest_hassio: Snapshot = self.getDeleteScheme().getOldest(filter(HA_DELETABLE_LAMBDA, self.snapshots))
            self.hassio.deleteSnapshot(oldest_hassio)
            if not oldest_hassio.isInDrive():
                self.snapshots.remove(oldest_hassio)
        self._updateFreshness()

    def _checkForBackup(self) -> None:
        # Get the local and remote snapshots available
        self.hassio.loadInfo()
        self._syncSnapshots()

        if not self.driveEnabled():
            self.hassio.updateSnapshotsSensor("waiting", self.snapshots)
            return

        self._purgeHaSnapshots()
        self._purgeDriveBackups()

        next_snapshot = self.getNextSnapshotTime()
        if next_snapshot and self.time.now() > next_snapshot:
            self.info("Start new scheduled backup")
            try:
                self.startSnapshot()
            except SnapshotInProgress:
                pass

        if self.sim_error is not None:
            raise KnownError(self.sim_error)

        # Get the snapshots that should be backed up, which is at most N of the oldest
        # snapshots in home assistant which aren't in Drive.
        should_backup: List[Snapshot] = list(filter(HA_LAMBDA, self.snapshots))
        should_backup.reverse()
        should_backup = list(take(should_backup, self.config.maxSnapshotsInGoogleDrive()))
        should_backup = list(filter(NOT_DRIVE_LAMBDA, should_backup))

        # remove newer snapshots that are only in Drive
        for snapshot in self.snapshots:
            if len(should_backup) > 0 and snapshot.isInDrive() and not snapshot.isInHA() and snapshot.date() > should_backup[0].date():
                should_backup.remove(should_backup[0])

        for snapshot in self.snapshots:
            snapshot.setWillBackup(snapshot in should_backup)

        for to_backup in should_backup:
            if self.drive.enabled():
                snapshot.setWillBackup(True)
                self.info("Uploading {}".format(to_backup.name()))
                if not self.folder_id:
                    raise Exception("No folder Id")
                self.lastUploadSize = to_backup.size()
                self.drive.saveSnapshot(to_backup, self.hassio.downloadUrl(to_backup), self.folder_id)
                self.uploads += 1

                # purge backups again, since adding one might have put us over the limit
                self._purgeDriveBackups()
                self.info("Upload complete")
            else:
                snapshot.setWillBackup(False)

        self.hassio.updateSnapshotsSensor("backed_up", self.snapshots)
        self.hassio.updateSnapshotStaleSensor(False)
        if self.notified:
            self.hassio.dismissNotification()
            self.notified = False

    def _updateFreshness(self) -> None:
        deleteFromDrive = None
        deleteFromHa = None
        scheme = self.getDeleteScheme()
        if self.config.maxSnapshotsInHassio() > 0 and self.haDeletableSnapshotCount() >= self.config.maxSnapshotsInHassio():
            deleteFromHa = scheme.getOldest(filter(HA_DELETABLE_LAMBDA, self.snapshots))
        if self.drive.enabled() and self.config.maxSnapshotsInGoogleDrive() > 0 and self.driveDeletableSnapshotCount() >= self.config.maxSnapshotsInGoogleDrive():
            deleteFromDrive = self.getDeleteScheme().getOldest(filter(DRIVE_DELETABLE_LAMBDA, self.snapshots))

        for snapshot in self.snapshots:
            snapshot.deleteNextFromDrive = (snapshot == deleteFromDrive)
            snapshot.deleteNextFromHa = (snapshot == deleteFromHa)

    def getExceptionInfo(self) -> str:
        if self.last_error:
            if isinstance(self.last_error, WrappedException):
                return formatException(self.last_error.innerException)
            if isinstance(self.last_error, Exception):
                return formatException(self.last_error)
            else:
                return str(self.last_error)
        else:
            return ""

    def getDebugInfo(self):
        return {
            'addonVersion': self.hassio.self_info.get('version', 'unknown'),
            'host': self.hassio.host_info,
            'www.googleapis.com': resolveHostname('www.googleapis.com'),
            'oauth2.googleapis.com': resolveHostname('oauth2.googleapis.com'),
            'successes': self.successes,
            'failures': self.failures,
            'uploads': self.uploads,
            'syncStarted': formatTimeSince(self.last_refresh),
            'started': formatTimeSince(self.start_time),
            'driveSnapshots': self.driveSnapshotCount(),
            'haSnapshots': self.haSnapshotCount()
        }

    def getError(self, error=None) -> str:
        if not error:
            error = self.last_error
        if error is not None:
            if isinstance(error, WrappedException):
                return self.getError(error.innerException)
            if isinstance(error, HttpAccessTokenRefreshError):
                return "creds_bad"
            elif isinstance(error, Exception):
                formatted = formatException(error)
                if DRIVE_FULL_MESSAGE in formatted:
                    return "drive_full"
                elif CANT_REACH_GOOGLE_MESSAGE in formatted:
                    return "cant_reach_google"
                elif CANT_REACH_GOOGLE_AUTH_MESSAGE in formatted:
                    return "cant_reach_google"
                elif CANT_REACH_GOOGLE_UNAVAILABLE_MESSAGE in formatted:
                    return "cant_reach_google"
                elif GOOGLE_TIMEOUT_1_MESSAGE in formatted:
                    return "google_timeout"
                elif GOOGLE_TIMEOUT_2_MESSAGE in formatted:
                    return "google_timeout"
                elif GOOGLE_SESSION_EXPIRED in formatted:
                    return "google_session_expired"
                elif GOOGLE_500_ERROR in formatted:
                    return "google_server_error"
                return "default_error"
            else:
                return "default_error"
        else:
            return ""
