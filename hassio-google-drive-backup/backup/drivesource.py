import os.path
import os

from datetime import datetime
from requests.exceptions import HTTPError
from oauth2client.client import Credentials
from .model import SnapshotSource, CreateOptions
from datetime import timedelta
from .snapshots import DriveSnapshot, AbstractSnapshot
from io import IOBase
from .snapshots import Snapshot
from .snapshots import PROP_KEY_DATE
from .snapshots import PROP_KEY_SLUG
from .snapshots import PROP_KEY_NAME
from .snapshots import PROP_TYPE
from .snapshots import PROP_VERSION
from .snapshots import PROP_PROTECTED
from .snapshots import PROP_RETAINED
from typing import Dict, Any
from .config import Config
from .logbase import LogBase
from .thumbnail import THUMBNAIL_IMAGE
from .helpers import parseDateTime
from .driverequests import DriveRequests
from .time import Time
from .exceptions import LogicError
from .globalinfo import GlobalInfo
from .const import SOURCE_GOOGLE_DRIVE
from .settings import Setting

MIME_TYPE = "application/tar"
THUMBNAIL_MIME_TYPE = "image/png"
FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'
FOLDER_NAME = 'Hass.io Snapshots'
FOLDER_CACHE_SECONDS = 60 * 5


class DriveSource(SnapshotSource[DriveSnapshot], LogBase):
    # SOMEDAY: read snapshots all in one big batch request, then sort the folder and child addons from that.  Would need to add test verifying the "current" backup directory is used instead of the "latest"
    def __init__(self, config: Config, time: Time, drive_requests, info: GlobalInfo):
        super().__init__()
        self.config = config
        self.drivebackend: DriveRequests = drive_requests
        self.time = time
        self._folderId = None
        self._folder_queryied_last = None
        self._info = info

    def saveCreds(self, creds: Credentials) -> None:
        self.info("Saving new Google Drive credentials")
        self.drivebackend.saveCredentials(creds)
        self.trigger()

    def name(self) -> str:
        return SOURCE_GOOGLE_DRIVE

    def maxCount(self) -> None:
        return self.config.get(Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE)

    def upload(self) -> bool:
        return self.config.get(Setting.ENABLE_DRIVE_UPLOAD)

    def enabled(self) -> bool:
        return self.drivebackend.enabled()

    def create(self, options: CreateOptions) -> DriveSnapshot:
        raise LogicError("Snapshots can't be created in Drive")

    def getFolderId(self) -> str:
        return self._getParentFolderId()

    def get(self) -> Dict[str, DriveSnapshot]:
        self._info.drive_folder_id = self.getFolderId()
        snapshots: Dict[str, DriveSnapshot] = {}
        for child in self.drivebackend.query("'{}' in parents".format(self._getParentFolderId())):
            properties = child.get('appProperties')
            if properties and PROP_KEY_DATE in properties and PROP_KEY_SLUG in properties and PROP_KEY_NAME in properties and not child.get('trashed'):
                snapshot = DriveSnapshot(child)
                snapshots[snapshot.slug()] = snapshot
        return snapshots

    def delete(self, snapshot: Snapshot):
        item = self._validateSnapshot(snapshot)
        self.info("Deleting '{}' From Google Drive".format(item.name()))
        self.drivebackend.delete(item.id())
        snapshot.removeSource(self.name())

    def save(self, snapshot: AbstractSnapshot, bytes: IOBase) -> DriveSnapshot:
        retain = snapshot.getOptions() and snapshot.getOptions().retain_sources.get(self.name(), False)
        file_metadata = {
            'name': str(snapshot.name()) + ".tar",
            'parents': [self._getParentFolderId()],
            'description': 'A Hass.io snapshot file uploaded by Hass.io Google Drive Backup',
            'appProperties': {
                PROP_KEY_SLUG: snapshot.slug(),
                PROP_KEY_DATE: str(snapshot.date()),
                PROP_KEY_NAME: str(snapshot.name()),
                PROP_TYPE: str(snapshot.snapshotType()),
                PROP_VERSION: str(snapshot.version()),
                PROP_PROTECTED: str(snapshot.protected()),
                PROP_RETAINED: str(retain)
            },
            'contentHints': {
                'indexableText': 'Hass.io hassio snapshot backup home assistant',
                'thumbnail': {
                    'image': THUMBNAIL_IMAGE,
                    'mimeType': THUMBNAIL_MIME_TYPE
                }
            },
            'createdTime': self._timeToRfc3339String(snapshot.date()),
            'modifiedTime': self._timeToRfc3339String(snapshot.date())
        }

        try:
            self._info.upload(bytes.size())
            snapshot.overrideStatus("Uploading {0}%", bytes)
            for progress in self.drivebackend.create(bytes, file_metadata, MIME_TYPE):
                if isinstance(progress, float):
                    self.debug("Uploading {1} {0:.2f}%".format(progress * 100, snapshot.name()))
                else:
                    return DriveSnapshot(progress)
            raise LogicError("Google Drive snapshot upload didn't return a completed item before exiting")
        finally:
            snapshot.clearStatus()

    def read(self, snapshot: Snapshot) -> IOBase:
        item = self._validateSnapshot(snapshot)
        return self.drivebackend.download(item.id())

    def retain(self, snapshot: Snapshot, retain: bool) -> None:
        item = self._validateSnapshot(snapshot)
        if item.retained() == retain:
            return
        file_metadata: Dict[str, str] = {
            'appProperties': {
                PROP_RETAINED: str(retain),
            },
        }
        self.drivebackend.update(item.id(), file_metadata)
        item.setRetained(retain)

    def changeBackupFolder(self, id):
        if self._verifyBackupFolderWithQuery(id):
            self._saveFolder(id)
            self._folderId = id
            self._folder_queryied_last = self.time.now()
        else:
            # TODO
            pass  

    def _verifyBackupFolderWithQuery(self, id):
        # Query drive for the folder to make sure it still exists and we have the right permission on it.
        try:
            folder = self._get(id)
            if not self._isValidFolder(folder):
                self.info("Provided snapshot folder {0} is invalid".format(id))
                return False
            return True
        except HTTPError as e:
            # 404 means the folder oean't exist (maybe it got moved?)
            if e.response.status_code == 404:
                self.info("Provided snapshot folder {0} is gone".format(id))
                return False
            else:
                raise e

    def _getParentFolderId(self):
        if not self._folder_queryied_last or self._folder_queryied_last + timedelta(seconds=FOLDER_CACHE_SECONDS) < self.time.now():
            self._folderId = self._validateFolderId()
        return self._folderId

    def _validateSnapshot(self, snapshot: Snapshot) -> DriveSnapshot:
        drive_item: DriveSnapshot = snapshot.getSource(self.name())
        if not drive_item:
            raise LogicError("Requested to do something with a snapshot from Google Drive, but the snapshot has no Google Drive source")
        return drive_item

    def _timeToRfc3339String(self, time: datetime) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _validateFolderId(self) -> str:
        # First, check if we cached the drive folder
        if os.path.exists(self.config.get(Setting.FOLDER_FILE_PATH)):
            with open(self.config.get(Setting.FOLDER_FILE_PATH), "r") as folder_file:
                folder_id: str = folder_file.readline()
                if not self._verifyBackupFolderWithQuery(folder_id):
                    return self._findDriveFolder()
        return self._findDriveFolder()

    def _get(self, id):
        return self.drivebackend.get(id)

    def _findDriveFolder(self) -> str:
        folders = []

        for child in self.drivebackend.query("mimeType='" + FOLDER_MIME_TYPE + "'"):
            if self._isValidFolder(child):
                folders.append(child)

        folders.sort(key=lambda c: parseDateTime(c.get("modifiedTime")))
        if len(folders) > 0:
            self.info("Found " + folders[len(folders) - 1].get('name'))
            return self._saveFolder(folders[len(folders) - 1])
        return self._createDriveFolder()

    def _isValidFolder(self, folder) -> bool:
        try:
            caps = folder.get('capabilities')
            if folder.get('trashed'):
                return False
            elif not caps['canAddChildren']:
                return False
            elif not caps['canListChildren']:
                return False
            elif not caps.get('canDeleteChildren', False) and not caps.get('canRemoveChildren', False):
                return False
            elif folder.get("mimeType") != FOLDER_MIME_TYPE:
                return False
        except Exception:
            return False
        return True

    def _createDriveFolder(self) -> str:
        self.info('Creating folder "{}" in "My Drive"'.format(FOLDER_NAME))
        file_metadata: Dict[str, str] = {
            'name': FOLDER_NAME,
            'mimeType': FOLDER_MIME_TYPE,
            'appProperties': {
                "backup_folder": "true",
            },
        }
        folder = self.drivebackend.createFolder(file_metadata)
        return self._saveFolder(folder)

    def _saveFolder(self, folder: Any) -> str:
        self.info("Saving snapshot folder: " + folder.get('id'))
        with open(self.config.get(Setting.FOLDER_FILE_PATH), "w") as folder_file:
            folder_file.write(folder.get('id'))
        return folder.get('id')
