import os.path
import sys
import os
import tarfile
import json
import argparse
import datetime
import wsgiref.simple_server
import wsgiref.util
import http.server
import socketserver
import threading
import cherrypy
import urllib
import oauth2client
import traceback
import httplib2
import random
import string
import flask
import threading

from urllib.parse import quote
from urllib.parse import unquote
from dateutil.relativedelta import relativedelta
from datetime import timedelta
from dateutil.tz import tzutc
from dateutil.parser import parse
from datetime import datetime
from apiclient.http import MediaFileUpload
from apiclient.errors import HttpError
from pprint import pprint
from time import sleep
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage
from cherrypy import _cperror
from flask import Flask
from flask import request
from flask import send_file
from time import sleep

app = Flask(__name__)

snapshots = []
NEW_SNAPSHOT_SLEEP_SECONDS = 20

@app.route('/')
def index():
    return 'Running'

@app.route('/snapshots', methods=['GET'])
def getsnapshots():
    return formatDataResponse({'snapshots' : snapshots})


@app.route('/snapshots/new/full', methods=['POST'])
def newSnapshot():
    slug = getSlugName()
    input_json = request.get_json()
    sleep(NEW_SNAPSHOT_SLEEP_SECONDS)
    snapshots.append({
        'name' : input_json['name'],
        'date' : str(datetime.now()),
        'size' : 81694720,
        'slug' : slug
        })
    return formatDataResponse(slug)

@app.route('/snapshots/<slug>/remove', methods=['POST'])
def delete(slug):
    delete = None
    for snapshot in snapshots:
        if snapshot['slug'] == slug:
            delete = snapshot
    if not delete:
        raise Exception('no snapshot with this slug')
    snapshots.pop(snapshots.index(delete))
    return formatDataResponse("deleted")

@app.route('/snapshots/<slug>/info', methods=['GET'])
def info(slug):
    delete = None
    for snapshot in snapshots:
        if snapshot['slug'] == slug:
            return formatDataResponse(snapshot)
    raise Exception('no snapshot with this slug')

@app.route('/snapshots/<slug>/download', methods=['GET'])
def download(slug):
    delete = None
    for snapshot in snapshots:
        if snapshot['slug'] == slug:
            return send_file('C:\\Users\\home\\Desktop\\d84fa4bd.tar')
    raise Exception('no snapshot with this slug')

@app.route('/addons/self/info', methods=['GET'])
def hostInfo():
    return formatDataResponse({
    "webui": "http://[HOST]:1627/",
})


@app.route('/info', methods=['GET'])
def selfInfo():
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

@app.route("/homeassistant/api/states/snapshot_backup.state", methods=['POST'])
def setBackupState():
    print("Updated snapshot state with: {}".format(request.get_json()))
    return ""

@app.route("/homeassistant/api/states/binary_sensor.snapshots_stale", methods=['POST'])
def setBinarySensorState():
    print("Updated snapshot stale sensor with: {}".format(request.get_json()))
    return ""

@app.route("/homeassistant/api/services/persistent_notification/create", methods=['POST'])
def createNotification():
    print("Created notification with: {}".format(request.get_json()))
    return ""

@app.route("/homeassistant/api/services/persistent_notification/dismiss", methods=['POST'])
def dismissNotification():
    print("Dismissed notification with: {}".format(request.get_json()))
    return ""

@app.route('/snapshots/slugname')
def getSlugName():
        return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8)) 

def formatDataResponse(data):
    return json.dumps({'result' : 'ok', 'data' : data})

def formatErrorResponse(error):
    return {'result' : error}

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')



