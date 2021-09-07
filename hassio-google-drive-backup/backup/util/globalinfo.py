
from datetime import timedelta
from threading import Lock

from injector import inject, singleton

from ..time import Time
from ..logger import getLogger

logger = getLogger(__name__)


@singleton
class GlobalInfo():
    @inject
    def __init__(self, time: Time):
        self._time = time
        self._syncs = 0
        self._failures = 0
        self._last_error = 0
        self._successes = 0
        self._last_failure_time = None
        self._uploads = 0
        self._last_upload = None
        self._last_success = time.now()
        self._last_sync_success = None
        self._last_upload_size = None
        self._last_sync_start = None
        self._last_error = None
        self._supress_error = False
        self.credVersion = 0
        self._first_sync = True
        self._multipleDeletesPermitted = False
        self._dns_info = None
        self._skip_space_check_once = False
        self._ignore_errors_for_now = False
        self._start_time = time.now()

        self.ha_ssl = False
        self.addons = None
        self.ha_port = None
        self.slug = None
        self.url = ""
        self.debug = {}
        self.lock = Lock()
        self.backup_cooldown_time = time.now()

    def ignoreErrorsForNow(self):
        return self._ignore_errors_for_now

    def setIngoreErrorsForNow(self, value):
        self._ignore_errors_for_now = value

    def failureCount(self):
        return self._failures

    def refresh(self):
        pass

    def setDnsInfo(self, info):
        self._dns_info = info

    def getDnsInfo(self):
        return self._dns_info

    def success(self):
        self._first_sync = False
        self._last_error = None
        self._last_success = self._time.now()
        self._last_sync_success = self._time.now()
        self._successes += 1
        self._multipleDeletesPermitted = False
        self.setIngoreErrorsForNow(False)

    def sync(self):
        self._last_sync_start = self._time.now()
        self._syncs += 1

    def failed(self, error):
        self._first_sync = False
        self._last_error = error
        self._failures += 1
        self._last_failure_time = self._time.now()
        self._supress_error = False
        self.setIngoreErrorsForNow(False)

    def suppressError(self):
        self._supress_error = True

    def isErrorSuppressed(self):
        return self.suppressError

    def upload(self, size):
        self._last_upload = self._time.now()
        self._uploads += 1
        self._last_upload_size = size

    def credsSaved(self):
        self.credVersion += 1

    def isPermitMultipleDeletes(self) -> bool:
        return self._multipleDeletesPermitted

    def allowMultipleDeletes(self) -> bool:
        self._multipleDeletesPermitted = True

    def addDebugInfo(self, key, value):
        with self.lock:
            self.debug[key] = value

    def isSkipSpaceCheckOnce(self):
        return self._skip_space_check_once

    def setSkipSpaceCheckOnce(self, val):
        self._skip_space_check_once = val

    def triggerBackupCooldown(self, delay: timedelta):
        self.backup_cooldown_time = self._time.now() + delay

    def backupCooldownTime(self):
        return self.backup_cooldown_time
