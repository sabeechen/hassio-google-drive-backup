import os
import os.path
from datetime import timedelta
from typing import Any, Dict

from aiohttp.client_exceptions import ClientResponseError
from injector import inject, singleton

from ..config import Config, Setting
from ..exceptions import (BackupFolderInaccessible, BackupFolderMissingError,
                          GoogleDrivePermissionDenied, LogInToGoogleDriveError)
from ..time import Time
from .driverequests import DriveRequests
from ..logger import getLogger

logger = getLogger(__name__)

FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'
FOLDER_NAME = 'Home Assistant Backups'
FOLDER_CACHE_SECONDS = 30


@singleton
class FolderFinder():
    @inject
    def __init__(self, config: Config, time: Time, drive_requests: DriveRequests):
        self.config = config
        self.drivebackend: DriveRequests = drive_requests
        self.time = time

        # The cached folder id
        self._folderId = None

        # When the fodler id was last cached
        self._folder_queryied_last = None

        # These get set when an existing folder is found and should cause the UI to
        # prompt for what to do about it.
        self._existing_folder = None
        self._use_existing = None
        self._folder_details = None

    def resolveExisting(self, val):
        if self._existing_folder:
            self._use_existing = val
        else:
            self._use_existing = None

    def _isSharedDrive(self, folder):
        driveId = folder.get("driveId", None)
        return driveId and len(driveId) > 0

    def currentIsSharedDrive(self):
        return self._folder_details and self._isSharedDrive(self._folder_details)

    async def get(self):
        if self._existing_folder and self._use_existing is not None:
            if self._use_existing:
                await self.save(self._existing_folder)
            else:
                await self.create()
            self._use_existing = None
        if not self._folder_queryied_last or self._folder_queryied_last + timedelta(seconds=FOLDER_CACHE_SECONDS) < self.time.now():
            try:
                self._folderId = await self._readFolderId()
            except (BackupFolderMissingError, BackupFolderInaccessible):
                if not self.config.get(Setting.SPECIFY_BACKUP_FOLDER):
                    # Search for a folder, they may have created one before
                    self._existing_folder = await self._search()
                    if self._existing_folder:
                        self._folderId = self._existing_folder.get('id')
                    else:
                        # Create folder, since no other folder is available
                        await self.create()
                else:
                    raise
            self._folder_queryied_last = self.time.now()
        return self._folderId

    def getExisting(self):
        return self._existing_folder

    async def save(self, folder: Any) -> str:
        if not isinstance(folder, str):
            self._folder_details = folder
            folder = folder.get('id')
        else:
            self._folder_details = None
        logger.info("Saving backup folder: " + folder)
        with open(self.config.get(Setting.FOLDER_FILE_PATH), 'w') as folder_file:
            folder_file.write(folder)
        self._folderId = folder
        self._folder_queryied_last = self.time.now()
        self._existing_folder = None

    def reset(self):
        if os.path.exists(self.config.get(Setting.FOLDER_FILE_PATH)):
            os.remove(self.config.get(Setting.FOLDER_FILE_PATH))
        self._folderId = None
        self._folder_queryied_last = None
        self._existing_folder = None

    def getCachedFolder(self):
        return self._folderId

    def deCache(self):
        self._folderId = None
        self._folder_queryied_last = None

    async def _readFolderId(self) -> str:
        # First, check if we cached the drive folder
        if not os.path.exists(self.config.get(Setting.FOLDER_FILE_PATH)):
            raise BackupFolderMissingError()
        if os.path.exists(self.config.get(Setting.FOLDER_FILE_PATH)):
            with open(self.config.get(Setting.FOLDER_FILE_PATH), "r") as folder_file:
                folder_id: str = folder_file.readline()
            if await self._verify(folder_id):
                return folder_id
            else:
                raise BackupFolderInaccessible(folder_id)

    async def _search(self) -> str:
        folders = []

        try:
            async for child in self.drivebackend.query("mimeType='" + FOLDER_MIME_TYPE + "'"):
                if self._isValidFolder(child):
                    folders.append(child)
        except ClientResponseError as e:
            # 404 means the folder doesn't exist (maybe it got moved?)
            if e.status == 404:
                "Make Error"
                raise LogInToGoogleDriveError()
            else:
                raise e

        if len(folders) == 0:
            return None

        folders.sort(key=lambda c: Time.parse(c.get("modifiedTime")))
        # Found a folder, which means we're probably using the add-on from a
        # previous (or duplicate) installation.  Record and return the id but don't
        # persist it until the user chooses to do so.
        folder = folders[len(folders) - 1]
        logger.info("Found " + folder.get('name'))
        return folder

    async def _verify(self, id):
        if self.drivebackend.isCustomCreds():
            # If the user is using custom creds and specifying the backup folder, then chances are the
            # app doesn't have permission to access the parent folder directly.  Ironically, we can still
            # query for children and add/remove backups.  Not a huge deal, just
            # means we can't verify the folder still exists, isn't trashed, etc.  Just let it be valid
            # and handle potential errors elsewhere.
            return True
        # Query drive for the folder to make sure it still exists and we have the right permission on it.
        try:
            folder = await self.drivebackend.get(id)
            if not self._isValidFolder(folder):
                logger.info("Provided backup folder {0} is invalid".format(id))
                return False
            self._folder_details = folder
            return True
        except ClientResponseError as e:
            if e.status == 404:
                # 404 means the folder doesn't exist (maybe it got moved?) but can also mean that we
                # just don't have permission to see the folder.   Often we can still upload into it, so just
                # let it pass without further verification and let other error handling (on upload) identify problems.
                return True
            else:
                raise e
        except GoogleDrivePermissionDenied:
            # Lost permission on the backup folder
            return False

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
                if self._isSharedDrive(folder) and caps.get("canTrashChildren", False):
                    # Allow folders in shared drives if you can still trash items inside it.
                    return True
                return False
            elif folder.get("mimeType") != FOLDER_MIME_TYPE:
                return False
        except Exception:
            return False
        return True

    async def create(self) -> str:
        logger.info('Creating folder "{}" in "My Drive"'.format(FOLDER_NAME))
        file_metadata: Dict[str, str] = {
            'name': FOLDER_NAME,
            'mimeType': FOLDER_MIME_TYPE,
            'appProperties': {
                "backup_folder": "true",
            },
        }
        folder = await self.drivebackend.createFolder(file_metadata)
        self._folder_details = folder
        await self.save(folder)
        return folder.get('id')
