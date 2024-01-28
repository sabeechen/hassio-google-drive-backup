from datetime import datetime
from io import IOBase
from asyncio import Event
from typing import Dict, Any

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientResponseError
from injector import inject, singleton

from ..util import AsyncHttpGetter, GlobalInfo
from ..config import Config, Setting, CreateOptions
from ..config.byteformatter import ByteFormatter
from ..const import SOURCE_GOOGLE_DRIVE
from ..exceptions import (BackupFolderInaccessible,
                          ExistingBackupFolderError,
                          GoogleDrivePermissionDenied, 
                          LogicError,
                          DriveQuotaExceeded)
from ..model.backups import (PROP_NOTE, PROP_PROTECTED, PROP_RETAINED, PROP_TYPE, PROP_VERSION)
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
DRIVE_MAX_PROPERTY_LENGTH = 120


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
        self._cred_trigger = Event()

    def saveCreds(self, creds: Creds) -> None:
        logger.info("Saving new Google Drive credentials")
        self.drivebackend.saveCredentials(creds)
        self.trigger()
        self._cred_trigger.set()

    async def debug_wait_for_credentials(self):
        await self._cred_trigger.wait()
        self._cred_trigger.clear()

    def isCustomCreds(self):
        return self.drivebackend.isCustomCreds()

    @property
    def might_be_oob_creds(self) -> bool:
        return self.drivebackend.might_be_oob_creds

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

    def detail(self):
        if self._drive_info and 'user' in self._drive_info and 'emailAddress' in self._drive_info['user']:
            return f'{self._drive_info["user"]["emailAddress"]}'
        else:
            return super().detail()

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
        if backup.note() is not None:
            desc = backup.note()
        else:
            desc = 'A Home Assistant backup file uploaded by Home Assistant Google Drive Backup'
        file_metadata = {
            'name': str(backup.name()) + ".tar",
            'parents': [parent_id],
            'description': desc,
            'appProperties': {
                NECESSARY_PROP_KEY_SLUG: backup.slug(),
                NECESSARY_PROP_KEY_DATE: str(backup.date()),
                PROP_TYPE: str(backup.backupType()),
                PROP_VERSION: str(backup.version()),
                PROP_PROTECTED: str(backup.protected()),
                PROP_RETAINED: str(retain),
            },
            'contentHints': {
                'indexableText': 'Home Assistant hassio ' + NECESSARY_OLD_BACKUP_NAME + ' ' + NECESSARY_OLD_BACKUP_PLURAL_NAME + ' backup backups home assistant ' + desc,
                'thumbnail': {
                    'image': THUMBNAIL_IMAGE,
                    'mimeType': THUMBNAIL_MIME_TYPE
                }
            },
            'createdTime': self._timeToRfc3339String(backup.date()),
            'modifiedTime': self._timeToRfc3339String(backup.date())
        }

        if backup.note() is not None:
            file_metadata['appProperties'][PROP_NOTE] = self.truncateAppProperty(PROP_NOTE, backup.note())
        file_metadata['appProperties'][NECESSARY_PROP_KEY_NAME] = self.truncateAppProperty(NECESSARY_PROP_KEY_NAME, str(backup.name()))

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
            except DriveQuotaExceeded as space_error:
                try:
                    space_error.set_data({
                        'backup_size': ByteFormatter().format(backup.size()),
                        'free_space': ByteFormatter().format(self.freeSpace())
                    })
                except Exception as e:
                    space_error.set_data({
                        'backup_size': 'Error',
                        'free_space': 'Error'
                    })
                    logger.error(e)
                raise
            finally:
                backup.clearUploadSource()
                self._uploadedAtLeastOneChunk = False
                backup.clearStatus()

    def truncateAppProperty(self, key: str, value: str|None):
        # Annoylingly, Drive properties can be a maximum of 124 bytes, in len(key + value) UTF8 encoded.
        # https://developers.google.com/drive/api/guides/properties
        # Is the extra indexing REALLY that expensive? Thats like some 1990's mainframe limitation.
        # Make sure we stay well under that limit
        if value is None:
            return value
        permitted = ""
        current = 0
        while current < len(value) and len(str(key + permitted + value[current]).encode('utf-8')) < DRIVE_MAX_PROPERTY_LENGTH:
            permitted += value[current]
            current += 1
        return permitted

    async def read(self, backup: Backup) -> IOBase:
        item = self._validateBackup(backup)
        return await self.drivebackend.download(item.id(), item.size())

    async def retain(self, backup: Backup, retain: bool) -> None:
        item = self._validateBackup(backup)
        if item.retained() == retain:
            return
        file_metadata: Dict[str, Any] = {
            'appProperties': {
                PROP_RETAINED: str(retain),
            },
        }
        await self.drivebackend.update(item.id(), file_metadata)
        item.setRetained(retain)

    async def note(self, backup, note: str|None) -> None:
        item = self._validateBackup(backup)
        truncated = self.truncateAppProperty(PROP_NOTE, note)
        file_metadata: Dict[str, Any] = {
            'appProperties': {
                PROP_NOTE: truncated,
            },
            'description': note,
        }
        logger.debug(f"Adding a note to drive backup '{item.name()}'")
        await self.drivebackend.update(item.id(), file_metadata)
        item.setNote(truncated)

    async def getFolderId(self):
        return await self.folder_finder.get()

    def _validateBackup(self, backup: Backup) -> DriveBackup:
        drive_item = backup.getSource(self.name())
        if not drive_item or not isinstance(drive_item, DriveBackup):
            raise LogicError(
                "Requested to do something with a backup from Google Drive, but the backup has no Google Drive source")
        return drive_item

    def _timeToRfc3339String(self, time: datetime) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ")

    async def _get(self, id):
        return await self.drivebackend.get(id)
