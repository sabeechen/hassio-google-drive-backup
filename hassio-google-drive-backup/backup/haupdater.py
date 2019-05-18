import requests

from .logbase import LogBase
from .config import Config
from .harequests import HaRequests
from .time import Time
from .globalinfo import GlobalInfo
from .helpers import formatException
from .backoff import Backoff
from .worker import Worker
from datetime import timedelta

NOTIFICATION_TITLE = "Hass.io Google Drive Backup is Having Trouble"
NOTIFICATION_DESC_LINK = "The add-on is having trouble backing up your snapshots and needs attention.  Please visit the add-on [status page]({0}) for details."
NOTIFICATION_DESC_STATIC = "The add-on is having trouble backing up your snapshots and needs attention.  Please visit the add-on status page for details."

MAX_BACKOFF = 60 * 5  # 5 minutes
FIRST_BACKOFF = 20  # 1 minute


class HaUpdater(Worker, LogBase):
    def __init__(self, requests: HaRequests, config: Config, time: Time, global_info: GlobalInfo):
        super().__init__("Sensor Updater", self.update, time, 5)
        self._time = time
        self._config = config
        self._requests: HaRequests = requests
        self._cache = []
        self._info = global_info
        self._notified = False
        self._ha_offline = False
        self._snapshots_stale = True
        self._backoff = Backoff(max=MAX_BACKOFF, base=FIRST_BACKOFF)

    def update(self):
        try:
            if self._config.enableSnapshotStaleSensor():
                self._requests.updateSnapshotStaleSensor(self._stale())
            if self._config.enableSnapshotStateSensor() and self._snapshots_stale:
                self._requests.updateSnapshotsSensor(self._state(), self._cache)
                self._snapshots_stale = False
            if self._config.notifyForStaleSnapshots():
                if self._stale() and not self._notified:
                    if self._info.url is None or len(self._info.url) == 0:
                        message = NOTIFICATION_DESC_STATIC
                    else:
                        message = NOTIFICATION_DESC_LINK.format(self._info.url)
                    self._requests.sendNotification(NOTIFICATION_TITLE, message)
                    self._notified = True
                elif not self._stale() and self._notified:
                    self._requests.dismissNotification()
                    self._notified = False
            if self._ha_offline:
                self._ha_offline = False
            self._backoff.reset()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 502:
                if not self._ha_offline:
                    self.error("Unable to reach Home Assistant.  Is it restarting?")
                    self._ha_offline = True
            else:
                self.error("Trouble updating Home Assistant sensors.")
                self.error(formatException(e))
            self._snapshots_stale = True
            self._time.sleep(self._backoff.backoff(e))
        except Exception as e:
            self._snapshots_stale = True
            self.error("Trouble updating Home Assistant sensors.")
            self.error(formatException(e))
            self._time.sleep(self._backoff.backoff(e))

    def updateSnapshots(self, snapshots):
        self._cache = snapshots
        self._snapshots_stale = True

    def _stale(self):
        if self._info._first_sync:
            return False
        if not self._info._last_error:
            return False
        return self._time.now() > self._info._last_failure_time + timedelta(minutes=self._config.snapshotStaleMinutes())

    def _state(self):
        if self._stale():
            return "error"
        else:
            return "waiting" if self._info._first_sync else "backed_up"
