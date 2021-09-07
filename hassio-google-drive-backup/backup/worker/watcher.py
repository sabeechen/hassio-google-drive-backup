from datetime import datetime, timedelta
from threading import Lock
from typing import List, Optional

from injector import inject, singleton
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from ..config import Config, Setting, Startable
from ..time import Time
from .trigger import Trigger
from ..logger import getLogger

logger = getLogger(__name__)

REPORT_DELAY_SECONDS = 5


@singleton
class Watcher(Trigger, FileSystemEventHandler, Startable):
    @inject
    def __init__(self, time: Time, config: Config):
        super().__init__()
        self.time = time
        self.last_list: Optional[List[str]] = None
        self.config: Config = config
        self.observer: Observer = Observer()
        self.last_change: datetime = time.now()
        self.report: bool = False
        self.report_debug: bool = True
        self.lock: Lock = Lock()
        self.started = False

    async def start(self):
        self.observer.schedule(self, self.config.get(
            Setting.BACKUP_DIRECTORY_PATH), recursive=False)
        self.observer.start()
        self.started = True

    def isStarted(self):
        return self.started

    def name(self):
        return "Backup Directory Watcher"

    def on_any_event(self, event):
        """
        Backup directory was changed in some way
        """
        logger.debug("Backup directory changed")
        try:
            self.lock.acquire()
            self.last_change = self.time.now()
            self.report = True

            if self.report_debug:
                logger.debug(
                    "Backup directory was written to, we'll reload backups from Home Assistant soon")
                self.report_debug = False
        finally:
            self.lock.release()

    def on_moved(self, event):
        logger.debug("Backup directory moved event")

    def on_created(self, event):
        logger.debug("Backup directory created event")

    def on_deleted(self, event):
        # Always trigger on delete, most likely a backup was deleted
        self.trigger()
        logger.debug("Backup directory deleted event")

    def on_modified(self, event):
        logger.debug("Backup directory modified event")

    def haveFilesChanged(self) -> bool:
        try:
            self.lock.acquire()
            if self.report and self.time.now() > self.last_change + timedelta(seconds=REPORT_DELAY_SECONDS):
                logger.info("Backup directory changed")
                self.report = False
                self.report_debug = True
                return True
            return False
        finally:
            self.lock.release()

    def check(self):
        if self.haveFilesChanged():
            return True
        else:
            return super().check()

    async def stop(self):
        self.observer.stop()
        self.observer.join()
