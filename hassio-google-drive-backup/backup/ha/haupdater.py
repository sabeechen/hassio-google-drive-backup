from datetime import timedelta

from aiohttp.client_exceptions import ClientResponseError
from injector import inject, singleton

from ..model import Coordinator, Snapshot
from ..config import Config, Setting, Startable
from ..util import GlobalInfo, Backoff, Estimator
from .harequests import HaRequests
from ..time import Time
from ..worker import Worker
from ..const import SOURCE_HA, SOURCE_GOOGLE_DRIVE
from ..logger import getLogger

logger = getLogger(__name__)

NOTIFICATION_TITLE = "Home Assistant Google Drive Backup is Having Trouble"
NOTIFICATION_DESC_LINK = "The add-on is having trouble backing up your snapshots and needs attention.  Please visit the add-on [status page]({0}) for details."
NOTIFICATION_DESC_STATIC = "The add-on is having trouble backing up your snapshots and needs attention.  Please visit the add-on status page for details."

MAX_BACKOFF = 60 * 5  # 5 minutes
FIRST_BACKOFF = 60  # 1 minute

# Wait 5 minutes before logging
NOTIFY_DELAY = 60 * 5  # 5 minute

STALE_ENTITY_NAME = "sensor.snapshots_stale"
SNAPSHOT_ENTITY_NAME = "sensor.snapshot_backup"

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

        self._last_snapshot_update = None
        self.last_snapshot_update_time = time.now() - timedelta(days=1)

    async def update(self):
        try:
            if self._config.get(Setting.ENABLE_SNAPSHOT_STALE_SENSOR):
                await self._requests.updateSnapshotStaleSensor(self._stale())
            if self._config.get(Setting.ENABLE_SNAPSHOT_STATE_SENSOR):
                await self._maybeSendSnapshotUpdate()
            if self._config.get(Setting.NOTIFY_FOR_STALE_SNAPSHOTS):
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
        except ClientResponseError as e:
            if self._first_error is None:
                self._first_error = self._time.now()
            if int(e.status / 100) == 5:
                if self._time.now() > self._first_error + timedelta(seconds=NOTIFY_DELAY):
                    logger.error(
                        "Unable to reach Home Assistant (HTTP {0}).  This is normal if Home Assistant is restarting.  You will probably see some errors in the supervisor logs until it comes back online.".format(e.status))
            else:
                logger.error("Trouble updating Home Assistant sensors.")
            self._last_snapshot_update = None
            await self._time.sleepAsync(self._backoff.backoff(e))
        except Exception as e:
            self._last_snapshot_update = None
            logger.error("Trouble updating Home Assistant sensors.")
            logger.printException(e)
            await self._time.sleepAsync(self._backoff.backoff(e))

    async def _maybeSendSnapshotUpdate(self):
        update = self._buildSnapshotUpdate()
        if update != self._last_snapshot_update or self._time.now() > self.last_snapshot_update_time + timedelta(hours=1):
            await self._requests.updateEntity(SNAPSHOT_ENTITY_NAME, update)
            self._last_snapshot_update = update
            self.last_snapshot_update_time = self._time.now()

    def _stale(self):
        if self._info._first_sync:
            return False
        if not self._info._last_error:
            return False
        return self._time.now() > self._info._last_success + timedelta(seconds=self._config.get(Setting.SNAPSHOT_STALE_SECONDS))

    def _state(self):
        if self._stale():
            return "error"
        else:
            return "waiting" if self._info._first_sync else "backed_up"

    def _buildSnapshotUpdate(self):
        snapshots = self._coordinator.snapshots()
        last = "Never"
        if len(snapshots) > 0:
            last = max(snapshots, key=lambda s: s.date()).date().isoformat()

        def makeSnapshotData(snapshot: Snapshot):
            return {
                "name": snapshot.name(),
                "date": str(snapshot.date().isoformat()),
                "state": snapshot.status(),
                "size": snapshot.sizeString()
            }
        return {
            "state": self._state(),
            "attributes": {
                "friendly_name": "Snapshot State",
                "last_snapshot": last,  # type: ignore
                "snapshots_in_google_drive": len(list(filter(lambda s: s.getSource(SOURCE_GOOGLE_DRIVE) is not None, snapshots))),
                "snapshots_in_hassio": len(list(filter(lambda s: s.getSource(SOURCE_HA), snapshots))),
                "snapshots_in_home_assistant": len(list(filter(lambda s: s.getSource(SOURCE_HA), snapshots))),
                "size_in_google_drive": Estimator.asSizeString(sum(map(lambda v: v.sizeInt(), filter(lambda s: s.getSource(SOURCE_GOOGLE_DRIVE), snapshots)))),
                "size_in_home_assistant": Estimator.asSizeString(sum(map(lambda v: v.sizeInt(), filter(lambda s: s.getSource(SOURCE_HA), snapshots)))),
                "snapshots": list(map(makeSnapshotData, snapshots))
            }
        }
