from .logbase import LogBase
from .config import Config
from .harequests import HaRequests
from .time import Time
from .globalinfo import GlobalInfo
from .helpers import formatException
from .backoff import Backoff
from .worker import Worker
from .settings import Setting
from datetime import timedelta
from injector import inject, singleton
from aiohttp.client_exceptions import ClientResponseError

NOTIFICATION_TITLE = "Hass.io Google Drive Backup is Having Trouble"
NOTIFICATION_DESC_LINK = "The add-on is having trouble backing up your snapshots and needs attention.  Please visit the add-on [status page]({0}) for details."
NOTIFICATION_DESC_STATIC = "The add-on is having trouble backing up your snapshots and needs attention.  Please visit the add-on status page for details."

MAX_BACKOFF = 60 * 5  # 5 minutes
FIRST_BACKOFF = 60  # 1 minute

# Wait 5 minutes before logging
NOTIFY_DELAY = 60 * 5  # 5 minute


@singleton
class HaUpdater(Worker, LogBase):
    @inject
    def __init__(self, requests: HaRequests, config: Config, time: Time, global_info: GlobalInfo):
        super().__init__("Sensor Updater", self.update, time, 5)
        self._time = time
        self._config = config
        self._requests: HaRequests = requests
        self._cache = []
        self._info = global_info
        self._notified = False
        self._snapshots_stale = True
        self._backoff = Backoff(max=MAX_BACKOFF, base=FIRST_BACKOFF)
        self._first_error = None

    async def update(self):
        try:
            if self._config.get(Setting.ENABLE_SNAPSHOT_STALE_SENSOR):
                await self._requests.updateSnapshotStaleSensor(self._stale())
            if self._config.get(Setting.ENABLE_SNAPSHOT_STATE_SENSOR) and self._snapshots_stale:
                await self._requests.updateSnapshotsSensor(self._state(), self._cache)
                self._snapshots_stale = False
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
                    self.error("Unable to reach Home Assistant (HTTP {0}).  Is it restarting?".format(e.status))
            else:
                self.error("Trouble updating Home Assistant sensors.")
                self.error(formatException(e))
            self._snapshots_stale = True
            await self._time.sleepAsync(self._backoff.backoff(e))
        except Exception as e:
            self._snapshots_stale = True
            self.error("Trouble updating Home Assistant sensors.")
            self.error(formatException(e))
            await self._time.sleepAsync(self._backoff.backoff(e))

    def updateSnapshots(self, snapshots):
        self._cache = snapshots
        self._snapshots_stale = True

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
