from .logbase import LogBase
from .seekablerequest import SeekableRequest
from .responsestream import IteratorByteStream
from .config import Config
from .time import Time
from datetime import datetime, timedelta
from requests import request
from urllib.parse import urlencode
from time import sleep
import json
import os
from oauth2client.client import Credentials

MIME_TYPE = "application/tar"
FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'
FOLDER_NAME = 'Hass.io Snapshots'
DRIVE_VERSION = "v3"
DRIVE_SERVICE = "drive"

SELECT_FIELDS = "id,name,appProperties,size,trashed,mimeType,modifiedTime,capabilities"
THUMBNAIL_MIME_TYPE = "image/png"
QUERY_FIELDS = "nextPageToken,files(" + SELECT_FIELDS + ")"
CREATE_FIELDS = SELECT_FIELDS
URL_FILES = "https://www.googleapis.com/drive/v3/files/"
URL_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"
URL_AUTH = "https://www.googleapis.com/oauth2/v4/token"
PAGE_SIZE = 100
CHUNK_SIZE = 5 * 262144

# Defines the retry strategy for calls made to Drive
# max # of time to retry and call to Drive
DRIVE_MAX_RETRIES: int = 5
# The initial backoff for drive retries.
DRIVE_RETRY_INITIAL_SECONDS: int = 2
# How uch longer to wait for each Drive service call (Exponential backoff)
DRIVE_EXPONENTIAL_BACKOFF: int = 2


class DriveRequests(LogBase):
    def __init__(self, config: Config, time: Time):
        self.config = config
        self.time = time
        self.cred_expiration = None
        self.cred_bearer = None
        self.tryLoadCredentials()
        self.debug = False

    def _getHeaders(self, refresh=False):
        return {
            "Authorization": "Bearer " + self.getToken(refresh=refresh)
        }

    def enabled(self):
        return self.cred_bearer is not None

    def tryLoadCredentials(self):
        if os.path.isfile(self.config.credentialsFilePath()):
            with open(self.config.credentialsFilePath()) as f:
                loaded = json.load(f)
                self.cred_bearer = loaded['access_token']
                self.cred_expiration = self.time.parse(loaded['token_expiry'])
                return
        self.cred_bearer = None
        self.cred_expiration = None

    def saveCredentials(self, creds: Credentials):
        parsed = json.loads(creds.to_json())
        with open(self.config.credentialsFilePath(), "w") as f:
            json.dump(parsed, f)
        self.cred_bearer = parsed['access_token']
        self.cred_expiration = self.time.parse(parsed['token_expiry'])

    def getToken(self, refresh=False):
        if (self.cred_expiration or self.time.now() + timedelta(minutes=1) < self.cred_expiration) and not refresh:
            return self.cred_bearer
        required = [
            'token_expiry',
            'access_token',
            'refresh_token',
            'scopes',
            'client_id',
            'client_secret'
        ]
        with open(self.config.credentialsFilePath()) as f:
            loaded = json.load(f)
        for key in required:
            if key not in loaded:
                raise Exception("Required key {key} wasn't present in Google Drive your credentials.")
        if len(loaded['scopes']) == 0:
            raise Exception("An authenticated scope wasn't present in Google Drive your credentials.")

        required = [
            'access_token',
            'expires_in',
            'scope',
            'token_type'
        ]
        for key in required:
            if key not in loaded['token_response']:
                raise Exception("Required key {key} wasn't present in Google Drive your credentials token response.")

        # refresh the credentials
        data = 'client_id={0}&client_secret={1}&refresh_token={2}&grant_type=refresh_token'.format(loaded['client_id'], loaded['client_secret'], loaded['refresh_token'])
        self.info("Requesting refreshed Google Drive credentials")
        resp = self.retryRequest("POST", URL_AUTH, is_json=True, data=data, auth_headers={"Content-Type": "application/x-www-form-urlencoded"}, cred_retry=False)
        required = [
            'access_token',
            'expires_in',
            'token_type'
        ]
        for key in required:
            if key not in resp:
                raise Exception("Required key {key} wasn't present in Google Drive's authentication response.")
        loaded['access_token'] = resp['access_token']
        expiration: datetime = self.time.now() + timedelta(seconds=resp['expires_in'])
        loaded['token_expiry'] = expiration.strftime("%Y-%m-%dT%H:%M:%SZ")
        loaded['token_response'] = resp
        with open(self.config.credentialsFilePath(), "w") as f:
            json.dump(loaded, f)
        self.cred_bearer = loaded['access_token']
        self.cred_expiration = expiration
        return loaded['access_token']

    def get(self, id):
        q = {
            "fields": SELECT_FIELDS
        }
        return self.retryRequest("GET", URL_FILES + id + "/?" + urlencode(q), is_json=True)

    def download(self, id, length_bytes):
        return SeekableRequest(URL_FILES + id + "?alt=media", self._getHeaders(), length_bytes)

    def query(self, query):
        # TODO: page size should be configurable
        continuation = None
        while True:
            q = {
                "q": query,
                "fields": QUERY_FIELDS,
                "pageSize": PAGE_SIZE
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
        self.retryRequest("PATCH", URL_FILES + id, json=update_metadata)

    def delete(self, id):
        self.retryRequest("DELETE", URL_FILES + id)

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
        if 'Location' not in initial.headers:
            raise Exception("Response from Google Drive included no upload location information")
        location = initial.headers['Location']
        while True:
            start = stream.tell()
            data = stream.read(CHUNK_SIZE)
            if len(data) == 0:
                raise Exception("Snapshot file stream ended prematurely while uploading to Google Drive")
            headers = {
                "Content-Length": str(len(data)),
                "Content-Range": "bytes {0}-{1}/{2}".format(start, start + len(data) - 1, total_size)
            }
            partial = self.retryRequest("PUT", location, headers=headers, data=data)
            yield float(start + len(data)) / float(total_size)
            if partial.status_code == 200 or partial.status_code == 201:
                # upload completed, return the object json
                yield self.get(partial.json()['id'])
                break
            elif partial.status_code == 308:
                # upload partially complete, seek to the new requested position
                if "Range" not in partial.headers or not partial.headers["Range"].startswith("bytes=0-"):
                    raise Exception("Invalid range header from Google while uploading a snapshot to Google Drive.")
                try:
                    position = int(partial.headers["Range"][len("bytes=0-"):])
                    stream.seek(position + 1)
                except ValueError:
                    raise Exception("Invalid range header from Google while uploading a snapshot to Google Drive: " + partial.headers["Range"])
            else:
                raise Exception("Unexpected HTTP response while uploading a snapshot to Google Drive: " + str(partial.status_code))

    def createFolder(self, metadata):
        return self.retryRequest("POST", URL_FILES, is_json=True, json=metadata)

    def retryRequest(self, method, url, auth_headers=None, headers=None, json=None, data=None, is_json=False, stream=False, cred_retry=True):
        backoff = DRIVE_RETRY_INITIAL_SECONDS
        attempts = 0
        refresh_token = False
        while True:
            if auth_headers is not None:
                send_headers = auth_headers.copy()
            else:
                send_headers = self._getHeaders(refresh=refresh_token)
                refresh_token = False
            if headers:
                send_headers.update(headers)
            attempts += 1
            # TODO: make timeout configurable
            response = request(method, url, headers=send_headers, json=json, timeout=(30, 30), data=data, stream=stream)

            # Only retry 403 and 5XX error, see https://developers.google.com/drive/api/v3/manage-uploads
            if response.ok:
                break
            elif attempts > DRIVE_MAX_RETRIES:
                # out of retries give up.
                response.raise_for_status()
            elif response.status_code == 401 and cred_retry:
                # retry with fresh creds
                self.info("Google Drive credentials expired.  We'll retry with new ones.")
                refresh_token = True
                sleep(backoff)
                backoff *= DRIVE_EXPONENTIAL_BACKOFF
            elif response.status_code == 403 or int(response.status_code / 100) == 5:
                self.error("Google Drive returned HTTP code: {0}: we'll retry in {1} seconds".format(response.status_code, backoff))
                sleep(backoff)
                # backoff exponentially, a good practice in general but also helps resolve rate limit errors.
                backoff *= DRIVE_EXPONENTIAL_BACKOFF
            else:
                break

        response.raise_for_status()
        if is_json:
            return response.json()
        else:
            return response
