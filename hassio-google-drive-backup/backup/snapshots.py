
from datetime import datetime
from .helpers import parseDateTime, strToBool
from typing import Dict, Optional, Any
from .const import SOURCE_GOOGLE_DRIVE, SOURCE_HA
from .exceptions import ensureKey
PROP_KEY_SLUG = "snapshot_slug"
PROP_KEY_DATE = "snapshot_date"
PROP_KEY_NAME = "snapshot_name"
PROP_TYPE = "type"
PROP_VERSION = "version"
PROP_PROTECTED = "protected"
PROP_RETAINED = "retained"

DRIVE_KEY_TEXT = "Google Drive's snapshot metadata"
HA_KEY_TEXT = "Hass.io's snapshot metadata"


class AbstractSnapshot():
    def __init__(self, name: str, slug: str, source: str, date: str, size: int, version: str, snapshotType: str, protected: bool, retained: bool = False, uploadable: bool = False, details={}):
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
        self._snapshotType = snapshotType
        self._protected = protected

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

    def date(self) -> datetime:
        return self._date

    def source(self) -> str:
        return self._source

    def retained(self) -> str:
        return self._retained

    def version(self):
        return self._version

    def snapshotType(self):
        return self._snapshotType

    def protected(self):
        return self._protected

    def setRetained(self, retained):
        self._retained = retained

    def uploadable(self) -> bool:
        return self._uploadable

    def setUploadable(self, uploadable):
        self._uploadable = uploadable

    def details(self):
        return self._details

    def status(self):
        return None


class DriveSnapshot(AbstractSnapshot):

    """
    Represents a Hass.io snapshot stored on Google Drive
    """
    def __init__(self, data: Dict[Any, Any]):
        props = ensureKey('appProperties', data, DRIVE_KEY_TEXT)
        retained = strToBool(props.get(PROP_RETAINED, "False"))
        super().__init__(
            name=ensureKey(PROP_KEY_NAME, props, DRIVE_KEY_TEXT),
            slug=ensureKey(PROP_KEY_SLUG, props, DRIVE_KEY_TEXT),
            date=parseDateTime(ensureKey(PROP_KEY_DATE, props, DRIVE_KEY_TEXT)),
            size=int(ensureKey("size", data, DRIVE_KEY_TEXT)),
            source=SOURCE_GOOGLE_DRIVE,
            snapshotType=props.get(PROP_TYPE, "?"),
            version=props.get(PROP_VERSION, "?"),
            protected=strToBool(props.get(PROP_PROTECTED, "?")),
            retained=retained,
            uploadable=False,
            details=data)
        self._id = ensureKey('id', data, DRIVE_KEY_TEXT)

    def id(self) -> str:
        return self._id

    def __str__(self) -> str:
        return "<Drive: {0} Name: {1} Id: {2}>".format(self.slug(), self.name(), self.id())

    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def __repr__(self) -> str:
        return self.__str__()


class HASnapshot(AbstractSnapshot):
    """
    Represents a Hass.io snapshot stored locally in Home Assistant
    """
    def __init__(self, data: Dict[str, Any], retained=False):
        super().__init__(
            name=ensureKey('name', data, HA_KEY_TEXT),
            slug=ensureKey('slug', data, HA_KEY_TEXT),
            date=parseDateTime(ensureKey('date', data, HA_KEY_TEXT)),
            size=float(ensureKey("size", data, HA_KEY_TEXT)) * 1024 * 1024,
            source=SOURCE_HA,
            snapshotType=ensureKey('type', data, HA_KEY_TEXT),
            version=ensureKey('homeassistant', data, HA_KEY_TEXT),
            protected=ensureKey('protected', data, HA_KEY_TEXT),
            retained=retained,
            uploadable=True,
            details=data)

    def __str__(self) -> str:
        return "<HA: {0} Name: {1} {2}>".format(self.slug(), self.name(), self.date().isoformat())

    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def __repr__(self) -> str:
        return self.__str__()


class Snapshot(object):
    """
    Represents a Hass.io snapshot stored on Google Drive, locally in
    Home Assistant, or a pending snapshot we expect to see show up later
    """
    def __init__(self, snapshot: Optional[AbstractSnapshot] = None):
        self.sources: Dict[str, AbstractSnapshot] = {}
        self._purgeNext: Dict[str, bool] = {}
        self._options = None
        self._status_override = None
        self._status_override_args = None
        if snapshot is not None:
            self.addSource(snapshot)

    def setOptions(self, options):
        self._options = options

    def getOptions(self):
        return self._options

    def updatePurge(self, source: str, purge: bool):
        self._purgeNext[source] = purge

    def addSource(self, snapshot: AbstractSnapshot):
        self.sources[snapshot.source()] = snapshot
        if snapshot.getOptions() and not self.getOptions():
            self.setOptions(snapshot.getOptions())

    def removeSource(self, source):
        if source in self.sources:
            del self.sources[source]
        if source in self._purgeNext:
            del self._purgeNext[source]

    def getPurges(self):
        return self._purgeNext

    def getSource(self, source: str):
        return self.sources.get(source, None)

    def name(self):
        for snapshot in self.sources.values():
            return snapshot.name()
        return "error"

    def slug(self) -> str:
        for snapshot in self.sources.values():
            return snapshot.slug()
        return "error"

    def size(self) -> int:
        for snapshot in self.sources.values():
            return snapshot.size()
        return 0

    def snapshotType(self) -> str:
        for snapshot in self.sources.values():
            return snapshot.snapshotType()
        return "error"

    def version(self) -> str:
        for snapshot in self.sources.values():
            return snapshot.snapshotType()
        return "?"

    def details(self):
        for snapshot in self.sources.values():
            return snapshot.details()
        return "?"

    def protected(self) -> bool:
        for snapshot in self.sources.values():
            return snapshot.protected()
        return False

    def date(self) -> datetime:
        for snapshot in self.sources.values():
            return snapshot.date()
        return datetime.now()

    def sizeString(self) -> str:
        size_string = self.size()
        if type(size_string) == str:
            return size_string
        size_bytes = float(size_string)
        if size_bytes <= 1024.0:
            return str(int(size_bytes)) + " B"
        if size_bytes <= 1024.0 * 1024.0:
            return str(int(size_bytes / 1024.0)) + " kB"
        if size_bytes <= 1024.0 * 1024.0 * 1024.0:
            return str(int(size_bytes / (1024.0 * 1024.0))) + " MB"
        return str(int(size_bytes / (1024.0 * 1024.0 * 1024.0))) + " GB"

    def status(self) -> str:
        if self._status_override is not None:
            return self._status_override.format(*self._status_override_args)

        for snapshot in self.sources.values():
            status = snapshot.status()
            if status:
                return status

        inDrive = self.getSource(SOURCE_GOOGLE_DRIVE) is not None
        inHa = self.getSource(SOURCE_HA) is not None

        if inDrive and inHa:
            return "Backed Up"
        if inDrive:
            return "Drive Only"
        if inHa:
            return "Hass.io Only"
        return "Deleted"

    def isDeleted(self) -> bool:
        return len(self.sources) == 0

    def overrideStatus(self, format, *args) -> None:
        self._status_override = format
        self._status_override_args = args

    def clearStatus(self):
        self._status_override = None
        self._status_override_args = None

    def __str__(self) -> str:
        return "<Slug: {0} {1} {2}>".format(self.slug(), " ".join(self.sources), self.date().isoformat())

    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def __repr__(self) -> str:
        return self.__str__()


class DummySnapshotSource(AbstractSnapshot):
    def __init__(self, name, date, source, slug):
        super().__init__(
            name=name,
            slug=slug,
            date=date,
            size=0,
            source=source,
            snapshotType="dummy",
            version="dummy_version",
            protected=True,
            retained=False,
            uploadable=True,
            details={})


class DummySnapshot(Snapshot):
    def __init__(self, name, date, source, slug, size=0):
        super().__init__(None)
        self._size = size
        self.addSource(DummySnapshotSource(name, date, source, slug))

    def size(self):
        return self._size
