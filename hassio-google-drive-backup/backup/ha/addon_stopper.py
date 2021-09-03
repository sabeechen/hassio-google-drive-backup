import json
import os

from backup.config import Config, Setting
from backup.worker import Worker
from backup.exceptions import SupervisorFileSystemError
from .harequests import HaRequests
from injector import inject, singleton
from backup.time import Time
from backup.logger import getLogger
from datetime import timedelta
from asyncio import Lock

LOGGER = getLogger(__name__)
CHECK_DURATION = timedelta(seconds=60)
ATTR_STATE = "state"
ATTR_WATCHDOG = "watchdog"
ATTR_NAME = "name"
STATE_STOPPED = "stopped"
STATE_STARTED = "started"


@singleton
class AddonStopper(Worker):
    @inject
    def __init__(self, config: Config, requests: HaRequests, time: Time):
        super().__init__("StartandStopTimer", self.check, time, 10)
        self.requests = requests
        self.config = config
        self.time = time
        self.must_start = set()
        self.must_enable_watchdog = set()
        self.stop_start_check_time = time.now()
        self._backing_up = False
        self.allow_run = False
        self.lock = Lock()

    async def start(self, schedule=True):
        if schedule:
            await super().start()
        if os.path.isfile(self.config.get(Setting.STOP_ADDON_STATE_PATH)):
            with open(self.config.get(Setting.STOP_ADDON_STATE_PATH)) as file:
                data = json.load(file)
                self.must_enable_watchdog = set(data.get("watchdog", []))
                self.must_start = set(data.get("start", []))

    def allowRun(self):
        if not self.allow_run:
            for slug in self.config.get(Setting.STOP_ADDONS).split(','):
                if len(slug) == 0:
                    continue
                self.must_start.add(slug)
            self.allow_run = True

    def isBackingUp(self, backingUp):
        self._backing_up = backingUp

    async def stopAddons(self, self_slug):
        async with self.lock:
            self._backing_up = True
            for slug in self.config.get(Setting.STOP_ADDONS).split(','):
                if slug == self_slug or len(slug) == 0:
                    # Don't ask the supervisor to stop yourself.  That would be BAD.
                    continue
                try:
                    info = await self.requests.getAddonInfo(slug)
                    if info.get(ATTR_STATE, None) == STATE_STARTED:
                        if info.get(ATTR_WATCHDOG, False):
                            try:
                                LOGGER.info("Temporarily disabling watchdog for addon '%s'", info.get(ATTR_NAME, slug))
                                await self.requests.updateAddonOptions(slug, {ATTR_WATCHDOG: False})
                                self.must_enable_watchdog.add(slug)
                            except Exception as e:
                                LOGGER.error("Unable to disable watchdog for addon {0}".format(info.get(ATTR_NAME, slug)))
                                LOGGER.printException(e)
                        try:
                            LOGGER.info("Stopping addon '%s'", info.get(ATTR_NAME, slug))
                            await self.requests.stopAddon(slug)
                            self.must_start.add(slug)
                        except Exception as e:
                            LOGGER.error("Unable to stop addon '{0}'".format(info.get(ATTR_NAME, slug)))
                            LOGGER.printException(e)
                except Exception as e:
                    LOGGER.error("Unable to lookup info for addon '{0}', please check your configuration".format(slug))
                    LOGGER.printException(e)
            self._save()

    async def startAddons(self):
        self._backing_up = False
        self.stop_start_check_time = self.time.now() + CHECK_DURATION
        await self.check()

    async def check(self):
        async with self.lock:
            if self._backing_up:
                return
            if not self.allow_run:
                return
            changes = False
            if len(self.must_start) > 0:
                for slug in list(self.must_start):
                    try:
                        info = await self.requests.getAddonInfo(slug)
                        if info.get(ATTR_STATE, None) == STATE_STOPPED:
                            LOGGER.info("Starting addon '%s'", info.get(ATTR_NAME, slug))
                            await self.requests.startAddon(slug)
                            self.must_start.remove(slug)
                            changes = True
                        elif info.get(ATTR_STATE, None) == 'started' and self.time.now() > self.stop_start_check_time:
                            # Give up on restarting it, looks like it was never stopped
                            self.must_start.remove(slug)
                            changes = True
                    except Exception as e:
                        LOGGER.error("Unable to start addon '%s'", slug)
                        LOGGER.printException(e)
                        self.must_start.remove(slug)
                        changes = True

            if len(self.must_enable_watchdog) > 0:
                for slug in list(self.must_enable_watchdog):
                    if slug in self.must_start:
                        # Wait until we're done trying to start the addon before re-enabling the watchdog, otherwise the supervisor complains
                        continue
                    try:
                        info = await self.requests.getAddonInfo(slug)
                        if not info.get(ATTR_WATCHDOG, True):
                            LOGGER.info("Re-enabling watchdog for addon '%s'", info.get(ATTR_NAME, slug))
                            await self.requests.updateAddonOptions(slug, {ATTR_WATCHDOG: True})
                    except Exception as e:
                        LOGGER.error("Unable to re-enable watchdog for addon '%s'", slug)
                        LOGGER.printException(e)
                    self.must_enable_watchdog.remove(slug)
                    changes = True
            if changes:
                self._save()

    def _save(self):
        try:
            with open(self.config.get(Setting.STOP_ADDON_STATE_PATH), "w") as file:
                json.dump({"start": list(self.must_start), "watchdog": list(self.must_enable_watchdog)}, file)
        except OSError:
            raise SupervisorFileSystemError()
