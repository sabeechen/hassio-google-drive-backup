from .snapshots import Snapshot
from .snapshots import DriveSnapshot
from .snapshots import HASnapshot
from .helpers import makeDict
from .helpers import count
from .helpers import take
from .helpers import formatException
from .drive import Drive
from .hassio import Hassio, SnapshotInProgress
from .watcher import Watcher
from .config import Config
from .time import Time
from pprint import pformat
from dateutil.relativedelta import relativedelta
from threading import Lock
from datetime import timedelta
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from oauth2client.client import Credentials  # type: ignore
from .backupscheme import GenerationalScheme, OldestScheme
from .logbase import LogBase
from .knownerror import KnownError

BAD_TOKEN_ERROR_MESSAGE: str = "Google rejected the credentials we gave it.  Please use the \"Reauthorize\" button on the right to give the Add-on permission to use Google Drive again.  This can happen if you change your account password, you revoke the add-on's access, your Google Account has been inactive for 6 months, or your system's clock is off."

DATE_LAMBDA: Callable[[Snapshot], datetime] = lambda s: s.date()
HA_LAMBDA: Callable[[Snapshot], bool] = lambda s: s.isInHA()
DRIVE_LAMBDA: Callable[[Snapshot], bool] = lambda s: s.isInDrive()
NOT_DRIVE_LAMBDA: Callable[[Snapshot], bool] = lambda s: not s.isInDrive()
SLUG_LAMBDA: Callable[[Snapshot], str] = lambda s: s.slug()
DRIVE_SLUG_LAMBDA: Callable[[DriveSnapshot], str] = lambda s: s.slug()
HA_SLUG_LAMBDA: Callable[[HASnapshot], str] = lambda s: s.slug()

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
        self.addon_info: Optional[Dict[Any, Any]] = None
        self.host_info: Optional[Dict[Any, Any]] = None
        self.sim_error: Optional[str] = None
        self.next_error_rety: datetime = self.time.now()
        self.next_error_backoff: int = ERROR_BACKOFF_MIN_SECS
        self.one_shot: bool = False
        self.snapshots_stale: bool = False

    def getDeleteScheme(self):
        gen_config = self.config.getGenerationalConfig()
        if gen_config:
            return GenerationalScheme(self.time, gen_config)
        else:
            return OldestScheme()

    def saveCreds(self, creds: Credentials) -> None:
        self.drive.saveCreds(creds)
        self.one_shot = True

    def simulateError(self, error: Optional[str]) -> None:
        self.sim_error = error

    def driveEnabled(self) -> bool:
        return self.drive.enabled()

    def driveSnapshotCount(self) -> int:
        return count(self.snapshots, DRIVE_LAMBDA)

    def haSnapshotCount(self) -> int:
        return count(self.snapshots, HA_LAMBDA)

    def doBackupWorkflow(self) -> None:
        self.last_refresh = self.time.now()
        try:
            self.lock.acquire()
            if self.addon_info is None:
                self.host_info = self.hassio.readHostInfo()
                self.addon_info = self.hassio.readAddonInfo()
            self._checkForBackup()
            self.snapshots_stale = False
            self.last_error = None
            self.last_success = self.time.now()
            self.next_error_rety = self.time.now()
            self.next_error_backoff = ERROR_BACKOFF_MIN_SECS
        except Exception as e:
            self.error(formatException(e))
            self.error("A retry will be attempted in {} seconds".format(self.next_error_backoff))
            self.next_error_rety = self.time.now() + relativedelta(seconds=self.next_error_backoff)
            self.next_error_backoff = self.next_error_backoff * ERROR_BACKOFF_EXP_MUL
            if self.next_error_backoff > ERROR_BACKOFF_MAX_SECS:
                self.next_error_backoff = ERROR_BACKOFF_MAX_SECS
            self.last_error = e
            self.maybeSendStalenessNotifications()
        finally:
            self.lock.release()

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
        time_that_day_local = datetime(newest_local.year, newest_local.month, newest_local.day, hour, minute, 0, tzinfo=self.time.local_tz)
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
                    if self.addon_info and self.host_info:
                        url = self.addon_info["webui"].replace("[HOST]", self.host_info["hostname"])
                        self.hassio.sendNotification("Hass.io Google Drive is Having Trouble", "The add-on is having trouble backing up your snapshots and needs attention.  Please visit the [status page](" + url + ") for details.")
                    else:
                        self.hassio.sendNotification("Hass.io Google Drive is Having Trouble", "The add-on is having trouble backing up your snapshots and needs attention.  Please visit the status page for details.")
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
                return
        raise Exception("Couldn't find this snapshot")

    def startSnapshot(self) -> Snapshot:
        self.info("Creating new snapshot")
        for snapshot in self.snapshots:
            if snapshot.isPending():
                raise SnapshotInProgress()
        snapshot = self.hassio.newSnapshot()
        self.snapshots.append(snapshot)
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

        added_from_ha: bool = False
        for snapshot_from_ha in ha_snapshots:
            if not snapshot_from_ha.slug() in local_map:
                ha_snapshot: Snapshot = Snapshot(snapshot_from_ha)
                self.snapshots.append(ha_snapshot)
                local_map[ha_snapshot.slug()] = ha_snapshot
                added_from_ha = True
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

        self.snapshots.sort(key=DATE_LAMBDA)
        if (self.config.verbose()):
            self.debug("Final Snapshots:")
            self.debug(pformat(self.snapshots))

    def _purgeDriveBackups(self) -> None:
        while self.drive.enabled() and self.config.maxSnapshotsInGoogleDrive() > 0 and self.driveSnapshotCount() > self.config.maxSnapshotsInGoogleDrive():
            oldest: Snapshot = self.getDeleteScheme().getOldest(filter(DRIVE_LAMBDA, self.snapshots))
            self.drive.deleteSnapshot(oldest)
            if oldest.isDeleted():
                self.snapshots.remove(oldest)

    def _purgeHaSnapshots(self) -> None:
        while self.config.maxSnapshotsInHassio() > 0 and self.haSnapshotCount() > self.config.maxSnapshotsInHassio():
            oldest_hassio: Snapshot = self.getDeleteScheme().getOldest(filter(HA_LAMBDA, self.snapshots))
            self.hassio.deleteSnapshot(oldest_hassio)
            if not oldest_hassio.isInDrive():
                self.snapshots.remove(oldest_hassio)

    def _checkForBackup(self) -> None:
        # Get the local and remote snapshots available
        self._syncSnapshots()
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

        for snapshot in self.snapshots:
            snapshot.setWillBackup(snapshot in should_backup)

        for to_backup in should_backup:
            if self.drive.enabled():
                snapshot.setWillBackup(True)
                self.info("Uploading {}".format(to_backup))
                if not self.folder_id:
                    raise Exception("No folder Id")
                self.drive.saveSnapshot(to_backup, self.hassio.downloadUrl(to_backup), self.folder_id)

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
