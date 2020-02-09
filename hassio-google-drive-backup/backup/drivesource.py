import os
import os.path
from datetime import datetime, timedelta
from io import IOBase
from typing import Any, Dict

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientResponseError
from injector import inject, singleton
from oauth2client.client import Credentials

from .asynchttpgetter import AsyncHttpGetter
from .config import Config
from .const import SOURCE_GOOGLE_DRIVE
from .driverequests import DriveRequests
from .exceptions import (BackupFolderInaccessible, BackupFolderMissingError,
                         ExistingBackupFolderError,
                         GoogleDrivePermissionDenied, LogicError)
from .globalinfo import GlobalInfo
from .helpers import parseDateTime
from .logbase import LogBase
from .model import CreateOptions, SnapshotDestination
from .settings import Setting
from .snapshots import (PROP_KEY_DATE, PROP_KEY_NAME, PROP_KEY_SLUG,
                        PROP_PROTECTED, PROP_RETAINED, PROP_TYPE, PROP_VERSION,
                        AbstractSnapshot, DriveSnapshot, Snapshot)
from .thumbnail import THUMBNAIL_IMAGE
from .time import Time

MIME_TYPE = "application/tar"
THUMBNAIL_MIME_TYPE = "image/png"
FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'
FOLDER_NAME = 'Hass.io Snapshots'
FOLDER_CACHE_SECONDS = 30


@singleton
class DriveSource(SnapshotDestination, LogBase):
    # SOMEDAY: read snapshots all in one big batch request, then sort the folder and child addons from that.  Would need to add test verifying the "current" backup directory is used instead of the "latest"
    @inject
    def __init__(self, config: Config, time: Time, drive_requests: DriveRequests, info: GlobalInfo, session: ClientSession):
        super().__init__()
        self.session = session
        self.config = config
        self.drivebackend: DriveRequests = drive_requests
        self.time = time
        self._folderId = None
        self._folder_queryied_last = None
        self._info = info

        # These get set when an existing folder is found and should cause the UI to
        # prompt for what to do about it.
        self._existing_folder_id = None
        self._existing_folder_name = None
        self._existing_folders = {}

    def saveCreds(self, creds: Credentials) -> None:
        self.info("Saving new Google Drive credentials")
        self.drivebackend.saveCredentials(creds)
        self.trigger()

    def isCustomCreds(self):
        return self.drivebackend.isCustomCreds()

    def name(self) -> str:
        return SOURCE_GOOGLE_DRIVE

    def maxCount(self) -> None:
        return self.config.get(Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE)

    def upload(self) -> bool:
        return self.config.get(Setting.ENABLE_DRIVE_UPLOAD)

    def enabled(self) -> bool:
        return self.drivebackend.enabled()

    async def create(self, options: CreateOptions) -> DriveSnapshot:
        raise LogicError("Snapshots can't be created in Drive")

    async def getFolderId(self) -> str:
        return await self._getParentFolderId()

    def checkBeforeChanges(self):
        if self._existing_folder_id:
            raise ExistingBackupFolderError(
                self._existing_folder_id, self._existing_folder_name)

    async def get(self) -> Dict[str, DriveSnapshot]:
        parent = await self.getFolderId()
        self._info.drive_folder_id = parent
        snapshots: Dict[str, DriveSnapshot] = {}
        try:
            async for child in self.drivebackend.query("'{}' in parents".format(parent)):
                properties = child.get('appProperties')
                if properties and PROP_KEY_DATE in properties and PROP_KEY_SLUG in properties and PROP_KEY_NAME in properties:
                    snapshot = DriveSnapshot(child)
                    snapshots[snapshot.slug()] = snapshot
        except ClientResponseError as e:
            if e.status == 404:
                # IIUC, 404 on create can only mean that the parent id isn't valid anymore.
                raise BackupFolderInaccessible(parent)
            raise e
        except GoogleDrivePermissionDenied:
            # This should always mean we lost permission on the backup folder, but at least it still exists.
            raise BackupFolderInaccessible(parent)
        return snapshots

    async def delete(self, snapshot: Snapshot):
        item = self._validateSnapshot(snapshot)
        self.info("Deleting '{}' From Google Drive".format(item.name()))
        await self.drivebackend.delete(item.id())
        snapshot.removeSource(self.name())

    async def save(self, snapshot: AbstractSnapshot, source: AsyncHttpGetter) -> DriveSnapshot:
        retain = snapshot.getOptions() and snapshot.getOptions(
        ).retain_sources.get(self.name(), False)
        file_metadata = {
            'name': str(snapshot.name()) + ".tar",
            'parents': [await self._getParentFolderId()],
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

        async with source:
            try:
                self.info("Uploading '{}' to Google Drive".format(
                    snapshot.name()))
                size = source.size()
                self._info.upload(size)
                snapshot.overrideStatus("Uploading {0}%", source)
                async for progress in self.drivebackend.create(source, file_metadata, MIME_TYPE):
                    if isinstance(progress, float):
                        self.debug("Uploading {1} {0:.2f}%".format(
                            progress * 100, snapshot.name()))
                    else:
                        return DriveSnapshot(progress)
                raise LogicError(
                    "Google Drive snapshot upload didn't return a completed item before exiting")
            except ClientResponseError as e:
                if e.status == 404:
                    # IIUC, 404 on create can only mean that the parent id isn't valid anymore.
                    raise BackupFolderInaccessible(await self._getParentFolderId())
                raise e
            except GoogleDrivePermissionDenied:
                # This shoudl always mean we lost permission on the backup folder, but at least it still exists.
                raise BackupFolderInaccessible(await self._getParentFolderId())
            finally:
                snapshot.clearStatus()

    async def read(self, snapshot: Snapshot) -> IOBase:
        item = self._validateSnapshot(snapshot)
        return await self.drivebackend.download(item.id(), item.size())

    async def retain(self, snapshot: Snapshot, retain: bool) -> None:
        item = self._validateSnapshot(snapshot)
        if item.retained() == retain:
            return
        file_metadata: Dict[str, str] = {
            'appProperties': {
                PROP_RETAINED: str(retain),
            },
        }
        await self.drivebackend.update(item.id(), file_metadata)
        item.setRetained(retain)

    def changeBackupFolder(self, id):
        self._saveFolderId(id)
        self._folderId = id
        self._folder_queryied_last = None
        self._existing_folder_id = None
        self._existing_folder_name = None

    async def _verifyBackupFolderWithQuery(self, id):
        if self.isCustomCreds():
            # If the user is using custom creds and specifying the snapshot folder, then chances are the
            # app doesn't have permission to access the parent folder directly.  Ironically, we can still
            # query for children and add/remove snapshots.  Not a huge deal, just
            # means we can't verify the folder still exists, isn't trashed, etc.  Just let it be valid
            # and handle potential errors elsewhere.
            return True
        # Query drive for the folder to make sure it still exists and we have the right permission on it.
        try:
            folder = await self._get(id)
            if not self._isValidFolder(folder):
                self.info("Provided snapshot folder {0} is invalid".format(id))
                return False
            return True
        except ClientResponseError as e:
            # 404 means the folder doesn't exist (maybe it got moved?)
            if e.status == 404:
                self.info("Provided snapshot folder {0} is gone".format(id))
                return False
            else:
                raise e

    async def _getParentFolderId(self):
        if not self._folder_queryied_last or self._folder_queryied_last + timedelta(seconds=FOLDER_CACHE_SECONDS) < self.time.now():
            self._folderId = await self._validateFolderId()
            self._folder_queryied_last = self.time.now()
        return self._folderId

    def _validateSnapshot(self, snapshot: Snapshot) -> DriveSnapshot:
        drive_item: DriveSnapshot = snapshot.getSource(self.name())
        if not drive_item:
            raise LogicError(
                "Requested to do something with a snapshot from Google Drive, but the snapshot has no Google Drive source")
        return drive_item

    def _timeToRfc3339String(self, time: datetime) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ")

    async def _validateFolderId(self) -> str:
        # First, check if we cached the drive folder
        if os.path.exists(self.config.get(Setting.FOLDER_FILE_PATH)):
            with open(self.config.get(Setting.FOLDER_FILE_PATH), "r") as folder_file:
                folder_id: str = folder_file.readline()
            if await self._verifyBackupFolderWithQuery(folder_id):
                return folder_id
            elif self.config.get(Setting.SPECIFY_SNAPSHOT_FOLDER):
                # Raise a special exception about losing access.
                raise BackupFolderInaccessible(folder_id)

        if self.config.get(Setting.SPECIFY_SNAPSHOT_FOLDER):
            raise BackupFolderMissingError()
        return await self._findDriveFolder()

    async def _get(self, id):
        return await self.drivebackend.get(id)

    async def _findDriveFolder(self) -> str:
        folders = []

        async for child in self.drivebackend.query("mimeType='" + FOLDER_MIME_TYPE + "'"):
            if self._isValidFolder(child):
                folders.append(child)

        folders.sort(key=lambda c: parseDateTime(c.get("modifiedTime")))
        if len(folders) > 0:
            # Found a folder, which means we're probably using the add-on from a
            # previous (or duplicate) installation.  Record and return the id but don't
            # persist it until the user chooses to do so.
            folder = folders[len(folders) - 1]
            self.info("Found " + folder.get('name'))

            if self._info.getUseExistingFolder() is not None:
                if self._info.getUseExistingFolder():
                    # Just use the folder
                    return self._saveFolderId(folder.get('id'))
                else:
                    # Create a new folder
                    new_id = await self._createDriveFolder()
                    self._info.resolveFolder(None)
                    return new_id
            self._folderId = folder.get("id")
            self._existing_folder_name = folder.get("name")
            self._existing_folder_id = folder.get("id")
            return self._folderId

        # Create a new folder since one doesn't already exist.
        return await self._createDriveFolder()

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

    async def _createDriveFolder(self) -> str:
        self.info('Creating folder "{}" in "My Drive"'.format(FOLDER_NAME))
        file_metadata: Dict[str, str] = {
            'name': FOLDER_NAME,
            'mimeType': FOLDER_MIME_TYPE,
            'appProperties': {
                "backup_folder": "true",
            },
        }
        folder = await self.drivebackend.createFolder(file_metadata)
        return self._saveFolder(folder)

    def _saveFolder(self, folder: Any) -> str:
        return self._saveFolderId(folder.get('id'))

    def _saveFolderId(self, folder_id: str) -> str:
        self.info("Saving snapshot folder: " + folder_id)
        with open(self.config.get(Setting.FOLDER_FILE_PATH), "w") as folder_file:
            folder_file.write(folder_id)
        self._existing_folder_name = None
        self._existing_folder_id = None
        return folder_id

    def resetFolder(self):
        if (os.path.exists(self.config.get(Setting.FOLDER_FILE_PATH))):
            os.remove(self.config.get(Setting.FOLDER_FILE_PATH))
        self._folderId = None
        self._folder_queryied_last = None
        self._existing_folder_name = None
        self._existing_folder_id = None
        self._folder_queryied_last = None
