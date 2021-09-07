
from datetime import datetime, timedelta
from typing import Dict, Optional
from dateutil.tz import tzutc
from ..util import Estimator

from ..const import SOURCE_GOOGLE_DRIVE, SOURCE_HA
from ..logger import getLogger

logger = getLogger(__name__)

PROP_TYPE = "type"
PROP_VERSION = "version"
PROP_PROTECTED = "protected"
PROP_RETAINED = "retained"

DRIVE_KEY_TEXT = "Google Drive's backup metadata"
HA_KEY_TEXT = "Home Assistant's backup metadata"


class AbstractBackup():
    def __init__(self, name: str, slug: str, source: str, date: str, size: int, version: str, backupType: str, protected: bool, retained: bool = False, uploadable: bool = False, details={}):
        self._options = None
        self._name = name
        self._slug = slug
        self._source = source
        self._date = date
        self._size = size
        self._retained = retained
        self._uploadable = uploadable
        self._details = details
        self._version = version
        self._backupType = backupType
        self._protected = protected
        self._ignore = False

    def setOptions(self, options):
        self._options = options

    def getOptions(self):
        return self._options

    def name(self) -> str:
        return self._name

    def slug(self) -> str:
        return self._slug

    def size(self) -> int:
        return self._size

    def sizeInt(self) -> int:
        try:
            return int(self.size())
        except ValueError:
            return 0

    def date(self) -> datetime:
        return self._date

    def source(self) -> str:
        return self._source

    def retained(self) -> str:
        return self._retained

    def version(self):
        return self._version

    def backupType(self):
        return self._backupType

    def protected(self):
        return self._protected

    def setRetained(self, retained):
        self._retained = retained

    def uploadable(self) -> bool:
        return self._uploadable

    def considerForPurge(self) -> bool:
        return not self.retained()

    def setUploadable(self, uploadable):
        self._uploadable = uploadable

    def details(self):
        return self._details

    def status(self):
        return None

    def madeByTheAddon(self):
        return True

    def ignore(self):
        return self._ignore

    def setIgnore(self, ignore):
        self._ignore = ignore


class Backup(object):
    """
    Represents a Home Assistant backup stored on Google Drive, locally in
    Home Assistant, or a pending backup we expect to see show up later
    """

    def __init__(self, backup: Optional[AbstractBackup] = None):
        self.sources: Dict[str, AbstractBackup] = {}
        self._purgeNext: Dict[str, bool] = {}
        self._options = None
        self._status_override = None
        self._status_override_args = None
        self._state_detail = None
        self._upload_source = None
        self._upload_source_name = None
        self._upload_fail_info = None
        if backup is not None:
            self.addSource(backup)

    def setOptions(self, options):
        self._options = options

    def getOptions(self):
        return self._options

    def updatePurge(self, source: str, purge: bool):
        self._purgeNext[source] = purge

    def addSource(self, backup: AbstractBackup):
        self.sources[backup.source()] = backup
        if backup.getOptions() and not self.getOptions():
            self.setOptions(backup.getOptions())

    def getStatusDetail(self):
        return self._state_detail

    def setStatusDetail(self, info):
        self._state_detail = info

    def removeSource(self, source):
        if source in self.sources:
            del self.sources[source]
        if source in self._purgeNext:
            del self._purgeNext[source]

    def getPurges(self):
        return self._purgeNext

    def uploadInfo(self):
        if not self._upload_source:
            return {}
        elif self._upload_source.progress() == 100:
            return {}
        else:
            return {
                'progress': self._upload_source.progress()
            }

    def getSource(self, source: str):
        return self.sources.get(source, None)

    def name(self):
        for backup in self.sources.values():
            return backup.name()
        return "error"

    def slug(self) -> str:
        for backup in self.sources.values():
            return backup.slug()
        return "error"

    def size(self) -> int:
        for backup in self.sources.values():
            return backup.size()
        return 0

    def sizeInt(self) -> int:
        for backup in self.sources.values():
            return backup.sizeInt()
        return 0

    def backupType(self) -> str:
        for backup in self.sources.values():
            return backup.backupType()
        return "error"

    def version(self) -> str:
        for backup in self.sources.values():
            if backup.version() is not None:
                return backup.version()
        return None

    def details(self):
        for backup in self.sources.values():
            if backup.details() is not None:
                return backup.details()
        return {}

    def getUploadInfo(self, time):
        if self._upload_source_name is None:
            return None
        ret = {
            'name': self._upload_source_name
        }
        if self._upload_fail_info:
            ret['failure'] = self._upload_fail_info
        elif self._upload_source is not None:
            ret['progress'] = self._upload_source.progress()
            ret['speed'] = self._upload_source.speed(timedelta(seconds=20))
            ret['total'] = self._upload_source.position()
            ret['started'] = time.formatDelta(self._upload_source.startTime())
        return ret

    def protected(self) -> bool:
        for backup in self.sources.values():
            return backup.protected()
        return False

    def ignore(self) -> bool:
        for backup in self.sources.values():
            if not backup.ignore():
                return False
        return True

    def date(self) -> datetime:
        for backup in self.sources.values():
            return backup.date()
        return datetime.now(tzutc())

    def sizeString(self) -> str:
        size_string = self.size()
        if type(size_string) == str:
            return size_string
        return Estimator.asSizeString(size_string)

    def status(self) -> str:
        # TODO: Drive Specific
        if self._status_override is not None:
            return self._status_override.format(*self._status_override_args)

        for backup in self.sources.values():
            status = backup.status()
            if status:
                return status

        inDrive = self.getSource(SOURCE_GOOGLE_DRIVE) is not None
        inHa = self.getSource(SOURCE_HA) is not None

        if inDrive and inHa:
            return "Backed Up"
        if inDrive:
            return "Drive Only"
        if inHa:
            return "HA Only"
        return "Deleted"

    def isDeleted(self) -> bool:
        return len(self.sources) == 0

    def overrideStatus(self, format, *args) -> None:
        self._status_override = format
        self._status_override_args = args

    def setUploadSource(self, source_name: str, source):
        self._upload_source = source
        self._upload_source_name = source_name
        self._upload_fail_info = None

    def clearUploadSource(self):
        self._upload_source = None
        self._upload_source_name = None
        self._upload_fail_info = None

    def uploadFailure(self, info):
        self._upload_source = None
        self._upload_fail_info = info

    def clearStatus(self):
        self._status_override = None
        self._status_override_args = None

    def __str__(self) -> str:
        return "<Slug: {0} {1} {2}>".format(self.slug(), " ".join(self.sources), self.date().isoformat())

    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def __repr__(self) -> str:
        return self.__str__()
