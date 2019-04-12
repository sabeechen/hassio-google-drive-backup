import os.path
import os
import requests
import httplib2

from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.discovery import Resource
from apiclient.http import MediaIoBaseUpload
from apiclient.errors import HttpError
from oauth2client.client import Credentials
from time import sleep
from oauth2client.file import Storage
from .snapshots import DriveSnapshot
from .snapshots import Snapshot
from .snapshots import PROP_KEY_DATE
from .snapshots import PROP_KEY_SLUG
from .snapshots import PROP_KEY_NAME
from .snapshots import PROP_TYPE
from .snapshots import PROP_VERSION
from .snapshots import PROP_PROTECTED
from .hassio import HEADERS
from typing import List, Dict, TypeVar, Any
from requests import Response
from .config import Config
from .responsestream import ResponseStream
from .logbase import LogBase
from .thumbnail import THUMBNAIL_IMAGE
from .helpers import parseDateTime

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
        self.cred_storage: Storage = Storage(config.credentialsFilePath())
        self.creds: Credentials = self.cred_storage.get()
        self.config: Config = config

    def saveCreds(self, creds: Credentials) -> None:
        self.creds = creds
        self.cred_storage.put(creds)

    def _drive(self) -> Resource:
        if self.creds is None:
            raise Exception("Drive isn't enabled, this is a bug")
        if self.creds.access_token_expired:
            self.creds.refresh(httplib2.Http())
            self.cred_storage.put(self.creds)
        return build(DRIVE_SERVICE, DRIVE_VERSION, credentials=self.creds)

    def enabled(self) -> bool:
        """
        Drive isn't "enabled" until the user goes through the Google authentication flow in Server, so this
        is a convenient way to track if that has happened or not.
        """
        return self.creds is not None

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
                PROP_PROTECTED: str(snapshot.protected())
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
        response: Response = requests.get(download_url, stream=True, headers=HEADERS)
        stream: ResponseStream = ResponseStream(response.iter_content(262144))
        media: MediaIoBaseUpload = MediaIoBaseUpload(stream, mimetype='application/tar', chunksize=262144, resumable=True)
        snapshot.uploading(0)
        request = self._drive().files().create(media_body=media, body=file_metadata, fields=CREATE_FIELDS)
        drive_response = None
        last_percent = -1
        while drive_response is None:
            status2, drive_response = self._retryDriveServiceCall(request, func=lambda a: a.next_chunk())
            if status2:
                new_percent = int(status2.progress() * 100)
                if last_percent != new_percent:
                    last_percent = new_percent
                    snapshot.uploading(last_percent)
                    self.info("Uploading {1} {0}%".format(last_percent, snapshot.name()))
        snapshot.uploading(100)
        snapshot.setDrive(DriveSnapshot(drive_response))

    def deleteSnapshot(self, snapshot: Snapshot) -> None:
        self.info("Deleting: {}".format(snapshot))
        if not snapshot.driveitem:
            raise Exception("Drive item was null")
        self._retryDriveServiceCall(self._drive().files().delete(fileId=snapshot.driveitem.id()))
        self.info("Deleted snapshot backup from drive '{}'".format(snapshot.name()))
        snapshot.driveitem = None

    def _timeToRfc3339String(self, time: datetime) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ")

    def readSnapshots(self, parent_id: str) -> List[DriveSnapshot]:
        snapshots: List[DriveSnapshot] = []
        for child in self._iterateQuery(q="'{}' in parents".format(parent_id)):
            properties = child.get('appProperties')
            if properties and PROP_KEY_DATE in properties and PROP_KEY_SLUG in properties and PROP_KEY_NAME in properties and not child.get('trashed'):
                snapshots.append(DriveSnapshot(child))
        return snapshots

    T = TypeVar('T')
    V = TypeVar('V')

    def _retryDriveServiceCall(self, request: Any, func: Any = None) -> Any:
        attempts = 0
        backoff = DRIVE_RETRY_INITIAL_SECONDS
        while True:
            try:
                attempts += 1
                if func is None:
                    return request.execute()
                else:
                    return func(request)
            except HttpError as e:
                if attempts >= DRIVE_MAX_RETRIES:
                    # fail, too many retries
                    self.error("Too many calls to Drive failed, so we'll give up for now")
                    raise e
                # Only retry 403 and 5XX error, see https://developers.google.com/drive/api/v3/manage-uploads
                if e.resp.status != 403 and int(e.resp.status / 5) != 5:
                    self.error("Drive returned non-retryable error code: {0}".format(e.resp.status))
                    raise e
                self.error("Drive returned error code: {0}:, we'll retry in {1} seconds".format(e.resp.status, backoff))
                sleep(backoff)
                backoff *= DRIVE_EXPONENTIAL_BACKOFF

    def getFolderId(self) -> str:
        # First, check if we cached the drive folder
        if os.path.exists(self.config.folderFilePath()):
            with open(self.config.folderFilePath(), "r") as folder_file:
                folder_id: str = folder_file.readline()

                # Query drive for the folder to make sure it still exists and we have the right permission on it.
                try:
                    folder = self._retryDriveServiceCall(self._drive().files().get(fileId=folder_id, fields='id,trashed,capabilities,mimeType,name,modifiedTime'))
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

    def _findDriveFolder(self) -> str:
        folders = []

        for child in self._iterateQuery(q="mimeType='" + FOLDER_MIME_TYPE + "'"):
            if self._isValidFolder(child):
                folders.append(child)

        folders.sort(key=lambda c: parseDateTime(c.get("modifiedTime")))
        if len(folders) > 0:
            self.info("Found " + folders[len(folders) - 1].get('name'))
            return self._saveFolder(folders[len(folders) - 1])
        return self._createDriveFolder()

    def _iterateQuery(self, q=None):
        token = None
        while(True):
            if token:
                request = self._drive().files().list(
                    q=q,
                    fields=QUERY_FIELDS,
                    pageToken=token,
                    pageSize=1
                )
            else:
                request = self._drive().files().list(
                    q=q,
                    fields=QUERY_FIELDS,
                    pageSize=1
                )
            response = self._retryDriveServiceCall(request)
            for child in response['files']:
                yield child
            if 'nextPageToken' not in response or len(response['nextPageToken']) == 0:
                break
            token = response['nextPageToken']

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
        folder = self._retryDriveServiceCall(self._drive().files().create(body=file_metadata, fields='id'))
        return self._saveFolder(folder)

    def _saveFolder(self, folder: Any) -> str:
        self.info("Saving snapshot folder: " + folder.get('id'))
        with open(self.config.folderFilePath(), "w") as folder_file:
            folder_file.write(folder.get('id'))
        return folder.get('id')

    def downloadDriveFile(id):
        pass
