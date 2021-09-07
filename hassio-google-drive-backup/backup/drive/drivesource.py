from datetime import datetime
from io import IOBase
from typing import Dict

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientResponseError
from injector import inject, singleton

from ..util import AsyncHttpGetter, GlobalInfo
from ..config import Config, Setting, CreateOptions
from ..const import SOURCE_GOOGLE_DRIVE
from ..exceptions import (BackupFolderInaccessible,
                          ExistingBackupFolderError,
                          GoogleDrivePermissionDenied, LogicError)
from ..model.backups import (PROP_PROTECTED, PROP_RETAINED, PROP_TYPE, PROP_VERSION)
from ..time import Time
from .driverequests import DriveRequests
from .folderfinder import FolderFinder
from .thumbnail import THUMBNAIL_IMAGE
from ..model import BackupDestination, DriveBackup, Backup
from ..logger import getLogger
from ..creds.creds import Creds
from backup.const import NECESSARY_OLD_BACKUP_NAME, NECESSARY_OLD_BACKUP_PLURAL_NAME, NECESSARY_PROP_KEY_SLUG, NECESSARY_PROP_KEY_DATE, NECESSARY_PROP_KEY_NAME

logger = getLogger(__name__)

MIME_TYPE = "application/tar"
THUMBNAIL_MIME_TYPE = "image/png"
FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'
FOLDER_NAME = 'Home Assistant Backups'
FOLDER_CACHE_SECONDS = 30


@singleton
class DriveSource(BackupDestination):
    # SOMEDAY: read backups all in one big batch request, then sort the folder and child addons from that.  Would need to add test verifying the "current" backup directory is used instead of the "latest"
    @inject
    def __init__(self, config: Config, time: Time, drive_requests: DriveRequests, info: GlobalInfo, session: ClientSession, folderfinder: FolderFinder):
        super().__init__()
        self.session = session
        self.config = config
        self.drivebackend: DriveRequests = drive_requests
        self.time = time
        self.folder_finder = folderfinder
        self._info = info
        self._uploadedAtLeastOneChunk = False
        self._drive_info = None

    def saveCreds(self, creds: Creds) -> None:
        logger.info("Saving new Google Drive credentials")
        self.drivebackend.saveCredentials(creds)
        self.trigger()

    def isCustomCreds(self):
        return self.drivebackend.isCustomCreds()

    def name(self) -> str:
        return SOURCE_GOOGLE_DRIVE

    def title(self) -> str:
        return "Google Drive"

    def maxCount(self) -> None:
        return self.config.get(Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE)

    def upload(self) -> bool:
        return self.config.get(Setting.ENABLE_DRIVE_UPLOAD)

    def enabled(self) -> bool:
        return self.drivebackend.enabled()

    def needsConfiguration(self) -> bool:
        if not self.config.get(Setting.ENABLE_DRIVE_UPLOAD):
            return False
        return super().needsConfiguration()

    def freeSpace(self):
        if self._drive_info and self._drive_info.get("storageQuota") is not None and not self.folder_finder.currentIsSharedDrive():
            info = self._drive_info.get("storageQuota")
            if 'limit' in info and 'usage' in info:
                return int(info.get("limit")) - int((info.get("usage")))
        return super().freeSpace()

    async def create(self, options: CreateOptions) -> DriveBackup:
        raise LogicError("Backups can't be created in Drive")

    def checkBeforeChanges(self):
        existing = self.folder_finder.getExisting()
        if existing:
            raise ExistingBackupFolderError(
                existing.get('id'), existing.get('name'))

    def icon(self) -> str:
        return "google-drive"

    def isWorking(self):
        return self._uploadedAtLeastOneChunk

    async def get(self, allow_retry=True) -> Dict[str, DriveBackup]:
        parent = await self.getFolderId()
        try:
            self._drive_info = await self.drivebackend.getAboutInfo()
        except Exception as e:
            # This is just used to get the remaining space in Drive, which is a
            # nice to have.  Just log the error to debug if we can't get it
            logger.debug("Unable to retrieve Google Drive storage info: " + str(e))
        backups: Dict[str, DriveBackup] = {}
        try:
            async for child in self.drivebackend.query("'{}' in parents".format(parent)):
                properties = child.get('appProperties')
                if properties and NECESSARY_PROP_KEY_DATE in properties and NECESSARY_PROP_KEY_SLUG in properties and not child['trashed']:
                    backup = DriveBackup(child)
                    backups[backup.slug()] = backup
        except ClientResponseError as e:
            if e.status == 404:
                # IIUC, 404 on create can only mean that the parent id isn't valid anymore.
                if not self.config.get(Setting.SPECIFY_BACKUP_FOLDER) and allow_retry:
                    self.folder_finder.deCache()
                    await self.folder_finder.create()
                    return await self.get(False)
                raise BackupFolderInaccessible(parent)
            raise e
        except GoogleDrivePermissionDenied:
            # This should always mean we lost permission on the backup folder, but at least it still exists.
            if not self.config.get(Setting.SPECIFY_BACKUP_FOLDER) and allow_retry:
                self.folder_finder.deCache()
                await self.folder_finder.create()
                return await self.get(False)
            raise BackupFolderInaccessible(parent)
        return backups

    async def delete(self, backup: Backup):
        item = self._validateBackup(backup)
        if item.canDeleteDirectly():
            logger.info("Deleting '{}' From Google Drive".format(item.name()))
            await self.drivebackend.delete(item.id())
        else:
            logger.info("Trashing '{}' in Google Drive".format(item.name()))
            await self.drivebackend.update(item.id(), {"trashed": True})
        backup.removeSource(self.name())

    async def save(self, backup: Backup, source: AsyncHttpGetter) -> DriveBackup:
        retain = backup.getOptions() and backup.getOptions().retain_sources.get(self.name(), False)
        parent_id = await self.getFolderId()
        file_metadata = {
            'name': str(backup.name()) + ".tar",
            'parents': [parent_id],
            'description': 'A Home Assistant backup file uploaded by Home Assistant Google Drive Backup',
            'appProperties': {
                NECESSARY_PROP_KEY_SLUG: backup.slug(),
                NECESSARY_PROP_KEY_DATE: str(backup.date()),
                PROP_TYPE: str(backup.backupType()),
                PROP_VERSION: str(backup.version()),
                PROP_PROTECTED: str(backup.protected()),
                PROP_RETAINED: str(retain)
            },
            'contentHints': {
                'indexableText': 'Home Assistant hassio ' + NECESSARY_OLD_BACKUP_NAME + ' ' + NECESSARY_OLD_BACKUP_PLURAL_NAME + ' backup backups home assistant',
                'thumbnail': {
                    'image': THUMBNAIL_IMAGE,
                    'mimeType': THUMBNAIL_MIME_TYPE
                }
            },
            'createdTime': self._timeToRfc3339String(backup.date()),
            'modifiedTime': self._timeToRfc3339String(backup.date())
        }

        if len(backup.name().encode()) < 100:
            file_metadata['appProperties'][NECESSARY_PROP_KEY_NAME] = str(backup.name())

        async with source:
            try:
                logger.info("Uploading '{}' to Google Drive".format(
                    backup.name()))
                size = source.size()
                self._info.upload(size)
                backup.overrideStatus("Uploading {0}%", source)
                backup.setUploadSource(self.title(), source)
                async for progress in self.drivebackend.create(source, file_metadata, MIME_TYPE):
                    self._uploadedAtLeastOneChunk = True
                    if isinstance(progress, float):
                        logger.debug("Uploading {1} {0:.2f}%".format(
                            progress * 100, backup.name()))
                    else:
                        return DriveBackup(progress)
                raise LogicError(
                    "Google Drive backup upload didn't return a completed item before exiting")
            except ClientResponseError as e:
                if e.status == 404:
                    # IIUC, 404 on create can only mean that the parent id isn't valid anymore.
                    raise BackupFolderInaccessible(parent_id)
                raise e
            except GoogleDrivePermissionDenied:
                # This should always mean we lost permission on the backup folder, since we could have only just
                # created the backup item on this request.
                raise BackupFolderInaccessible(parent_id)
            finally:
                backup.clearUploadSource()
                self._uploadedAtLeastOneChunk = False
                backup.clearStatus()

    async def read(self, backup: Backup) -> IOBase:
        item = self._validateBackup(backup)
        return await self.drivebackend.download(item.id(), item.size())

    async def retain(self, backup: Backup, retain: bool) -> None:
        item = self._validateBackup(backup)
        if item.retained() == retain:
            return
        file_metadata: Dict[str, str] = {
            'appProperties': {
                PROP_RETAINED: str(retain),
            },
        }
        await self.drivebackend.update(item.id(), file_metadata)
        item.setRetained(retain)

    async def getFolderId(self):
        return await self.folder_finder.get()

    def _validateBackup(self, backup: Backup) -> DriveBackup:
        drive_item: DriveBackup = backup.getSource(self.name())
        if not drive_item:
            raise LogicError(
                "Requested to do something with a backup from Google Drive, but the backup has no Google Drive source")
        return drive_item

    def _timeToRfc3339String(self, time: datetime) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ")

    async def _get(self, id):
        return await self.drivebackend.get(id)
