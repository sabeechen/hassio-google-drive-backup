from .logbase import LogBase
from .seekablerequest import SeekableRequest
from .config import Config
from .time import Time
from .resolver import Resolver
from .exceptions import LogicError, GoogleCredentialsExpired, ProtocolError, ensureKey, GoogleInternalError, DriveQuotaExceeded, GoogleDnsFailure, GoogleCantConnect, GoogleTimeoutError, GoogleSessionError
from datetime import timedelta
from requests.exceptions import HTTPError, ConnectionError, Timeout, ConnectTimeout
from requests import Response
from dns.exception import DNSException
from urllib.parse import urlencode
import json
import os
import re
from oauth2client.client import Credentials
from typing import Dict, Any, Optional

MIME_TYPE = "application/tar"
FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'
FOLDER_NAME = 'Hass.io Snapshots'
DRIVE_VERSION = "v3"
DRIVE_SERVICE = "drive"

SELECT_FIELDS = "id,name,appProperties,size,trashed,mimeType,modifiedTime,capabilities"
THUMBNAIL_MIME_TYPE = "image/png"
QUERY_FIELDS = "nextPageToken,files(" + SELECT_FIELDS + ")"
CREATE_FIELDS = SELECT_FIELDS
URL_FILES = "/drive/v3/files/"
URL_UPLOAD = "/upload/drive/v3/files/?uploadType=resumable"
URL_AUTH = "/oauth2/v4/token"
PAGE_SIZE = 100
CHUNK_SIZE = 5 * 262144
RANGE_RE = re.compile("^bytes=0-\\d+$")


RATE_LIMIT_EXCEEDED = 403
TOO_MANY_REQUESTS = 429


# Defines the retry strategy for calls made to Drive
# max # of time to retry and call to Drive
DRIVE_MAX_RETRIES: int = 5
# The initial backoff for drive retries.
DRIVE_RETRY_INITIAL_SECONDS: int = 2
# How uch longer to wait for each Drive service call (Exponential backoff)
DRIVE_EXPONENTIAL_BACKOFF: int = 2


class DriveRequests(LogBase):
    def __init__(self, config: Config, time: Time, request_client, resolver: Resolver):
        self.config = config
        self.time = time
        self.resolver = resolver

        self.cred_expiration = None
        self.cred_bearer = None
        self.cred_refresh = None
        self.cred_id = None
        self.cred_secret = None
        self._request_client = request_client
        self.tryLoadCredentials()

    def _getHeaders(self, refresh=False):
        return {
            "Authorization": "Bearer " + self.getToken(refresh=refresh),
            "Client-Identifier": self.config.clientIdentifier()
        }

    def _getAuthHeaders(self):
        return {
            "Client-Identifier": self.config.clientIdentifier(),
            "Content-Type": "application/x-www-form-urlencoded"
        }

    def enabled(self):
        return self.cred_refresh is not None

    def _enabledCheck(self):
        if not self.enabled():
            raise LogicError("Attempt to use Google Drive before credentials are configured")

    def tryLoadCredentials(self):
        if os.path.isfile(self.config.credentialsFilePath()):
            try:
                with open(self.config.credentialsFilePath()) as f:
                    loaded = json.load(f)
                    self.cred_bearer = loaded['access_token']
                    self.cred_refresh = loaded['refresh_token']
                    self.cred_secret = loaded['client_secret']
                    self.cred_id = loaded['client_id']
                    try:
                        self.cred_expiration = self.time.parse(loaded['token_expiry'])
                    except Exception:
                        # just eat the error, refresh now
                        self.cred_expiration = self.time.now() - timedelta(minutes=1)
                    return
            except Exception:
                pass
        self.cred_bearer = None
        self.cred_expiration = None
        self.cred_refresh = None
        self.cred_secret = None
        self.cred_id = None

    def saveCredentials(self, creds: Credentials):
        parsed = json.loads(creds.to_json())
        with open(self.config.credentialsFilePath(), "w") as f:
            json.dump(parsed, f)
        self.tryLoadCredentials()

    def getToken(self, refresh=False):
        if self.cred_expiration and self.time.now() + timedelta(minutes=1) < self.cred_expiration and not refresh:
            return self.cred_bearer

        # refresh the credentials
        data = 'client_id={0}&client_secret={1}&refresh_token={2}&grant_type=refresh_token'.format(
            self.cred_id,
            self.cred_secret,
            self.cred_refresh)
        self.debug("Requesting refreshed Google Drive credentials")
        try:
            resp = self.retryRequest("POST", URL_AUTH, is_json=True, data=data, auth_headers=self._getAuthHeaders(), cred_retry=False)
        except HTTPError as e:
            if e.response.status_code != 401:
                raise e
            raise GoogleCredentialsExpired()
        self.cred_expiration = self.time.now() + timedelta(seconds=int(ensureKey('expires_in', resp, "Google Drive's credential Response")))
        self.cred_bearer = ensureKey('access_token', resp, "Google Drive's Credential Response")
        return self.cred_bearer

    def get(self, id):
        q = {
            "fields": SELECT_FIELDS
        }
        return self.retryRequest("GET", URL_FILES + id + "/?" + urlencode(q), is_json=True)

    def download(self, id):
        return SeekableRequest(self.config.driveHost() + URL_FILES + id + "/?alt=media", self._getHeaders()).prepare()

    def query(self, query):
        # SOMEDAY: Add a test for page size, test server support is needed too for continuation tokens
        continuation = None
        while True:
            q = {
                "q": query,
                "fields": QUERY_FIELDS,
                "pageSize": self.config.googleDrivePageSize()
            }
            if continuation:
                q["pageToken"] = continuation
            response = self.retryRequest("GET", URL_FILES + "?" + urlencode(q), is_json=True)
            for item in response['files']:
                yield item
            if "nextPageToken" not in response or len(response['nextPageToken']) <= 0:
                break
            else:
                continuation = response['nextPageToken']

    def update(self, id, update_metadata):
        self.retryRequest("PATCH", URL_FILES + id + "/", json=update_metadata)

    def delete(self, id):
        self.retryRequest("DELETE", URL_FILES + id + "/")

    def create(self, stream, metadata, mime_type):
        # Upload logic is complicated. See https://developers.google.com/drive/api/v3/manage-uploads
        total_size = stream.size()
        metadata_bytes = json.dumps(metadata).encode(encoding='UTF-8')
        headers = {
            "X-Upload-Content-Type": mime_type,
            "X-Upload-Content-Length": str(total_size),
            "Content-Length": str(len(metadata_bytes)),
            "Content-Type": "application/json; charset=UTF-8"
        }
        initial = self.retryRequest("POST", URL_UPLOAD, headers=headers, data=metadata_bytes)
        location = ensureKey('Location', initial.headers, "Google Drive's Upload headers")
        while True:
            start = stream.tell()
            data = stream.read(CHUNK_SIZE)
            if len(data) == 0:
                raise LogicError("Snapshot file stream ended prematurely while uploading to Google Drive")
            headers = {
                "Content-Length": str(len(data)),
                "Content-Range": "bytes {0}-{1}/{2}".format(start, start + len(data) - 1, total_size)
            }
            try:
                partial = self.retryRequest("PUT", location, headers=headers, data=data, patch_url=False)
            except HTTPError as e:
                if e.response.status_code == 404:
                    raise GoogleSessionError()
                else:
                    raise e
            yield float(start + len(data)) / float(total_size)
            if partial.status_code == 200 or partial.status_code == 201:
                # upload completed, return the object json
                yield self.get(partial.json()['id'])
                break
            elif partial.status_code == 308:
                # upload partially complete, seek to the new requested position
                range_bytes = ensureKey("Range", partial.headers, "Google Drive's upload response headers")
                if not RANGE_RE.match(range_bytes):
                    raise ProtocolError("Range", partial.headers, "Google Drive's upload response headers")
                position = int(partial.headers["Range"][len("bytes=0-"):])
                stream.seek(position + 1)
            else:
                partial.raise_for_status()

    def createFolder(self, metadata):
        return self.retryRequest("POST", URL_FILES, is_json=True, json=metadata)

    def retryRequest(self, method, url, auth_headers: Optional[Dict[str, str]] = None, headers: Optional[Dict[str, str]] = None, json: Optional[Dict[str, Any]] = None, data: Any = None, is_json: bool = False, stream: bool = False, cred_retry: bool = True, patch_url: bool = True) -> Any:
        backoff = DRIVE_RETRY_INITIAL_SECONDS
        attempts = 0
        refresh_token = False
        if patch_url:
            url = self.config.driveHost() + url
        while True:
            if auth_headers is not None:
                send_headers = auth_headers.copy()
            else:
                send_headers = self._getHeaders(refresh=refresh_token)
                refresh_token = False
            if headers:
                send_headers.update(headers)
            attempts += 1

            self.debug("Making Google Drive request: " + url)
            try:
                response = self._request_client.request(method, url, headers=send_headers, json=json, timeout=self.config.googleDriveTimeoutSeconds(), data=data, stream=stream)
            except ConnectionError as e:
                if self.resolver is not None:
                    self.debug("Ran into trouble reaching Google Drive's servers.  We'll use alternate DNS servers on the next attempt.")
                    self.resolver.toggle()
                if "Name or service not known" in str(e):
                    raise GoogleDnsFailure()
                if "Connection refused" in str(e) or "Failed to establish a new connection" in str(e):
                    raise GoogleCantConnect()
                if isinstance(e, ConnectTimeout):
                    raise GoogleCantConnect()
                raise e
            except DNSException as e:
                if self.resolver is not None:
                    self.debug(str(e))
                    self.debug("Ran into trouble resolving Google Drive's servers.  We'll use normal DNS servers on the next attempt.")
                    self.resolver.toggle()
                raise GoogleDnsFailure()
            except Timeout:
                raise GoogleTimeoutError()

            # Only retry 403 and 5XX error, see https://developers.google.com/drive/api/v3/manage-uploads
            if response.ok:
                break

            self.raiseForKnownErrors(response)
            if attempts > DRIVE_MAX_RETRIES:
                # out of retries, give up if it failed.
                if response.status_code == 500 or response.status_code == 503:
                    raise GoogleInternalError()
                response.raise_for_status()
            elif response.status_code == 401 and cred_retry:
                # retry with fresh creds
                self.debug("Google Drive credentials expired.  We'll retry with new ones.")
                refresh_token = True
                self.time.sleep(backoff)
                backoff *= DRIVE_EXPONENTIAL_BACKOFF
            elif response.status_code == RATE_LIMIT_EXCEEDED or response.status_code == TOO_MANY_REQUESTS or int(response.status_code / 100) == 5:
                self.error("Google Drive returned HTTP code: {0}: we'll retry in {1} seconds".format(response.status_code, backoff))
                self.time.sleep(backoff)
                # backoff exponentially, a good practice in general but also helps resolve rate limit errors.
                backoff *= DRIVE_EXPONENTIAL_BACKOFF
            else:
                break
        response.raise_for_status()
        if is_json:
            return response.json()
        else:
            return response

    def raiseForKnownErrors(self, response: Response):
        try:
            message = response.json()
        except ValueError:
            # parsing json failed, just give up
            return
        if "error" not in message:
            return
        error_obj = message["error"]
        if "errors" not in error_obj:
            return
        for error in error_obj["errors"]:
            if "reason" not in error:
                continue
            if error["reason"] == "storageQuotaExceeded":
                raise DriveQuotaExceeded()
