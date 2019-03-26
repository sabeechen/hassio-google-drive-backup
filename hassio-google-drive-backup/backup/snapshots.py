import datetime

from datetime import datetime
from .helpers import parseDateTime

PROP_KEY_SLUG = "snapshot_slug"
PROP_KEY_DATE = "snapshot_date"
PROP_KEY_NAME = "snapshot_name"

class DriveSnapshot(object):
    """
    Represents a Hass.io snapshot stored on Google Drive
    """
    def __init__(self, source):
        self.source = source.copy()

    def id(self):
        return self.source.get('id')

    def name(self):
        return self.source.get('appProperties')[PROP_KEY_NAME]

    def slug(self):
        return self.source.get('appProperties')[PROP_KEY_SLUG]

    def size(self):
        return self.source.get('size') 

    def date(self):
        return parseDateTime(self.source.get('appProperties')[PROP_KEY_DATE])

    def __str__(self):
        return "<Drive: {0} Name: {1} Id: {2}>".format(self.slug(), self.name(), self.id())

    def __format__(self, format_spec):
        return self.__str__()

    def __repr__(self):
        return self.__str__()



class HASnapshot(object):
    """
    Represents a Hass.io snapshot stored locally in Home Assistant
    """
    def __init__(self, source):
        self.source = source.copy()

    def name(self):
        return self.source['name']

    def slug(self):
        return self.source['slug']

    def size(self):
        return self.source['size'] * 1024 * 1024

    def date(self):
        return parseDateTime(self.source['date'])

    def __str__(self):
        return "<HA: {0} Name: {1}>".format(self.slug(), self.name())

    def __format__(self, format_spec):
        return self.__str__()

    def __repr__(self):
        return self.__str__()


class Snapshot(object):
    """
    Represents a Hass.io snapshot stored on Google Drive, locally in 
    Home Assistant, or a pending snapshot we expect to see show up later 
    """
    def __init__(self, snapshot):
        self.driveitem = None
        self.pending = False
        self.ha = None
        if isinstance(snapshot, HASnapshot):
            self.ha = snapshot
            self.driveitem = None
            self.pending = False
        elif isinstance(snapshot, DriveSnapshot):
            self.driveitem = snapshot
            self.ha = None
            self.pending = False
        else :
            self.pending = True
        self.pending_name = None
        self.pending_date = None
        self.pending_slug = None
        self.uploading_pct = -1
        self.pendingHasFailed = False
        self.will_backup = True

    def setPending(self, name, date):
        self.pending_name = name
        self.pending_date = date
        self.pending_slug = "PENDING"
        self.pending = True

    def endPending(self, slug):
        self.pending_slug = slug

    def pendingFailed(self):
        self.pendingHasFailed = True

    def setWillBackup(self, will):
        self.will_backup = will

    def name(self):
        if self.driveitem:
            return self.driveitem.name()
        elif self.ha:
            return self.ha.name()
        elif self.pending:
            return self.pending_name
        else:
            return "error"

    def slug(self):
        if self.driveitem:
            return self.driveitem.slug()
        elif self.ha:
            return self.ha.slug()
        elif self.pending:
            return self.pending_slug
        else:
            return "error"


    def size(self):
        if self.driveitem:
            return self.driveitem.size()
        elif self.ha:
            return self.ha.size()
        else:
            return 0

    def date(self):
        if self.driveitem:
            return self.driveitem.date()
        elif self.ha:
            return self.ha.date()
        elif self.pending:
            return self.pending_date
        else:
            return datetime.now()

    def sizeString(self):
        size_bytes = float(self.size())
        if size_bytes <= 1024.0:
            return str(int(size_bytes)) + " B"
        if size_bytes <= 1024.0*1024.0:
            return str(int(size_bytes/1024.0)) + " kB"
        if size_bytes <= 1024.0*1024.0*1024.0:
            return str(int(size_bytes/(1024.0*1024.0))) + " MB"
        return str(int(size_bytes/(1024.0*1024.0*1024.0))) + " GB"

    def status(self):
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

    def setDrive(self, drive):
        self.driveitem = drive
        self.pending_name = None
        self.pending_date = None
        self.pending_slug = None
        self.uploading_pct = -1
        self.pending = False

    def setHA(self, ha):
        self.ha = ha
        self.pending_name = None
        self.pending_date = None
        self.pending_slug = None
        self.uploading_pct = -1
        self.pending = False

    def isInDrive(self):
        return not self.driveitem is None


    def isInHA(self):
        return not self.ha is None


    def isPending(self):
        return self.pending and not self.isInHA() and not self.pendingHasFailed


    def isDeleted(self):
        return not self.isPending() and not self.isInHA() and not self.isInDrive()


    def update(self, snapshot):
        if isinstance(snapshot, HASnapshot):
            self.ha = snapshot
        else:
            self.drive = snapshot


    def uploading(self, percent):
        self.uploading_pct = percent

    def __str__(self):
        return "<Slug: {0} Ha: {1} Drive: {2} Pending: {3}>".format(self.slug(), self.ha, self.driveitem, self.pending)

    def __format__(self, format_spec):
        return self.__str__()

    def __repr__(self):
        return self.__str__()
