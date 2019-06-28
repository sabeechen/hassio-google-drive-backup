import random
import string
import re
import datetime
from flask import request, Response, redirect

from typing import Dict, Any, List
from oauth2client.client import OAuth2Credentials
from flask_api import status
from flask_api.status import HTTP_401_UNAUTHORIZED, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND
from threading import Lock
from time import sleep
from io import BytesIO
from abc import ABC, abstractmethod
from urllib.parse import quote
from ..time import Time
from ..tests.helpers import createSnapshotTar, parseSnapshotInfo, all_addons

mimeTypeQueryPattern = re.compile("^mimeType='.*'$")
parentsQueryPattern = re.compile("^'.*' in parents$")
bytesPattern = re.compile("^bytes \\d+-\\d+/\\d+$")
intPattern = re.compile("\\d+")
rangePattern = re.compile("bytes=\\d+-\\d+")


class HTTPResponseError(Exception):
    def __init__(self, error_code):
        self.error_code = error_code


class Context(ABC):
    @abstractmethod
    def json(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def headers(self) -> Dict[str, str]:
        pass

    @abstractmethod
    def args(self) -> Dict[str, str]:
        pass

    @abstractmethod
    def params(self) -> Dict[str, str]:
        pass

    @abstractmethod
    def stream(self) -> Any:
        pass

    @abstractmethod
    def translate(self, resp):
        pass

    @abstractmethod
    def call(self, callable):
        pass


class TestBackend(object):
    def __init__(self, port, time: Time) -> None:
        self.items: Dict[str, Any] = {}
        self.upload_info: Dict[str, Any] = {}
        self.simulate_drive_errors = False
        self.error_code = 500
        self.last_error = False
        self.snapshots: Dict[str, Any] = {}
        self.snapshot_data: Dict[str, bytearray] = {}
        self.files: Dict[str, bytearray] = {}
        self.settings: Dict[str, Any] = self.defaultSettings()
        self._snapshot_lock = Lock()
        self._settings_lock = Lock()
        self._port = port
        self._ha_error = None
        self._entities = {}
        self._attributes = {}
        self._notification = None
        self._time = time
        self._options = self.defaultOptions()
        self._username = "user"
        self._password = "pass"

    def defaultOptions(self):
        return {
            "max_snapshots_in_hassio": 4,
            "max_snapshots_in_google_drive": 4,
            "days_between_snapshots": 3,
            "use_ssl": False
        }

    def setHomeAssistantError(self, status_code):
        self._ha_error = status_code

    def getEntity(self, entity):
        return self._entities.get(entity)

    def getAttributes(self, attribute):
        return self._attributes.get(attribute)

    def getNotification(self):
        return self._notification

    def reset(self) -> None:
        with self._snapshot_lock:
            with self._settings_lock:
                self._ha_error = None
                self.items = {}
                self.upload_info = {}
                self.snapshots = {}
                self.snapshot_data = {}
                self.files = {}
                self._entities = {}
                self._attributes = {}
                self._notification = None
                self.settings = self.defaultSettings()
                self._options = self.defaultOptions()

    def getSetting(self, key):
        with self._settings_lock:
            return self.settings[key]

    def update(self, config):
        with self._settings_lock:
            self.settings.update(config)

    def defaultSettings(self):
        return {
            'snapshot_wait_time': 0,
            'snapshot_min_size': 1024 * 256 * 1,
            'snapshot_max_size': 1024 * 256 * 2,
            'ha_header': "test_header",
            "ha_version": "0.91.3",
            "ha_last_version": "0.91.2",
            "machine": "raspberrypi3",
            "ip_address": "172.30.32.1",
            "arch": "armv7",
            "image": "homeassistant/raspberrypi3-homeassistant",
            "custom": True,
            "drive_upload_error": None,
            "boot": True,
            "port": 8099,
            "ha_port": 1337,
            "ssl": False,
            "watchdog": True,
            "wait_boot": 600,
            "web_ui": "http://[HOST]:1627/",
            "ingress_url": "/index",
            "supervisor": "2.2.2",
            "homeassistant": "0.93.1",
            "hassos": "0.69.69",
            "hassio_error": None,
            "hassio_snapshot_error": None,
            "hostname": "localhost",
            "always_hard_lock": False,
            "supported_arch": [],
            "channel": "dev",
            "addon_slug": "self_slug",
            "drive_refresh_token": "",
            "drive_auth_token": "",
            "drive_client_id": "test_client_id",
            "drive_client_secret": "test_client_secret",
            "drive_upload_sleep": 0,
            "drive_all_error": None
        }

    def driveError(self) -> Any:
        if not self.simulate_drive_errors:
            return False
        if not self.last_error:
            self.last_error = True
            return self.error_code
        else:
            self.last_error = False
            return None

    def _checkDriveError(self, context):
        if self.getSetting("drive_all_error"):
            raise HTTPResponseError(self.getSetting("drive_all_error"))
        error = self.driveError()
        if error:
            raise HTTPResponseError(error)

    def _checkDriveHeaders(self, context):
        self._checkDriveError(context)
        if context.headers().get("Authorization", "") != "Bearer " + self.getSetting('drive_auth_token'):
            raise HTTPResponseError(HTTP_401_UNAUTHORIZED)

    def driveAuthentication(self, context: Context) -> Any:
        self._checkDriveError(context)
        if context.params()['client_id'] != self.getSetting('drive_client_id'):
            return HTTP_401_UNAUTHORIZED
        if context.params()['client_secret'] != self.getSetting('drive_client_secret'):
            return HTTP_401_UNAUTHORIZED
        if context.params()['refresh_token'] != self.getSetting('drive_refresh_token'):
            return status.HTTP_401_UNAUTHORIZED
        if context.params()['grant_type'] != 'refresh_token':
            return HTTP_401_UNAUTHORIZED

        new_token = self.generateId(20)
        with self._settings_lock:
            self.settings['drive_auth_token'] = new_token

        return {
            'access_token': new_token,
            'expires_in': 3600,
            'token_type': 'who_cares'
        }

    def updateSettings(self, context) -> Any:
        data = context.json()
        with self._settings_lock:
            for key in data:
                self.settings[key] = data[key]
        return "updated"

    def driveCredsRedirect(self, context: Context) -> Any:
        # build valid credentials
        creds = OAuth2Credentials(
            "",
            self.getSetting("drive_client_id"),
            self.getSetting("drive_client_secret"),
            refresh_token=self.getSetting("drive_refresh_token"),
            token_expiry="",
            token_uri="",
            user_agent="")
        url = context.args()["redirectbacktoken"] + "?creds=" + quote(creds.to_json())
        return redirect(url)

    def driveGetItem(self, context, id: str) -> Any:
        self._checkDriveHeaders(context)
        if id not in self.items:
            return HTTP_404_NOT_FOUND
        request_type = context.args().get("alt", "metadata")
        if request_type == "media":
            # return bytes
            item = self.items[id]
            if 'bytes' not in item:
                return HTTP_400_BAD_REQUEST
            return self.serve_bytes(context, item['bytes'])
        else:
            fields = context.args().get("fields", "id").split(",")
            return self.filter_fields(self.items[id], fields)

    def driveUpdate(self, context, id: str) -> Any:
        self._checkDriveHeaders(context)
        if id not in self.items:
            return HTTP_404_NOT_FOUND
        update = context.json()
        for key in update:
            if key in self.items[id] and isinstance(self.items[id][key], dict):
                self.items[id][key].update(update[key])
            else:
                self.items[id][key] = update[key]
        return ""

    def driveDelete(self, context, id: str) -> Any:
        self._checkDriveHeaders(context)
        if id not in self.items:
            return HTTP_404_NOT_FOUND
        del self.items[id]
        return ""

    def driveQuery(self, context) -> Any:
        self._checkDriveHeaders(context)
        query: str = context.args().get("q", "")
        fields = self.parseFields(context.args().get('fields', 'id'))
        if mimeTypeQueryPattern.match(query):
            ret = []
            mimeType = query[len("mimeType='"):-1]
            for item in self.items.values():
                if item.get('mimeType', '') == mimeType:
                    ret.append(self.filter_fields(item, fields))
            return {'files': ret}
        elif parentsQueryPattern.match(query):
            ret = []
            parent = query[1:-len("' in parents")]
            for item in self.items.values():
                if parent in item.get('parents', []):
                    ret.append(self.filter_fields(item, fields))
            return {'files': ret}
        elif len(query) == 0:
            ret = []
            for item in self.items.values():
                ret.append(self.filter_fields(item, fields))
            return {'files': ret}
        else:
            return HTTP_400_BAD_REQUEST

    def driveCreate(self, context) -> Any:
        self._checkDriveHeaders(context)
        id = self.generateId(30)
        item = self.formatItem(context.json(), id)
        self.items[id] = item
        return {'id': item['id']}

    def driveStartUpload(self, context) -> Any:
        self._checkDriveHeaders(context)
        if context.args().get('uploadType') != 'resumable':
            return HTTP_400_BAD_REQUEST
        mimeType = context.headers().get('X-Upload-Content-Type', None)
        if mimeType is None:
            return HTTP_400_BAD_REQUEST
        size = int(context.headers().get('X-Upload-Content-Length', -1))
        if size == -1:
            return HTTP_400_BAD_REQUEST
        metadata = context.json()
        id = self.generateId()
        self.upload_info['size'] = size
        self.upload_info['mime'] = mimeType
        self.upload_info['item'] = self.formatItem(metadata, id)
        self.upload_info['id'] = id
        self.upload_info['next_start'] = 0
        metadata['bytes'] = bytearray()
        metadata['size'] = size
        resp = Response()
        resp.headers['Location'] = "http://localhost:" + \
            str(self._port) + "/upload/drive/v3/files/progress/" + id
        return resp

    def driveContinueUpload(self, context: Context, id: str) -> Any:
        if self.getSetting("drive_upload_error") is not None:
            return self.getSetting("drive_upload_error")
        self._time.sleep(self.getSetting('drive_upload_sleep'))
        self._checkDriveHeaders(context)
        if self.upload_info.get('id', "") != id:
            return HTTP_400_BAD_REQUEST
        chunk_size = int(context.headers()['Content-Length'])
        info = context.headers()['Content-Range']
        if not bytesPattern.match(info):
            return HTTP_400_BAD_REQUEST
        numbers = intPattern.findall(info)
        start = int(numbers[0])
        end = int(numbers[1])
        total = int(numbers[2])
        if total != self.upload_info['size']:
            return HTTP_400_BAD_REQUEST
        if start != self.upload_info['next_start']:
            return HTTP_400_BAD_REQUEST
        if not (end == total - 1 or chunk_size % (256 * 1024) == 0):
            return HTTP_400_BAD_REQUEST
        if end > total - 1:
            return HTTP_400_BAD_REQUEST

        # get the chunk
        received_bytes = bytearray()
        while True:
            data = request.stream.read(1024 * 1024 * 10)
            if len(data) == 0:
                break
            else:
                received_bytes.extend(data)

        # validate the chunk
        if len(received_bytes) != chunk_size:
            return HTTP_400_BAD_REQUEST

        if len(received_bytes) != end - start + 1:
            return HTTP_400_BAD_REQUEST

        self.upload_info['item']['bytes'].extend(received_bytes)

        if len(self.upload_info['item']['bytes']) != end + 1:
            return HTTP_400_BAD_REQUEST

        if end == total - 1:
            # upload is complete, so create the item
            self.items[self.upload_info['id']] = self.upload_info['item']
            return {"id": self.upload_info['id']}
        else:
            # Return an incomplete response
            resp = Response()
            self.upload_info['next_start'] = end + 1
            resp.headers['Range'] = "bytes=0-{0}".format(end)
            resp.status_code = 308
            return resp

    def _verifyHassioHeader(self, context) -> bool:
        if self.getSetting("hassio_error") is not None:
            raise HTTPResponseError(self.getSetting("hassio_error"))
        self._verifyHeader(context, "X-HASSIO-KEY",
                           self.getSetting('ha_header'))

    def _verifyHaHeader(self, context) -> bool:
        if self._ha_error is not None:
            raise HTTPResponseError(self._ha_error)
        self._verifyHeader(context, "Authorization", "Bearer " + self.getSetting('ha_header'))

    def _verifyHeader(self, context, key: str, value: str) -> bool:
        if context.headers().get(key, None) != value:
            raise HTTPResponseError(HTTP_401_UNAUTHORIZED)

    def hassioSnapshots(self, context) -> Any:
        self._verifyHassioHeader(context)
        return self.formatDataResponse({'snapshots': list(self.snapshots.values())})

    def hassioSupervisorInfo(self, context) -> Any:
        self._verifyHassioHeader(context)
        return self.formatDataResponse(
            {
                "addons": list(all_addons).copy()
            }
        )

    def haInfo(self, context) -> Any:
        self._verifyHassioHeader(context)
        return self.formatDataResponse(
            {
                "version": self.getSetting('ha_version'),
                "last_version": self.getSetting('ha_last_version'),
                "machine": self.getSetting('machine'),
                "ip_address": self.getSetting('ip_address'),
                "arch": self.getSetting('arch'),
                "image": self.getSetting('image'),
                "custom": self.getSetting('custom'),
                "boot": self.getSetting('boot'),
                "port": self.getSetting('ha_port'),
                "ssl": self.getSetting('ssl'),
                "watchdog": self.getSetting('watchdog'),
                "wait_boot": self.getSetting('wait_boot')
            }
        )

    def hassioNewFullSnapshot(self, context) -> Any:
        input_json = context.json()
        if input_json.get('hardlock', False) or self.getSetting('always_hard_lock'):
            self._snapshot_lock.acquire()
        elif not self._snapshot_lock.acquire(blocking=False):
            return HTTP_400_BAD_REQUEST
        try:
            self._verifyHassioHeader(context)
            error = self.getSetting("hassio_snapshot_error")
            if error is not None:
                raise HTTPResponseError(error)

            seconds = int(context.args().get(
                'seconds', self.getSetting('snapshot_wait_time')))
            date = self._time.now()
            size = int(random.uniform(float(self.getSetting('snapshot_min_size')), float(
                self.getSetting('snapshot_max_size'))))
            slug = self.generateId(8)
            name = input_json['name']
            password = input_json.get('password', None)
            if seconds > 0:
                sleep(seconds)

            data = createSnapshotTar(slug, name, date, size, password=password)
            snapshot_info = parseSnapshotInfo(data)
            self.snapshots[slug] = snapshot_info
            self.snapshot_data[slug] = bytearray(data.getbuffer())
            return self.formatDataResponse({"slug": slug})
        finally:
            self._snapshot_lock.release()

    def hassioNewPartialSnapshot(self, context: Context) -> Any:
        input_json = context.json()
        if input_json.get('hardlock', False) or self.getSetting('always_hard_lock'):
            self._snapshot_lock.acquire()
        elif not self._snapshot_lock.acquire(blocking=False):
            return HTTP_400_BAD_REQUEST
        try:
            self._verifyHassioHeader(context)
            seconds = int(context.args().get(
                'seconds', self.getSetting('snapshot_wait_time')))
            date = self._time.now()
            size = int(random.uniform(float(self.getSetting('snapshot_min_size')), float(
                self.getSetting('snapshot_max_size'))))
            slug = self.generateId(8)
            name = input_json['name']
            password = input_json.get('password', None)
            if seconds > 0:
                sleep(seconds)

            data = createSnapshotTar(
                slug,
                name,
                date,
                size,
                included_folders=input_json['folders'],
                included_addons=input_json['addons'],
                password=password)
            snapshot_info = parseSnapshotInfo(data)
            self.snapshots[slug] = snapshot_info
            self.snapshot_data[slug] = bytearray(data.getbuffer())
            return self.formatDataResponse({"slug": slug})
        finally:
            self._snapshot_lock.release()

    def uploadNewSnapshot(self, context: Context) -> Any:
        self._verifyHassioHeader(context)
        try:
            received_bytes = bytearray()
            while True:
                data = request.stream.read(1024 * 1024 * 10)
                if len(data) == 0:
                    break
                else:
                    received_bytes.extend(data)
            info = parseSnapshotInfo(BytesIO(received_bytes))
            self.snapshots[info['slug']] = info
            self.snapshot_data[info['slug']] = received_bytes
            return self.formatDataResponse({"slug": info['slug']})
        except Exception as e:
            print(str(e))
            return self.formatErrorResponse("Bad snapshot")

    def hassioDelete(self, context: Context, slug: str) -> Any:
        self._verifyHassioHeader(context)
        if slug not in self.snapshots:
            return HTTP_404_NOT_FOUND
        del self.snapshots[slug]
        del self.snapshot_data[slug]
        return self.formatDataResponse("deleted")

    def hassioSnapshotInfo(self, context: Context, slug: str) -> Any:
        self._verifyHassioHeader(context)
        if slug not in self.snapshots:
            return HTTP_404_NOT_FOUND
        return self.formatDataResponse(self.snapshots[slug])

    def hassioSnapshotDownload(self, context: Context, slug: str) -> Any:
        self._verifyHassioHeader(context)
        if slug not in self.snapshot_data:
            return HTTP_404_NOT_FOUND
        return self.serve_bytes(context, self.snapshot_data[slug])

    def hassioSelfInfo(self, context: Context) -> Any:
        self._verifyHassioHeader(context)
        return self.formatDataResponse({
            "webui": self.getSetting('web_ui'),
            'ingress_url': self.getSetting('ingress_url'),
            "slug": self.getSetting('addon_slug'),
            "options": self._options
        })

    def hassioInfo(self, context: Context) -> Any:
        self._verifyHassioHeader(context)
        return self.formatDataResponse({
            "supervisor": self.getSetting('supervisor'),
            "homeassistant": self.getSetting('homeassistant'),
            "hassos": self.getSetting('hassos'),
            "hostname": self.getSetting('hostname'),
            "machine": self.getSetting('machine'),
            "arch": self.getSetting('arch'),
            "supported_arch": self.getSetting('supported_arch'),
            "channel": self.getSetting('channel')
        })

    def hassioAuthenticate(self, context: Context) -> Any:
        self._verifyHassioHeader(context)
        input_json = context.json()
        if input_json.get("username") != self._username or input_json.get("password") != self._password:
            return HTTP_400_BAD_REQUEST
        return self.formatDataResponse({})

    def haStateUpdate(self, context, entity: str) -> Any:
        self._verifyHaHeader(context)
        self._entities[entity] = context.json()['state']
        self._attributes[entity] = context.json()['attributes']
        return ""

    def createNotification(self, context: Context) -> Any:
        self._verifyHaHeader(context)
        print("Created notification with: {}".format(context.json()))
        self._notification = context.json().copy()
        return ""

    def dismissNotification(self, context: Context) -> Any:
        self._verifyHaHeader(context)
        print("Dismissed notification with: {}".format(context.json()))
        self._notification = None
        return ""

    def hassioUpdateOptions(self, context: Context) -> Any:
        self._verifyHassioHeader(context)
        self._options = context.json()['options'].copy()
        return self.formatDataResponse({})

    def uploadfile(self, context) -> Any:
        name: str = str(context.args().get("name"))
        data = bytearray()
        while True:
            chunk = context.stream().read(1024)
            if len(chunk) > 0:
                data.extend(chunk)
            else:
                break
        self.files[name] = data
        return ""

    def readFile(self, context) -> Any:
        return self.serve_bytes(context, self.files[str(context.args().get("name"))])

    def formatItem(self, base, id):
        base['capabilities'] = {'canAddChildren': True,
                                'canListChildren': True, 'canDeleteChildren': True}
        base['trashed'] = False
        base['id'] = id
        base['modifiedTime'] = self.timeToRfc3339String(self._time.now())
        return base

    def formatDataResponse(self, data: Any) -> str:
        return {'result': 'ok', 'data': data}

    def formatErrorResponse(self, error: str) -> str:
        return {'result': error}

    def generateId(self, length: int = 30) -> Any:
        return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))

    def timeToRfc3339String(self, time: datetime.datetime) -> Any:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ")

    def parseFields(self, source: str) -> List[str]:
        fields = []
        for field in source.split(","):
            if field.startswith("files("):
                fields.append(field[6:])
            elif field.endswith(")"):
                fields.append(field[:-1])
            else:
                fields.append(field)
        return fields

    def serve_bytes(self, context: Context, bytes: bytearray) -> Any:
        if "Range" in context.headers():
            # Do range request
            if not rangePattern.match(context.headers()['Range']):
                return HTTP_400_BAD_REQUEST

            numbers = intPattern.findall(request.headers['Range'])
            start = int(numbers[0])
            end = int(numbers[1])

            if start < 0:
                return HTTP_400_BAD_REQUEST
            if start > end:
                return HTTP_400_BAD_REQUEST
            if end > len(bytes) - 1:
                return HTTP_400_BAD_REQUEST
            resp = Response()
            resp.headers['Content-Range'] = "bytes {0}-{1}/{2}".format(
                start, end, len(bytes))
            resp.status_code = 206
            resp.data = bytes[start:end + 1]
            return resp
        else:
            return bytes

    def filter_fields(self, item: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
        ret = {}
        for field in fields:
            if field in item:
                ret[field] = item[field]
        return ret
