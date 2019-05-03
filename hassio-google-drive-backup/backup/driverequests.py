from .logbase import LogBase
from .thumbnail import THUMBNAIL_IMAGE
from .seekablerequest import SeekableRequest
from .responsestream import IteratorByteStream
from requests import request
from urllib.parse import urlencode
import httplib2
import json

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
PAGE_SIZE = 100
CHUNK_SIZE = 5 * 262144


class DriveRequests(LogBase):
    def __init__(self, creds, cred_storage):
        self.creds = creds
        self.cred_storage = cred_storage

    def _getHeaders(self):
        # TODO: this shoudl not use httplib2
        if self.creds.access_token_expired:
            self.creds.refresh(httplib2.Http())
            self.cred_storage.put(self.creds)
        return {
            "Authorization": "Bearer " + json.loads(self.creds.to_json())['access_token']
        }

    def get(self, id):
        q = {
            "fields": SELECT_FIELDS
        }
        return self.retryRequest("GET", URL_FILES + id + "/?" + urlencode(q), is_json=True)

    def download(self, id, length_bytes):
        iterator = self.retryRequest("GET", URL_FILES + id, stream=True).iter_content(chunk_size=CHUNK_SIZE)
        return IteratorByteStream(iterator, length_bytes)

    def downloadSeekable(self, id, length_bytes):
        return SeekableRequest(URL_FILES + id, self._getHeaders(), length_bytes)

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
                yield partial.json()
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

    def retryRequest(self, method, url, headers=None, json=None, data=None, is_json=False, stream=False):
        # TODO: This should *actually* retry on retryable errors
        send_headers = self._getHeaders()
        if headers:
            send_headers.update(headers)
        response = request(method, url, headers=send_headers, json=json, timeout=(30, 30), data=data, stream=stream)
        response.raise_for_status()
        if is_json:
            return response.json()
        else:
            return response
        # TODO: make timeout configurable
