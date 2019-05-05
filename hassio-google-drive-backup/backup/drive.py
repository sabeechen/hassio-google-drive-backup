import os.path
import os

from datetime import datetime
from apiclient.errors import HttpError
from oauth2client.client import Credentials
from .snapshots import DriveSnapshot
from .snapshots import Snapshot
from .snapshots import PROP_KEY_DATE
from .snapshots import PROP_KEY_SLUG
from .snapshots import PROP_KEY_NAME
from .snapshots import PROP_TYPE
from .snapshots import PROP_VERSION
from .snapshots import PROP_PROTECTED
from .snapshots import PROP_RETAINED
from typing import List, Dict, Any
from .config import Config
from .logbase import LogBase
from .thumbnail import THUMBNAIL_IMAGE
from .helpers import parseDateTime
from .helpers import formatException
from .seekablerequest import SeekableRequest
from .drivepython import DrivePython
from .driverequests import DriveRequests
from .time import Time

# Defines the retry strategy for calls made to Drive
# max # of time to retry and call to Drive
DRIVE_MAX_RETRIES: int = 5
# The initial backoff for drive retries.
DRIVE_RETRY_INITIAL_SECONDS: int = 2
# How uch longer to wait for each Drive service call (Exponential backoff)
DRIVE_EXPONENTIAL_BACKOFF: int = 2

MIME_TYPE = "application/tar"
FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'
FOLDER_NAME = 'Hass.io Snapshots'
DRIVE_VERSION = "v3"
DRIVE_SERVICE = "drive"

SELECT_FIELDS = "id,name,appProperties,size,trashed,mimeType,modifiedTime,capabilities"
THUMBNAIL_MIME_TYPE = "image/png"
QUERY_FIELDS = "nextPageToken,files(" + SELECT_FIELDS + ")"
CREATE_FIELDS = SELECT_FIELDS


class Drive(LogBase):
    """
    Stores the logic for making calls to Google Drive and managing credentials necessary to do so.
    """
    def __init__(self, config: Config):
        self.config = config
        if config.driveExperimental():
            self.drivebackend = DriveRequests(config, Time())
        else:
            self.drivebackend = DrivePython(config)

    def saveCreds(self, creds: Credentials) -> None:
        self.info("Saving new Google Drive credentials")
        self.drivebackend.saveCredentials(creds)

    def enabled(self) -> bool:
        return self.drivebackend.enabled()

    def saveSnapshot(self, snapshot: Snapshot, download_url: str, parent_id: str) -> Snapshot:
        file_metadata = {
            'name': str(snapshot.name()) + ".tar",
            'parents': [parent_id],
            'description': 'A Hass.io snapshot file uploaded by Hass.io Google Drive Backup',
            'appProperties': {
                PROP_KEY_SLUG: snapshot.slug(),
                PROP_KEY_DATE: str(snapshot.date()),
                PROP_KEY_NAME: str(snapshot.name()),
                PROP_TYPE: str(snapshot.snapshotType()),
                PROP_VERSION: str(snapshot.version()),
                PROP_PROTECTED: str(snapshot.protected()),
                PROP_RETAINED: str(snapshot._pending_retain_drive)
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
        stream: SeekableRequest = SeekableRequest(download_url, headers=self.config.getHassioHeaders())
        snapshot.uploading(0)
        response = None
        for progress in self.drivebackend.create(stream, file_metadata, MIME_TYPE):
            if isinstance(progress, float):
                new_percent = int(progress * 100)
                snapshot.uploading(new_percent)
                self.debug("Uploading {1} {0}%".format(new_percent, snapshot.name()))
            else:
                response = progress
        snapshot.uploading(100)
        snapshot.setDrive(DriveSnapshot(response))

    def deleteSnapshot(self, snapshot: Snapshot) -> None:
        self.info("Deleting: {}".format(snapshot.name()))
        if not snapshot.driveitem:
            raise Exception("Drive item was null")
        self.drivebackend.delete(snapshot.driveitem.id())
        self.info("Deleted snapshot backup from drive '{}'".format(snapshot.name()))
        snapshot.driveitem = None

    def _timeToRfc3339String(self, time: datetime) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ")

    def readSnapshots(self, parent_id: str) -> List[DriveSnapshot]:
        snapshots: List[DriveSnapshot] = []
        for child in self.drivebackend.query("'{}' in parents".format(parent_id)):
            properties = child.get('appProperties')
            if properties and PROP_KEY_DATE in properties and PROP_KEY_SLUG in properties and PROP_KEY_NAME in properties and not child.get('trashed'):
                snapshots.append(DriveSnapshot(child))
        return snapshots

    def getFolderId(self) -> str:
        # First, check if we cached the drive folder
        if os.path.exists(self.config.folderFilePath()):
            with open(self.config.folderFilePath(), "r") as folder_file:
                folder_id: str = folder_file.readline()

                # Query drive for the folder to make sure it still exists and we have the right permission on it.
                try:
                    folder = self._get(folder_id)
                    if not self._isValidFolder(folder):
                        self.info("Existing snapshot folder was invalid, so we'll try to find an existing one")
                        return self._findDriveFolder()
                    return folder_id
                except HttpError as e:
                    # 404 means the folder oean't exist (maybe it got moved?)
                    if e.resp.status == 404:
                        self.info("The Drive Snapshot folder is gone")
                        return self._findDriveFolder()
                    else:
                        raise e
        else:
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
            elif not caps['canRemoveChildren']:
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
        with open(self.config.folderFilePath(), "w") as folder_file:
            folder_file.write(folder.get('id'))
        return folder.get('id')

    def download(self, id, size):
        return self.drivebackend.download(id, size)

    def setRetain(self, snapshot, retain):
        file_metadata: Dict[str, str] = {
            'appProperties': {
                PROP_RETAINED: str(retain),
            },
        }
        self.drivebackend.update(snapshot.driveitem.id(), file_metadata)
        snapshot.driveitem.setRetain(retain)

    def downloadToFile(self, id, path, snapshot: Snapshot) -> bool:
        try:
            snapshot.setDownloading(0)
            with open(path, "wb") as fh:
                written = 0
                stream = self.download(id, int(snapshot.size()))
                while True:
                    data = stream.read(5 * 1024 * 1024)
                    if len(data) == 0:
                        break
                    written += len(data)
                    fh.write(data)
                    progress = int(100 * float(written) / float(snapshot.size()))
                    self.debug("Uploading '{0}' {1}%".format(id, progress))
                    snapshot.setDownloading(progress)
            snapshot.setDownloading(100)
            return True
        except Exception as e:
            snapshot.downloadFailed()
            self.error(formatException(e))
            return False
