#!/usr/bin/python3.7
import json
import threading

from flask import Flask, request, Response
from flask_api.status import HTTP_501_NOT_IMPLEMENTED
from typing import Any, Dict
from .testbackend import HelperTestBackend, Context, HTTPResponseError
from ..time import Time

app = Flask(__name__)
app.secret_key = "FBSVFGTYHAVPWVGFRTSCDFBZGBECRFTEX"
instances: Dict[str, HelperTestBackend] = {}
instance_lock = threading.Lock()
DEFAULTS = {
    'port': 1234,
    'client_id': None
}


class FlaskContext(Context):
    def __init__(self, request):
        self._request = request

    def json(self) -> Dict[str, Any]:
        return self._request.get_json()

    def headers(self) -> Dict[str, str]:
        return self._request.headers

    def args(self) -> Dict[str, str]:
        return self._request.args

    def params(self) -> Dict[str, str]:
        return self._request.values

    def stream(self) -> Any:
        return self._request.stream

    def translate(self, resp):
        data_type = type(resp)
        if data_type == Response:
            return resp
        if data_type == bytearray:
            return resp
        if data_type == dict:
            return json.dumps(resp, indent=4)
        if data_type == int:
            return "http error", resp
        if data_type == str:
            return resp
        else:
            # surface th error in flask
            return resp

    def call(self, callable):
        try:
            data = callable()
            return self.translate(data)
        except HTTPResponseError as e:
            return "request failed", e.error_code
        except Exception as e:
            return str(e), HTTP_501_NOT_IMPLEMENTED


def initInstance(id, time, port=1234):
    with instance_lock:
        instances[id] = HelperTestBackend(port, time)


def getContext():
    return FlaskContext(request)


def getState(context: Context):
    id = context.headers().get('Client-Identifier', "default")
    return getInstance(id)


def cleanupInstance(id):
    with instance_lock:
        del instances[id]


def getInstance(id):
    with instance_lock:
        if DEFAULTS['client_id']:
            id = DEFAULTS['client_id']
        if id not in instances:
            instances[id] = HelperTestBackend(DEFAULTS['port'], Time())
        return instances[id]


def setDefaults(port):
    DEFAULTS['port'] = port
    DEFAULTS['client_id'] = "default"


@app.route('/')
def index() -> str:
    return 'Running'


def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


@app.route('/oauth2/v4/token', methods=['POST'])
def driveAuthentication() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.driveAuthentication(context))


@app.route('/doareset', methods=['POST'])
def reset() -> Any:
    context = getContext()
    server = getState(context)
    server.reset()
    server.update(context.args())


@app.route('/uploadfile', methods=['POST'])
def uploadfile() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.uploadfile(context))


@app.route('/readfile', methods=['GET'])
def readFile() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.readFile(context))


@app.route('/updatesettings', methods=['POST'])
def updateSettings() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.updateSettings(context))


@app.route('/drive/v3/files/<id>/', methods=['GET'])
def driveGetItem(id: str) -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.driveGetItem(context, id))


@app.route('/drive/v3/files/<id>/', methods=['PATCH'])
def driveUpdate(id: str) -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.driveUpdate(context, id))


@app.route('/drive/v3/files/<id>/', methods=['DELETE'])
def driveDelete(id: str) -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.driveDelete(context, id))


@app.route('/drive/v3/files/', methods=['GET'])
def driveQuery() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.driveQuery(context))


@app.route('/drive/v3/files/', methods=['POST'])
def driveCreate() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.driveCreate(context))


@app.route('/upload/drive/v3/files/', methods=['POST'])
def driveStartUpload() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.driveStartUpload(context))


@app.route('/upload/drive/v3/files/progress/<id>', methods=['PUT'])
def driveContinueUpload(id: str) -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.driveContinueUpload(context, id))


@app.route('/snapshots', methods=['GET'])
def hassioSnapshots() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.hassioSnapshots(context))


@app.route('/supervisor/info', methods=['GET'])
def hassioSupervisorInfo() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.hassioSupervisorInfo(context))


@app.route('/homeassistant/info', methods=['GET'])
def haInfo() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.haInfo(context))


@app.route('/snapshots/new/full', methods=['POST'])
def hassioNewFullSnapshot() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.hassioNewFullSnapshot(context))


@app.route('/snapshots/new/partial', methods=['POST'])
def hassioNewPartialSnapshot() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.hassioNewPartialSnapshot(context))


@app.route('/snapshots/new/upload', methods=['GET', 'POST'])
def uploadNewSnapshot() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.uploadNewSnapshot(context))


@app.route('/snapshots/<slug>/remove', methods=['POST'])
def hassioDelete(slug: str) -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.hassioDelete(context, slug))


@app.route('/snapshots/<slug>/info', methods=['GET'])
def hassioSnapshotInfo(slug: str) -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.hassioSnapshotInfo(context, slug))


@app.route('/snapshots/<slug>/download', methods=['GET'])
def hassioSnapshotDownload(slug: str) -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.hassioSnapshotDownload(context, slug))


@app.route('/addons/self/info', methods=['GET'])
def hassioSelfInfo() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.hassioSelfInfo(context))


@app.route('/info', methods=['GET'])
def hassioInfo() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.hassioInfo(context))


@app.route('/auth', methods=['GET', 'POST'])
def hassioAuthenticate() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.hassioAuthenticate(context))


@app.route("/homeassistant/api/states/<entity>", methods=['POST'])
def haStateUpdate(entity: str) -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.haStateUpdate(context, entity))


@app.route("/homeassistant/api/services/persistent_notification/create", methods=['POST'])
def createNotification() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.createNotification(context))


@app.route("/homeassistant/api/services/persistent_notification/dismiss", methods=['POST'])
def dismissNotification() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.dismissNotification(context))


@app.route('/addons/self/options', methods=['POST'])
def hassioUpdateOptions() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.hassioUpdateOptions(context))


@app.route('/external/drivecreds/', methods=['POST', "GET"])
def driveCredGenerate() -> Any:
    context = getContext()
    server = getState(context)
    return context.call(lambda: server.driveCredsRedirect(context))


def main():
    setDefaults(2567)
    getInstance("").update({
        'snapshot_min_size': 1024 * 1024 * 3,
        'snapshot_max_size': 1024 * 1024 * 5,
        "drive_refresh_token": "test_refresh_token",
        "drive_client_id": "test_client_id",
        "drive_client_secret": "test_client_secret",
        "drive_upload_sleep": 5,
        "snapshot_wait_time": 15,
        "hassio_header": "test_header"})
    app.run(debug=False, host='0.0.0.0', threaded=True, port=2567)


if __name__ == '__main__':
    main()
