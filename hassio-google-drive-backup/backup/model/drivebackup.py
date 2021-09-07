from .backups import AbstractBackup
from typing import Any, Dict

from ..const import SOURCE_GOOGLE_DRIVE, NECESSARY_PROP_KEY_SLUG, NECESSARY_PROP_KEY_DATE, NECESSARY_PROP_KEY_NAME
from ..exceptions import ensureKey
from ..config import BoolValidator
from ..time import Time
from ..logger import getLogger

logger = getLogger(__name__)

PROP_TYPE = "type"
PROP_VERSION = "version"
PROP_PROTECTED = "protected"
PROP_RETAINED = "retained"
DRIVE_KEY_TEXT = "Google Drive's backup metadata"


class DriveBackup(AbstractBackup):

    """
    Represents a Home Assistant backup stored on Google Drive
    """

    def __init__(self, data: Dict[Any, Any]):
        props = ensureKey('appProperties', data, DRIVE_KEY_TEXT)
        retained = BoolValidator.strToBool(props.get(PROP_RETAINED, "False"))
        if NECESSARY_PROP_KEY_NAME in props:
            backup_name = ensureKey(NECESSARY_PROP_KEY_NAME, props, DRIVE_KEY_TEXT)
        else:
            backup_name = data['name'].replace(".tar", "")
        super().__init__(
            name=backup_name,
            slug=ensureKey(NECESSARY_PROP_KEY_SLUG, props, DRIVE_KEY_TEXT),
            date=Time.parse(
                ensureKey(NECESSARY_PROP_KEY_DATE, props, DRIVE_KEY_TEXT)),
            size=int(ensureKey("size", data, DRIVE_KEY_TEXT)),
            source=SOURCE_GOOGLE_DRIVE,
            backupType=props.get(PROP_TYPE, "?"),
            version=props.get(PROP_VERSION, None),
            protected=BoolValidator.strToBool(props.get(PROP_PROTECTED, "?")),
            retained=retained,
            uploadable=False,
            details=None)
        self._drive_data = data
        self._id = ensureKey('id', data, DRIVE_KEY_TEXT)

    def id(self) -> str:
        return self._id

    def canDeleteDirectly(self) -> str:
        caps = self._drive_data.get("capabilities", {})
        if caps.get('canDelete', False):
            return True

        # check if the item is in a shared drive
        sharedId = self._drive_data.get("driveId")
        if sharedId and len(sharedId) > 0 and caps.get("canTrash", False):
            # Its in a shared drive and trashable, so trash won't exhaust quota
            return False

        # We aren't certain we can trash or delete, so just make a try at deleting.
        return True

    def __str__(self) -> str:
        return "<Drive: {0} Name: {1} Id: {2}>".format(self.slug(), self.name(), self.id())

    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def __repr__(self) -> str:
        return self.__str__()
