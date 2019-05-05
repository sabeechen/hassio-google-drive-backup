from googleapiclient.discovery import build
from googleapiclient.discovery import Resource
from apiclient.http import MediaIoBaseUpload
from apiclient.http import MediaIoBaseDownload
from apiclient.errors import HttpError
from oauth2client.client import Credentials
from time import sleep
from oauth2client.file import Storage
from typing import Any
from .config import Config
from .responsestream import IteratorByteStream
from .logbase import LogBase

import httplib2

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


class Buffer(object):
    def __init__(self):
        self.bytes = None

    def write(self, bytes):
        self.bytes = bytes

    def close(self):
        pass


class DrivePython(LogBase):
    def __init__(self, config: Config):
        self.cred_storage: Storage = Storage(config.credentialsFilePath())
        self.creds: Credentials = self.cred_storage.get()

    def enabled(self):
        return self.creds is not None

    def saveCredentials(self, creds: Credentials):
        self.creds = creds
        self.cred_storage.put(creds)

    def get(self, id):
        return self._retryDriveServiceCall(self._drive().files().get(fileId=id, fields=SELECT_FIELDS))

    def download(self, id, length_bytes):
        return IteratorByteStream(self._download(id))

    def query(self, query):
        return self._iterateQuery(query)

    def update(self, id, update_metadata):
        self._drive().files().update(fileId=id, body=update_metadata).execute()

    def delete(self, id):
        self._retryDriveServiceCall(self._drive().files().delete(fileId=id))

    def create(self, stream, metadata, mime_type):
        media: MediaIoBaseUpload = MediaIoBaseUpload(stream, mimetype=mime_type, chunksize=5 * 262144, resumable=True)
        request = self._drive().files().create(media_body=media, body=metadata, fields=CREATE_FIELDS)
        drive_response = None
        while drive_response is None:
            status2, drive_response = self._retryDriveServiceCall(request, func=lambda a: a.next_chunk())
            if status2:
                yield float(status2.progress())
        yield drive_response

    def createFolder(self, metadata):
        # TODO: Make work
        return self._retryDriveServiceCall(self._drive().files().create(body=metadata, fields=CREATE_FIELDS))

    def _drive(self) -> Resource:
        if self.creds is None:
            raise Exception("Drive isn't enabled, this is a bug")
        if self.creds.access_token_expired:
            self.creds.refresh(httplib2.Http())
            self.cred_storage.put(self.creds)
        return build(DRIVE_SERVICE, DRIVE_VERSION, credentials=self.creds)

    def _download(self, id):
        request = self._drive().files().get_media(fileId=id)
        fh = Buffer()
        downloader = MediaIoBaseDownload(fh, request, chunksize=5 * 1024 * 1024)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            self.debug("Downloading {0} {1}%".format(id, int(status.progress() * 100)))
            yield fh.bytes
        fh.close()

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
