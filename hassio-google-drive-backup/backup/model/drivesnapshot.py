from .snapshots import AbstractSnapshot
from typing import Any, Dict

from ..const import SOURCE_GOOGLE_DRIVE
from ..exceptions import ensureKey
from ..config import BoolValidator
from ..time import Time
from ..logger import getLogger

logger = getLogger(__name__)

PROP_KEY_SLUG = "snapshot_slug"
PROP_KEY_DATE = "snapshot_date"
PROP_KEY_NAME = "snapshot_name"
PROP_TYPE = "type"
PROP_VERSION = "version"
PROP_PROTECTED = "protected"
PROP_RETAINED = "retained"
DRIVE_KEY_TEXT = "Google Drive's snapshot metadata"


class DriveSnapshot(AbstractSnapshot):

    """
    Represents a Home Assistant snapshot stored on Google Drive
    """

    def __init__(self, data: Dict[Any, Any]):
        props = ensureKey('appProperties', data, DRIVE_KEY_TEXT)
        retained = BoolValidator.strToBool(props.get(PROP_RETAINED, "False"))
        super().__init__(
            name=ensureKey(PROP_KEY_NAME, props, DRIVE_KEY_TEXT),
            slug=ensureKey(PROP_KEY_SLUG, props, DRIVE_KEY_TEXT),
            date=Time.parse(
                ensureKey(PROP_KEY_DATE, props, DRIVE_KEY_TEXT)),
            size=int(ensureKey("size", data, DRIVE_KEY_TEXT)),
            source=SOURCE_GOOGLE_DRIVE,
            snapshotType=props.get(PROP_TYPE, "?"),
            version=props.get(PROP_VERSION, "?"),
            protected=BoolValidator.strToBool(props.get(PROP_PROTECTED, "?")),
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
