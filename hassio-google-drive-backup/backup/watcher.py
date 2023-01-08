from datetime import timedelta
from threading import Lock
from asyncio import Event

from injector import inject, singleton
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from backup.config import Config, Setting, Startable
from backup.time import Time
from backup.worker import Trigger
from backup.logger import getLogger
from backup.ha import HaSource
from asyncio import get_event_loop
from os.path import join, abspath

logger = getLogger(__name__)

REPORT_DELAY_SECONDS = 5
LOG_INTERVAL = timedelta(seconds=30)
CHANGES_CHECK_DELAY = timedelta(seconds=10)


@singleton
class Watcher(Trigger, FileSystemEventHandler, Startable):
    @inject
    def __init__(self, time: Time, config: Config, source: HaSource):
        super().__init__()
        self.time = time
        self.config: Config = config
        self.observer: Observer = Observer()
        self._source = source
        self.lock: Lock = Lock()
        self.noticed_change_signal = Event()
        self._changes_have_happened = False
        self._last_change_time = None
        self._last_log_time = None
        self._last_notified_time = None
        self._loop = get_event_loop()

    async def start(self):
        if not self.config.get(Setting.WATCH_BACKUP_DIRECTORY):
            return
        self.observer.schedule(self, self.config.get(
            Setting.BACKUP_DIRECTORY_PATH), recursive=False)
        self.observer.start()

    def name(self):
        return "Backup Directory Watcher"

    def on_any_event(self, event: FileSystemEvent):
        if event.is_directory:
            # ignore any directory level events that bubble up
            return
        if event.event_type in ['modified', 'created']:
            return
        logger.trace("Backup directory modified: %s %s", event.event_type, event.src_path)
        with self.lock:
            self._last_change_time = self.time.now()
            self._changes_have_happened = True

            # Provide periodic log messages to indicate we'll backup soon.
            if not self._last_log_time:
                logger.info("A backup directory file was modified, we'll check for new backups soon.")
                self._last_log_time = self.time.now()
            elif (self.time.now() - self._last_log_time) > LOG_INTERVAL:
                logger.info("The backup directory is still being written to, waiting...")
                self._last_log_time = self.time.now()
            if not self.noticed_change_signal.is_set():
                self._loop.call_soon_threadsafe(self.noticed_change_signal.set)

    async def check(self):
        if not self._changes_have_happened:
            return

        check_backup_source = False
        with self.lock:
            if not self._last_change_time:
                return
            if self.time.now() - self._last_change_time > CHANGES_CHECK_DELAY:
                check_backup_source = True
                self._last_change_time = None
                self._changes_have_happened = False
        if check_backup_source:
            logger.debug("Checking backup source for changes...")
            await self._source.get()
            if self._source.query_had_changes:
                self.trigger()
        return await super().check()

    async def stop(self):
        if not self.config.get(Setting.WATCH_BACKUP_DIRECTORY):
            return
        self.observer.stop()
        self.observer.join()
