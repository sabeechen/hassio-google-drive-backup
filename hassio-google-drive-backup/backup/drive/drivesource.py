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
from ..model.snapshots import (PROP_KEY_DATE, PROP_KEY_NAME, PROP_KEY_SLUG,
                               PROP_PROTECTED, PROP_RETAINED, PROP_TYPE,
                               PROP_VERSION)
from ..time import Time
from .driverequests import DriveRequests
from .folderfinder import FolderFinder
from .thumbnail import THUMBNAIL_IMAGE
from ..model import SnapshotDestination, DriveSnapshot, Snapshot
from ..logger import getLogger
from ..creds.creds import Creds

logger = getLogger(__name__)

MIME_TYPE = "application/tar"
THUMBNAIL_MIME_TYPE = "image/png"
FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'
FOLDER_NAME = 'Home Assistant Snapshots'
FOLDER_CACHE_SECONDS = 30


@singleton
class DriveSource(SnapshotDestination):
    # SOMEDAY: read snapshots all in one big batch request, then sort the folder and child addons from that.  Would need to add test verifying the "current" backup directory is used instead of the "latest"
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

    async def create(self, options: CreateOptions) -> DriveSnapshot:
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

    async def get(self, allow_retry=True) -> Dict[str, DriveSnapshot]:
        parent = await self.getFolderId()
        try:
            self._drive_info = await self.drivebackend.getAboutInfo()
        except Exception as e:
            # This is just used to get the remaining space in Drive, which is a
            # nice to have.  Just log the error to debug if we can't get it
            logger.debug("Unable to retrieve Google Drive storage info: " + str(e))
        snapshots: Dict[str, DriveSnapshot] = {}
        try:
            async for child in self.drivebackend.query("'{}' in parents".format(parent)):
                properties = child.get('appProperties')
                if properties and PROP_KEY_DATE in properties and PROP_KEY_SLUG in properties and not child['trashed']:
                    snapshot = DriveSnapshot(child)
                    snapshots[snapshot.slug()] = snapshot
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
        return snapshots

    async def delete(self, snapshot: Snapshot):
        item = self._validateSnapshot(snapshot)
        if item.canDeleteDirectly():
            logger.info("Deleting '{}' From Google Drive".format(item.name()))
            await self.drivebackend.delete(item.id())
        else:
            logger.info("Trashing '{}' in Google Drive".format(item.name()))
            await self.drivebackend.update(item.id(), {"trashed": True})
        snapshot.removeSource(self.name())

    async def save(self, snapshot: Snapshot, source: AsyncHttpGetter) -> DriveSnapshot:
        retain = snapshot.getOptions() and snapshot.getOptions().retain_sources.get(self.name(), False)
        parent_id = await self.getFolderId()
        file_metadata = {
            'name': str(snapshot.name()) + ".tar",
            'parents': [parent_id],
            'description': 'A Home Assistant backup file uploaded by Home Assistant Google Drive Backup',
            'appProperties': {
                PROP_KEY_SLUG: snapshot.slug(),
                PROP_KEY_DATE: str(snapshot.date()),
                PROP_TYPE: str(snapshot.snapshotType()),
                PROP_VERSION: str(snapshot.version()),
                PROP_PROTECTED: str(snapshot.protected()),
                PROP_RETAINED: str(retain)
            },
            'contentHints': {
                'indexableText': 'Home Assistant hassio snapshot backup home assistant',
                'thumbnail': {
                    'image': THUMBNAIL_IMAGE,
                    'mimeType': THUMBNAIL_MIME_TYPE
                }
            },
            'createdTime': self._timeToRfc3339String(snapshot.date()),
            'modifiedTime': self._timeToRfc3339String(snapshot.date())
        }

        if len(snapshot.name().encode()) < 100:
            file_metadata['appProperties'][PROP_KEY_NAME] = str(snapshot.name())

        async with source:
            try:
                logger.info("Uploading '{}' to Google Drive".format(
                    snapshot.name()))
                size = source.size()
                self._info.upload(size)
                snapshot.overrideStatus("Uploading {0}%", source)
                snapshot.setUploadSource(self.title(), source)
                async for progress in self.drivebackend.create(source, file_metadata, MIME_TYPE):
                    self._uploadedAtLeastOneChunk = True
                    if isinstance(progress, float):
                        logger.debug("Uploading {1} {0:.2f}%".format(
                            progress * 100, snapshot.name()))
                    else:
                        return DriveSnapshot(progress)
                raise LogicError(
                    "Google Drive backup upload didn't return a completed item before exiting")
            except ClientResponseError as e:
                if e.status == 404:
                    # IIUC, 404 on create can only mean that the parent id isn't valid anymore.
                    raise BackupFolderInaccessible(parent_id)
                raise e
            except GoogleDrivePermissionDenied:
                # This should always mean we lost permission on the backup folder, since we could have only just
                # created the snapshot item on this request.
                raise BackupFolderInaccessible(parent_id)
            finally:
                snapshot.clearUploadSource()
                self._uploadedAtLeastOneChunk = False
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

    async def getFolderId(self):
        return await self.folder_finder.get()

    def _validateSnapshot(self, snapshot: Snapshot) -> DriveSnapshot:
        drive_item: DriveSnapshot = snapshot.getSource(self.name())
        if not drive_item:
            raise LogicError(
                "Requested to do something with a snapshot from Google Drive, but the snapshot has no Google Drive source")
        return drive_item

    def _timeToRfc3339String(self, time: datetime) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ")

    async def _get(self, id):
        return await self.drivebackend.get(id)
