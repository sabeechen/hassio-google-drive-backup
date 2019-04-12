
from datetime import datetime
from .helpers import parseDateTime
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any

PROP_KEY_SLUG = "snapshot_slug"
PROP_KEY_DATE = "snapshot_date"
PROP_KEY_NAME = "snapshot_name"
PROP_TYPE = "type"
PROP_VERSION = "version"
PROP_PROTECTED = "protected"


class AbstractSnapshot(ABC):
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def slug(self) -> str:
        pass

    @abstractmethod
    def size(self) -> int:
        pass

    @abstractmethod
    def date(self) -> datetime:
        pass


class DriveSnapshot(AbstractSnapshot):
    """
    Represents a Hass.io snapshot stored on Google Drive
    """
    def __init__(self, source: Dict[Any, Any]):
        self.source = source.copy()

    def id(self) -> str:
        return str(self.source.get('id'))

    def name(self) -> str:
        return self.source.get('appProperties')[PROP_KEY_NAME]  # type: ignore

    def slug(self) -> str:
        return self.source.get('appProperties')[PROP_KEY_SLUG]  # type: ignore

    def size(self) -> int:
        return self.source.get('size')  # type: ignore

    def date(self) -> datetime:
        return parseDateTime(self.source.get('appProperties')[PROP_KEY_DATE])  # type: ignore

    def snapshotType(self) -> str:
        props = self.source.get('appProperties')
        if PROP_TYPE in props:
            return props[PROP_TYPE]
        return "full"

    def version(self) -> str:
        props = self.source.get('appProperties')
        if PROP_VERSION in props:
            return props[PROP_VERSION]
        return "?"

    def protected(self) -> bool:
        props = self.source.get('appProperties')
        if PROP_PROTECTED in props:
            return props[PROP_VERSION] == "true" or props[PROP_VERSION] == "True"
        return False

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
    def __init__(self, source: Dict[str, Any]):
        self.source: Dict[str, Any] = source.copy()

    def name(self) -> str:
        return str(self.source['name'])

    def slug(self) -> str:
        return str(self.source['slug'])

    def size(self) -> int:
        return int(self.source['size']) * 1024 * 1024

    def date(self) -> datetime:
        return parseDateTime(self.source['date'])

    def snapshotType(self) -> str:
        return str(self.source['type'])

    def version(self) -> str:
        return str(self.source['version'])

    def protected(self) -> bool:
        return bool(self.source['protected'])

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
    def __init__(self, snapshot: Optional[AbstractSnapshot]):
        self.driveitem: Optional[DriveSnapshot] = None
        self.pending: bool = False
        self.ha: Optional[HASnapshot] = None
        if isinstance(snapshot, HASnapshot):
            self.ha = snapshot
            self.driveitem = None
            self.pending = False
        elif isinstance(snapshot, DriveSnapshot):
            self.driveitem = snapshot
            self.ha = None
            self.pending = False
        else:
            self.pending = True
        self.pending_name: Optional[str] = ""
        self.pending_date: Optional[datetime] = None
        self.pending_slug: Optional[str] = None
        self.uploading_pct: int = -1
        self.pendingHasFailed: bool = False
        self.will_backup: bool = True

    def setPending(self, name: str, date: datetime) -> None:
        self.pending_name = name
        self.pending_date = date
        self.pending_slug = "PENDING"
        self.pending = True

    def endPending(self, slug: str) -> None:
        self.pending_slug = slug

    def pendingFailed(self) -> None:
        self.pendingHasFailed = True

    def setWillBackup(self, will: bool) -> None:
        self.will_backup = will

    def name(self) -> str:
        if self.driveitem:
            return self.driveitem.name()
        elif self.ha:
            return self.ha.name()
        elif self.pending and self.pending_name:
            return self.pending_name
        else:
            return "error"

    def slug(self) -> str:
        if self.driveitem:
            return self.driveitem.slug()
        elif self.ha:
            return self.ha.slug()
        elif self.pending and self.pending_slug:
            return self.pending_slug
        else:
            return "error"

    def size(self) -> int:
        if self.driveitem:
            return self.driveitem.size()
        elif self.ha:
            return self.ha.size()
        else:
            return 0

    def snapshotType(self) -> str:
        if self.ha:
            return self.ha.snapshotType()
        elif self.driveitem:
            return self.driveItem.snapshotType()
        else:
            return "pending"

    def version(self) -> str:
        if self.ha:
            return self.ha.snapshotType()
        elif self.driveitem:
            return self.driveitem.snapshotType()
        else:
            return "?"

    def protected(self) -> bool:
        if self.ha:
            return self.ha.protected()
        elif self.driveitem:
            return self.driveitem.protected()
        else:
            return False

    def date(self) -> datetime:
        if self.driveitem:
            return self.driveitem.date()
        elif self.ha:
            return self.ha.date()
        elif self.pending and self.pending_date:
            return self.pending_date
        else:
            return datetime.now()

    def sizeString(self) -> str:
        size_bytes = float(self.size())
        if size_bytes <= 1024.0:
            return str(int(size_bytes)) + " B"
        if size_bytes <= 1024.0 * 1024.0:
            return str(int(size_bytes / 1024.0)) + " kB"
        if size_bytes <= 1024.0 * 1024.0 * 1024.0:
            return str(int(size_bytes / (1024.0 * 1024.0))) + " MB"
        return str(int(size_bytes / (1024.0 * 1024.0 * 1024.0))) + " GB"

    def status(self) -> str:
        if self.isInDrive() and self.isInHA():
            return "Backed Up"
        if self.isInDrive() and not self.isInHA():
            return "Drive Only"
        if not self.isInDrive() and self.isInHA() and self.uploading_pct >= 0:
            return "Uploading {}%".format(self.uploading_pct)
        if not self.isInDrive() and self.isInHA():
            if self.will_backup:
                return "Waiting"
            else:
                return "Hass.io Only"
        if self.pending:
            return "Pending"
        return "Invalid State"

    def setDrive(self, drive: DriveSnapshot) -> None:
        self.driveitem = drive
        self.pending_name = None
        self.pending_date = None
        self.pending_slug = None
        self.uploading_pct = -1
        self.pending = False

    def setHA(self, ha: HASnapshot) -> None:
        self.ha = ha
        self.pending_name = None
        self.pending_date = None
        self.pending_slug = None
        self.uploading_pct = -1
        self.pending = False

    def isInDrive(self) -> bool:
        return self.driveitem is not None

    def isInHA(self) -> bool:
        return self.ha is not None

    def isPending(self) -> bool:
        return self.pending and not self.isInHA() and not self.pendingHasFailed

    def isDeleted(self) -> bool:
        return not self.isPending() and not self.isInHA() and not self.isInDrive()

    def update(self, snapshot: AbstractSnapshot) -> None:
        if isinstance(snapshot, HASnapshot):
            self.ha = snapshot
        else:
            self.drive = snapshot

    def details(self):
        if self.isInHA():
            return self.ha.source
        elif self.isInDrive():
            return self.drive.details()
        else:
            return {}

    def uploading(self, percent: int) -> None:
        self.uploading_pct = percent

    def __str__(self) -> str:
        return "<Slug: {0} Ha: {1} Drive: {2} Pending: {3} {4}>".format(self.slug(), self.ha, self.driveitem, self.pending, self.date().isoformat())

    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def __repr__(self) -> str:
        return self.__str__()
