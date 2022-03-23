import io
import json
import math
import os
import re
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from datetime import timedelta

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientResponseError, ServerTimeoutError
from injector import inject, singleton

from ..util import AsyncHttpGetter
from ..config import Config, Setting
from ..exceptions import (GoogleCredentialsExpired,
                          GoogleSessionError, LogicError,
                          ProtocolError, ensureKey, KnownTransient, GoogleTimeoutError, GoogleUnexpectedError)
from backup.util import Backoff
from ..time import Time
from ..logger import getLogger
from backup.creds import Creds, Exchanger, DriveRequester

logger = getLogger(__name__)

MIME_TYPE = "application/tar"
FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'
FOLDER_NAME = 'Home Assistant Backups'
DRIVE_VERSION = "v3"
DRIVE_SERVICE = "drive"

SELECT_FIELDS = "id,name,appProperties,size,trashed,mimeType,modifiedTime,capabilities,parents,driveId"
THUMBNAIL_MIME_TYPE = "image/png"
QUERY_FIELDS = "nextPageToken,files(" + SELECT_FIELDS + ")"
CREATE_FIELDS = SELECT_FIELDS
URL_FILES = "/drive/v3/files/"
URL_ABOUT = "/drive/v3/about"
URL_START_UPLOAD = "/upload/drive/v3/files/?uploadType=resumable&supportsAllDrives=true"
PAGE_SIZE = 100
CHUNK_SIZE = 5 * 262144
RANGE_RE = re.compile("^bytes=0-\\d+$")

BASE_CHUNK_SIZE = 256 * 1024  # Google's api requires uploading chunks in multiples of 256kb

# During upload, chunks get sized to complete upload after 10s so we can give status updates on progress.
CHUNK_UPLOAD_TARGET_SECONDS = 10

# don't attempt to resume a session with than this many times consistant failures, just in case something is broken on Google's
# end so we don't retry the same broken session forever.  Because the addon eventually backs off to doing 1 attempt/hour, this will
# cause uploads to fail and start over after about 4 days.  This gets reset every time a chunk successfully uploads.
# God be with you if your upload takes that long.
RETRY_SESSION_ATTEMPTS = 100

# Google claims that an upload session becomes invalid after 7 days.  I have not verified this, but probably better to call it
# after 6 and restart the session.
UPLOAD_SESSION_EXPIRATION_DURATION = timedelta(days=6)


RATE_LIMIT_EXCEEDED = 403
TOO_MANY_REQUESTS = 429


# Defines the retry strategy for calls made to Drive
# max # of time to retry and call to Drive
DRIVE_MAX_RETRIES: int = 5
# The initial backoff for drive retries.
DRIVE_RETRY_INITIAL_SECONDS: int = 2
# How uch longer to wait for each Drive service call (Exponential backoff)
DRIVE_EXPONENTIAL_BACKOFF: int = 2


@singleton
class DriveRequests():
    @inject
    def __init__(self, config: Config, time: Time, drive: DriveRequester, session: ClientSession, exchanger: Exchanger):
        self.session = session
        self.config = config
        self.time = time
        self.drive = drive
        self.creds: Optional[Creds] = None
        self.exchanger: Exchanger = exchanger

        # Between attempts to upload, we keep track of the info needed to resume a resumable upload.
        self.last_attempt_metadata = None
        self.last_attempt_location = None
        self.last_attempt_count = 0
        self.last_attempt_start_time = None
        self.tryLoadCredentials()

    async def _getHeaders(self):
        return {
            "Authorization": "Bearer " + await self.getToken(),
            "Client-Identifier": self.config.clientIdentifier()
        }

    def isCustomCreds(self):
        return self.creds is not None and self.creds.id != self.config.get(Setting.DEFAULT_DRIVE_CLIENT_ID)

    def _getAuthHeaders(self):
        return {
            "Client-Identifier": self.config.clientIdentifier()
        }

    def enabled(self):
        return self.creds is not None and self.config.get(Setting.ENABLE_DRIVE_UPLOAD)

    def _enabledCheck(self):
        if not self.enabled():
            raise LogicError(
                "Attempt to use Google Drive before credentials are configured")

    def tryLoadCredentials(self):
        if os.path.isfile(self.config.get(Setting.CREDENTIALS_FILE_PATH)):
            try:
                with open(self.config.get(Setting.CREDENTIALS_FILE_PATH)) as f:
                    self.creds = Creds.load(self.time, json.load(f))
                return
            except Exception:
                pass

    def saveCredentials(self, creds: Creds):
        if not creds:
            if os.path.exists(self.config.get(Setting.CREDENTIALS_FILE_PATH)):
                os.remove(self.config.get(Setting.CREDENTIALS_FILE_PATH))
                self.creds = None
            return
        with open(self.config.get(Setting.CREDENTIALS_FILE_PATH), "w") as f:
            json.dump(creds.serialize(), f)
        self.tryLoadCredentials()

    async def getToken(self, refresh=False):
        if self.creds and not self.creds.is_expired and not refresh:
            return self.creds.access_token

        # refresh the credentials
        logger.debug("Requesting refreshed Google Drive credentials")
        self.creds = await self.exchanger.refresh(self.creds)
        return self.creds.access_token

    async def refreshToken(self):
        await self.getToken(refresh=True)

    async def get(self, id):
        q = {
            "fields": SELECT_FIELDS,
            "supportsAllDrives": "true"
        }
        return await self.retryRequest("GET", URL_FILES + id + "/?" + urlencode(q), is_json=True)

    async def download(self, id, size):
        ret = AsyncHttpGetter(self.config.get(Setting.DRIVE_URL) + URL_FILES + id + "/?alt=media&supportsAllDrives=true",
                              await self._getHeaders(),
                              self.session,
                              size=size,
                              timeoutFactory=GoogleTimeoutError.factory,
                              otherErrorFactory=GoogleUnexpectedError.factory,
                              timeout=ClientTimeout(
                                  sock_connect=self.config.get(Setting.DOWNLOAD_TIMEOUT_SECONDS),
                                  sock_read=self.config.get(Setting.DOWNLOAD_TIMEOUT_SECONDS)),
                              time=self.time)
        return ret

    async def query(self, query):
        # SOMEDAY: Add a test for page size, test server support is needed too for continuation tokens
        continuation = None
        while True:
            q = {
                "q": query,
                "fields": QUERY_FIELDS,
                "pageSize": self.config.get(Setting.GOOGLE_DRIVE_PAGE_SIZE),
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
                "corpora": "allDrives"
            }
            if continuation:
                q["pageToken"] = continuation
            response = await self.retryRequest("GET", URL_FILES + "?" + urlencode(q), is_json=True)
            for item in response['files']:
                yield item
            if "nextPageToken" not in response or len(response['nextPageToken']) <= 0:
                break
            else:
                continuation = response['nextPageToken']

    async def update(self, id, update_metadata):
        resp = await self.retryRequest("PATCH", URL_FILES + id + "/?supportsAllDrives=true", json=update_metadata)
        async with resp:
            pass

    async def delete(self, id):
        resp = await self.retryRequest("DELETE", URL_FILES + id + "/?supportsAllDrives=true")
        async with resp:
            pass

    async def getAboutInfo(self):
        q = {"fields": 'storageQuota'}
        return await self.retryRequest("GET", URL_ABOUT + "?" + urlencode(q), is_json=True)

    async def create(self, stream, metadata, mime_type):
        # Upload logic is complicated. See https://developers.google.com/drive/api/v3/manage-uploads#resumable
        total_size = stream.size()
        location = None
        if metadata == self.last_attempt_metadata and self.last_attempt_location is not None and self.last_attempt_count < RETRY_SESSION_ATTEMPTS and self.time.now() < self.last_attempt_start_time + UPLOAD_SESSION_EXPIRATION_DURATION:
            logger.debug(
                "Attempting to resume a previously failed upload where we left off")
            self.last_attempt_count += 1
            # Attempt to resume from a partially completed upload.
            headers = {
                "Content-Length": "0",
                "Content-Range": "bytes */{0}".format(total_size)
            }
            try:
                initial = await self.retryRequest("PUT", self.last_attempt_location, headers=headers, patch_url=False)
                async with initial:
                    if initial.status == 308:
                        # We can resume the upload, check where it left off
                        if 'Range' in initial.headers:
                            position = int(initial.headers["Range"][len("bytes=0-"):])
                            stream.position(position + 1)
                        else:
                            # No range header in the response means no bytes have been uploaded yet.
                            stream.position(0)
                        logger.debug("Resuming upload at byte {0} of {1}".format(
                            stream.position(), total_size))
                        location = self.last_attempt_location
                    else:
                        logger.debug("Drive returned status code {0}, so we'll have to start the upload over again.".format(
                            initial.status))
            except ClientResponseError as e:
                if e.status == 410:
                    # Drive doesn't recognize the resume token, so we'll just have to start over.
                    logger.debug("Drive upload session wasn't recognized, restarting upload form the beginning.")
                    location = None
                else:
                    raise

        if location is None:
            # There is no session resume, so start a new one.
            logger.debug("Starting a new upload session with Google Drive")
            headers = {
                "X-Upload-Content-Type": mime_type,
                "X-Upload-Content-Length": str(total_size),
            }
            initial = await self.retryRequest("POST", URL_START_UPLOAD, headers=headers, json=metadata)
            async with initial:
                # Google returns a url in the header "Location", which is where subsequent requests to upload
                # the backup's bytes should be sent.  Logic below handles uploading the file bytes in chunks.
                location = ensureKey(
                    'Location', initial.headers, "Google Drive's Upload headers")
                self.last_attempt_count = 0
                stream.position(0)

        # Keep track of the location in case the upload fails and we want to resume where we left off.
        # "metadata" is a durable fingerprint that uniquely identifies a backup, so we can use it to identify a
        # resumable partial upload in future retrys.
        self.last_attempt_location = location
        self.last_attempt_metadata = metadata
        self.last_attempt_start_time = self.time.now()

        # Always start with the minimum chunk size and work up from there in case the last attempt
        # failed due to connectivity errors or ... whatever.
        current_chunk_size = BASE_CHUNK_SIZE
        while True:
            start = stream.position()
            data: io.IOBaseBytesio = await stream.read(current_chunk_size)
            chunk_size = len(data.getbuffer())
            if chunk_size == 0:
                raise LogicError(
                    "Backup file stream ended prematurely while uploading to Google Drive")
            headers = {
                "Content-Length": str(chunk_size),
                "Content-Range": "bytes {0}-{1}/{2}".format(start, start + chunk_size - 1, total_size)
            }
            try:
                startTime = self.time.now()
                logger.debug("Sending {0} bytes to Google Drive".format(
                    current_chunk_size))
                partial = await self.retryRequest("PUT", location, headers=headers, data=data, patch_url=False)

                # Base the next chunk size on how long it took to send the last chunk.
                current_chunk_size = self._getNextChunkSize(
                    current_chunk_size, (self.time.now() - startTime).total_seconds())

                # any time a chunk gets uploaded, reset the retry counter.  This lets very flaky connections
                # complete eventually after enough retrying.
                self.last_attempt_count = 1
            except ClientResponseError as e:
                if math.floor(e.status / 100) == 4:
                    # clear the cached session location URI, since a 4XX error
                    # always means the upload session is no good anymore (AFAIK)
                    self.last_attempt_location = None
                    self.last_attempt_metadata = None

                if e.status == 404:
                    raise GoogleSessionError()
                else:
                    raise e
            yield float(start + chunk_size) / float(total_size)
            if partial.status == 200 or partial.status == 201:
                # Upload completed, return the object json
                self.last_attempt_location = None
                self.last_attempt_metadata = None
                yield await self.get((await partial.json())['id'])
                break
            elif partial.status == 308:
                # Upload partially complete, seek to the new requested position
                range_bytes = ensureKey(
                    "Range", partial.headers, "Google Drive's upload response headers")
                if not RANGE_RE.match(range_bytes):
                    raise ProtocolError(
                        "Range", partial.headers, "Google Drive's upload response headers")
                position = int(partial.headers["Range"][len("bytes=0-"):])
                stream.position(position + 1)
            else:
                partial.raise_for_status()
            await partial.release()

    def _getNextChunkSize(self, last_chunk_size, last_chunk_seconds):
        max = BASE_CHUNK_SIZE * math.floor(self.config.get(Setting.MAXIMUM_UPLOAD_CHUNK_BYTES) / BASE_CHUNK_SIZE)
        if max < BASE_CHUNK_SIZE:
            max = BASE_CHUNK_SIZE
        if last_chunk_seconds <= 0:
            return max
        next_chunk = CHUNK_UPLOAD_TARGET_SECONDS * last_chunk_size / last_chunk_seconds
        if next_chunk >= max:
            return max
        if next_chunk < BASE_CHUNK_SIZE:
            return BASE_CHUNK_SIZE
        return math.floor(next_chunk / BASE_CHUNK_SIZE) * BASE_CHUNK_SIZE

    async def createFolder(self, metadata):
        return await self.retryRequest("POST", URL_FILES + "?supportsAllDrives=true", is_json=True, json=metadata)

    async def retryRequest(self, method, url, auth_headers: Optional[Dict[str, str]] = None, headers: Optional[Dict[str, str]] = None, json: Optional[Dict[str, Any]] = None, data: Any = None, is_json: bool = False, cred_retry: bool = True, patch_url: bool = True):
        backoff = Backoff(base=DRIVE_RETRY_INITIAL_SECONDS, attempts=DRIVE_MAX_RETRIES)
        if patch_url:
            url = self.config.get(Setting.DRIVE_URL) + url
        while True:
            headers_to_use = await self._getHeaders()
            if headers:
                headers_to_use.update(headers)
            logger.debug("Making Google Drive request: " + url)
            try:
                data_to_use = data
                if isinstance(data_to_use, io.BytesIO):
                    # This is a pretty low-down dirty hack, but it works and lets us reuse the byte stream.
                    # aiohttp complains if you pass it a large byte object
                    data_to_use = io.BytesIO(data_to_use.getbuffer())
                    data_to_use.seek(0)
                response = await self.drive.request(method, url, headers=headers_to_use, json=json, data=data_to_use)
                if is_json:
                    ret = await response.json()
                    await response.release()
                    return ret
                else:
                    return response
            except GoogleCredentialsExpired:
                # Get fresh credentials, then retry right away.
                logger.debug("Google Drive credentials have expired.  We'll retry with new ones.")
                await self.refreshToken()
            except KnownTransient as e:
                backoff.backoff(e)
                logger.error("{0}: we'll retry in {1} seconds".format(e.message(), backoff.peek()))
                await self.time.sleepAsync(backoff.peek())
            except ServerTimeoutError:
                raise GoogleTimeoutError()
