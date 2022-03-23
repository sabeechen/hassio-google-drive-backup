from datetime import timedelta

from aiohttp.client_exceptions import ClientResponseError
from injector import inject, singleton

from ..model import Coordinator, Backup
from ..config import Config, Setting
from ..util import GlobalInfo, Backoff, Estimator
from .harequests import HaRequests
from ..time import Time
from ..worker import Worker
from ..const import SOURCE_HA, SOURCE_GOOGLE_DRIVE
from ..logger import getLogger

logger = getLogger(__name__)

NOTIFICATION_TITLE = "Home Assistant Google Drive Backup is Having Trouble"
NOTIFICATION_DESC_LINK = "The add-on is having trouble making backups and needs attention.  Please visit the add-on [status page]({0}) for details."
NOTIFICATION_DESC_STATIC = "The add-on is having trouble making backups and needs attention.  Please visit the add-on status page for details."

MAX_BACKOFF = 60 * 5  # 5 minutes
FIRST_BACKOFF = 60  # 1 minute

# Wait 5 minutes before logging
NOTIFY_DELAY = 60 * 5  # 5 minute

OLD_BACKUP_ENTITY_NAME = "sensor.snapshot_backup"
BACKUP_ENTITY_NAME = "sensor.backup_state"

REASSURING_MESSAGE = "Unable to reach Home Assistant (HTTP {0}).  This is normal if Home Assistant is restarting.  You will probably see some errors in the supervisor logs until it comes back online."


@singleton
class HaUpdater(Worker):
    @inject
    def __init__(self, requests: HaRequests, coordinator: Coordinator, config: Config, time: Time, global_info: GlobalInfo):
        super().__init__("Sensor Updater", self.update, time, 10)
        self._time = time
        self._coordinator = coordinator
        self._config = config
        self._requests: HaRequests = requests
        self._info = global_info
        self._notified = False
        self._backoff = Backoff(max=MAX_BACKOFF, base=FIRST_BACKOFF)
        self._first_error = None
        self._trigger_once = False

        self._last_backup_update = None
        self.last_backup_update_time = time.now() - timedelta(days=1)

    async def update(self):
        try:
            if self._config.get(Setting.ENABLE_BACKUP_STALE_SENSOR):
                await self._requests.updateBackupStaleSensor('on' if self._stale() else 'off')
            if self._config.get(Setting.ENABLE_BACKUP_STATE_SENSOR):
                await self._maybeSendBackupUpdate()
            if self._config.get(Setting.NOTIFY_FOR_STALE_BACKUPS):
                if self._stale() and not self._notified:
                    if self._info.url is None or len(self._info.url) == 0:
                        message = NOTIFICATION_DESC_STATIC
                    else:
                        message = NOTIFICATION_DESC_LINK.format(self._info.url)
                    await self._requests.sendNotification(NOTIFICATION_TITLE, message)
                    self._notified = True
                elif not self._stale() and self._notified:
                    await self._requests.dismissNotification()
                    self._notified = False
            self._backoff.reset()
            self._first_error = None
            self._trigger_once = False
        except ClientResponseError as e:
            if self._first_error is None:
                self._first_error = self._time.now()
            if int(e.status / 100) == 5:
                if self._time.now() > self._first_error + timedelta(seconds=NOTIFY_DELAY):
                    logger.error(
                        "Unable to reach Home Assistant (HTTP {0}).  This is normal if Home Assistant is restarting.  You will probably see some errors in the supervisor logs until it comes back online.".format(e.status))
            else:
                logger.error("Trouble updating Home Assistant sensors.")
            self._last_backup_update = None
            await self._time.sleepAsync(self._backoff.backoff(e))
        except Exception as e:
            self._last_backup_update = None
            logger.error("Trouble updating Home Assistant sensors.")
            logger.printException(e)
            await self._time.sleepAsync(self._backoff.backoff(e))

    async def _maybeSendBackupUpdate(self):
        update = self._buildBackupUpdate()
        if self._trigger_once or update != self._last_backup_update or self._time.now() > self.last_backup_update_time + timedelta(hours=1):
            if self._config.get(Setting.CALL_BACKUP_SNAPSHOT):
                await self._requests.updateEntity(OLD_BACKUP_ENTITY_NAME, update)
            else:
                await self._requests.updateEntity(BACKUP_ENTITY_NAME, update)
            self._last_backup_update = update
            self.last_backup_update_time = self._time.now()

    def _stale(self):
        if self._info._first_sync:
            return False
        if not self._info._last_error:
            return False
        return self._time.now() > self._info._last_success + timedelta(seconds=self._config.get(Setting.BACKUP_STALE_SECONDS))

    def _state(self):
        if self._stale():
            return "error"
        else:
            return "waiting" if self._info._first_sync else "backed_up"

    def triggerRefresh(self):
        self._trigger_once = True

    def _buildBackupUpdate(self):
        backups = list(filter(lambda s: not s.ignore(), self._coordinator.backups()))
        last = "Never"
        if len(backups) > 0:
            last = max(backups, key=lambda s: s.date()).date().isoformat()

        def makeBackupData(backup: Backup):
            return {
                "name": backup.name(),
                "date": str(backup.date().isoformat()),
                "state": backup.status(),
                "size": backup.sizeString(),
                "slug": backup.slug()
            }
        ha_backups = list(filter(lambda s: s.getSource(SOURCE_HA) is not None, backups))
        drive_backups = list(filter(lambda s: s.getSource(SOURCE_GOOGLE_DRIVE) is not None, backups))

        last_uploaded = "Never"
        if len(drive_backups) > 0:
            last_uploaded = max(drive_backups, key=lambda s: s.date()).date().isoformat()
        if self._config.get(Setting.CALL_BACKUP_SNAPSHOT):
            return {
                "state": self._state(),
                "attributes": {
                    "friendly_name": "Snapshot State",
                    "last_snapshot": last,  # type: ignore
                    "snapshots_in_google_drive": len(drive_backups),
                    "snapshots_in_hassio": len(ha_backups),
                    "snapshots_in_home_assistant": len(ha_backups),
                    "size_in_google_drive": Estimator.asSizeString(sum(map(lambda v: v.sizeInt(), drive_backups))),
                    "size_in_home_assistant": Estimator.asSizeString(sum(map(lambda v: v.sizeInt(), ha_backups))),
                    "snapshots": list(map(makeBackupData, backups))
                }
            }
        else:
            next = self._coordinator.nextBackupTime()
            if next is not None:
                next = next.isoformat()
            return {
                "state": self._state(),
                "attributes": {
                    "friendly_name": "Backup State",
                    "last_backup": last,  # type: ignore
                    "next_backup": next,
                    "last_uploaded": last_uploaded,
                    "backups_in_google_drive": len(drive_backups),
                    "backups_in_home_assistant": len(ha_backups),
                    "size_in_google_drive": Estimator.asSizeString(sum(map(lambda v: v.sizeInt(), drive_backups))),
                    "size_in_home_assistant": Estimator.asSizeString(sum(map(lambda v: v.sizeInt(), ha_backups))),
                    "backups": list(map(makeBackupData, backups))
                }
            }
