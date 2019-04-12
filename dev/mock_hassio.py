#!/usr/bin/python3.7
import os.path
import json
import random
import string

from dateutil.tz import tzutc
from dateutil.parser import parse
from datetime import datetime
from pprint import pprint
from time import sleep
from flask import Flask
from flask import request
from flask import send_file
from typing import List, Dict, Optional, Any
from threading import Lock
from flask_api import status  # type: ignore
from shutil import copyfile

app = Flask(__name__)

snapshots: List[Dict[Any, Any]] = []
NEW_SNAPSHOT_SLEEP_SECONDS = 30
TAR_FILE = "sample_tar.tar"
BACKUP_DIR = "backup"
snapshotting = False
snapshot_lock: Lock = Lock()


@app.route('/')
def index() -> str:
    return 'Running'


@app.route('/snapshots', methods=['GET'])
def getsnapshots() -> str:
    return formatDataResponse({'snapshots': snapshots})


@app.route('/snapshots/new/full', methods=['POST'])
def newSnapshot() -> Any:
    pprint(request.args)
    seconds = NEW_SNAPSHOT_SLEEP_SECONDS
    if 'seconds' in request.args.keys():  # type: ignore
        seconds = int(request.args['seconds'])

    date: Optional[datetime] = None
    if 'date' in request.args.keys():  # type: ignore
        date = parse(request.args['date'], tzinfos=tzutc)
    else:
        date = datetime.now(tzutc())
    if not snapshot_lock.acquire(blocking=False):
        return "", status.HTTP_400_BAD_REQUEST
    try:
        slug = getSlugName()
        input_json = request.get_json()
        name = input_json['name']
        sleep(seconds)
        snapshot_info = {
            'name': name,
            'date': str(date.isoformat()),
            'size': os.path.getsize(TAR_FILE) / 1024.0 / 1024.0,
            'slug': slug,
            'version': 'dev',
            'type': 'full'
        }
        if 'password' in input_json:
            snapshot_info['protected'] = True
        else:
            snapshot_info['protected'] = False
        snapshots.append(snapshot_info)
        copyfile(TAR_FILE, BACKUP_DIR + "/" + slug + ".tar")
        return formatDataResponse({"slug": slug})
    finally:
        snapshot_lock.release()


@app.route('/snapshots/<slug>/remove', methods=['POST'])
def delete(slug: str) -> str:
    delete: Optional[Dict[Any, Any]] = None
    for snapshot in snapshots:
        if snapshot['slug'] == slug:
            delete = snapshot
    if not delete:
        raise Exception('no snapshot with this slug')
    snapshots.pop(snapshots.index(delete))
    return formatDataResponse("deleted")


@app.route('/snapshots/<slug>/info', methods=['GET'])
def info(slug: str) -> str:
    for snapshot in snapshots:
        if snapshot['slug'] == slug:
            return formatDataResponse(snapshot)
    raise Exception('no snapshot with this slug')


@app.route('/snapshots/<slug>/download', methods=['GET'])
def download(slug: str) -> Any:
    for snapshot in snapshots:
        if snapshot['slug'] == slug:
            return send_file(TAR_FILE)
    raise Exception('no snapshot with this slug')


@app.route('/addons/self/info', methods=['GET'])
def hostInfo() -> str:
    return formatDataResponse({
        "webui": "http://[HOST]:1627/"
    })


@app.route('/info', methods=['GET'])
def selfInfo() -> str:
    return formatDataResponse({
        "supervisor": "version",
        "homeassistant": "version",
        "hassos": "null|version",
        "hostname": "localhost",
        "machine": "type",
        "arch": "arch",
        "supported_arch": [],
        "channel": "dev"
    })


@app.route('/auth', methods=['GET', 'POST'])
def auth() -> str:
    return formatDataResponse({})


@app.route("/homeassistant/api/states/sensor.snapshot_backup", methods=['POST'])
def setBackupState() -> str:
    print("Updated snapshot state with: {}".format(request.get_json()))
    return ""


@app.route("/homeassistant/api/states/binary_sensor.snapshots_stale", methods=['POST'])
def setBinarySensorState() -> str:
    print("Updated snapshot stale sensor with: {}".format(request.get_json()))
    return ""


@app.route("/homeassistant/api/services/persistent_notification/create", methods=['POST'])
def createNotification() -> str:
    print("Created notification with: {}".format(request.get_json()))
    return ""


@app.route("/homeassistant/api/services/persistent_notification/dismiss", methods=['POST'])
def dismissNotification() -> str:
    print("Dismissed notification with: {}".format(request.get_json()))
    return ""


@app.route('/snapshots/slugname')
def getSlugName() -> str:
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))


@app.route('/addons/self/options', methods=['POST'])
def setOptions() -> str:
    pprint(request.get_json())
    with open("data/options.json", "w") as file:
        file.write(json.dumps(request.get_json()['options'], indent=4))
    return formatDataResponse({})


def formatDataResponse(data: Any) -> str:
    return json.dumps({'result': 'ok', 'data': data}, sort_keys=True, indent=4)


def formatErrorResponse(error: str) -> Dict[str, str]:
    return {'result': error}


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', threaded=True)
