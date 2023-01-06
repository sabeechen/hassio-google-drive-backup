from .coordinator import Coordinator
from backup.worker import Worker
from injector import inject, singleton
from backup.time import Time
from backup.logger import getLogger
from backup.config import Config, Setting
from .model import BackupDestination
from .precache import Precache
from random import Random
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Any, Dict
from logging import DEBUG

logger = getLogger(__name__)


@dataclass
class CacheItem:
    """Class for keeping track of an item in inventory."""
    valid_until: datetime
    data: Any


@singleton
class DestinationPrecache(Worker, Precache):
    @inject
    def __init__(self, coord: Coordinator, time: Time, dest: BackupDestination, config: Config):
        super().__init__("Traffic Smoothing Cache", self.checkForSmoothing, time, 60)
        self._config = config
        self._coord = coord
        self._dest = dest
        self._offset = Random().random()
        self._cache: Dict[str, CacheItem] = {}
        self._last_error: datetime = None

    async def checkForSmoothing(self):
        if self._config.get(Setting.CACHE_WARMUP_MAX_SECONDS) == 0:
            # disable cache warmup
            return
        try:
            self._coord.setPrecache(self)
            nextSync = self._coord.nextSyncAttempt()
            now = self._time.now()
            if nextSync <= now:
                # No reason to warm the cache if we should sync right now anyway
                return
            if self.cached(self._dest.name(), now):
                # A value is already cached, so don't do anything
                return
            if now >= self.getNextWarmDate():
                # Warm the cache
                logger.debug("Preemptively retrieving and caching info from the backup destination to avoid peak demand")
                data = await self._dest.get()
                validity = nextSync + timedelta(minutes=1)
                self._cache[self._dest.name()] = CacheItem(validity, data)
                self._offset = Random().random()
        except Exception as e:
            # Any error should make us avoid precaching for a solid day.
            logger.debug("Unable to precache data from backup destination")
            logger.printException(e, level=DEBUG)
            self._offset = Random().random()
            if self._config.get(Setting.CACHE_WARMUP_ERROR_TIMEOUT_SECONDS) != 0:
                self._last_error = self._time.now()

    def getNextWarmDate(self):
        warm_date = self._coord.nextSyncAttempt() - timedelta(seconds=self._config.get(Setting.CACHE_WARMUP_MAX_SECONDS) * self._offset)
        if self._last_error:
            return max(warm_date, self._last_error + timedelta(self._config.get(Setting.CACHE_WARMUP_ERROR_TIMEOUT_SECONDS)))
        return warm_date

    def cached(self, source: str, date: datetime) -> Any:
        cached = self._cache.get(source)
        if cached and cached.valid_until >= date:
            return cached.data
        return None

    def clear(self):
        """Clears any precached data"""
        self._cache = {}
