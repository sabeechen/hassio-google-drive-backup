from .config import Config
from .time import Time
from .logbase import LogBase
from typing import Optional, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import timedelta
from datetime import datetime
from threading import Lock
from .trigger import Trigger

REPORT_DELAY_SECONDS = 5


class Watcher(Trigger, LogBase, FileSystemEventHandler):
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
        self.observer.schedule(self, self.config.backupDirectory(), recursive=False)
        self.observer.start()

    def name(self):
        return "Backup Directory Watcher"

    def on_any_event(self, event):
        """
        Backup directory was changed in some way
        """
        try:
            self.lock.acquire()
            self.last_change = self.time.now()
            self.report = True

            if self.report_debug:
                self.info("Backup directory was written to, we'll reload snapshots from Hassio soon")
                self.report_debug = False
        finally:
            self.lock.release()

    def haveFilesChanged(self) -> bool:
        try:
            self.lock.acquire()
            if self.report and self.time.now() > self.last_change + timedelta(seconds=REPORT_DELAY_SECONDS):
                self.info("Backup directory changed")
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

    def stop(self):
        self.observer.stop()
        self.observer.join()
