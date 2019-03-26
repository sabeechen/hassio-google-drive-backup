import os.path
import sys
import os
import json
import requests
import datetime
import threading

from datetime import datetime
from pprint import pprint
from time import sleep
from oauth2client.client import HttpAccessTokenRefreshError
from snapshots import HASnapshot
from snapshots import Snapshot
from helpers import nowutc
from helpers import formatException

# Secodns to wait after starting a snapshot before we consider it successful.
SNAPSHOT_FASTFAIL_SECOND = 10

HEADERS = {"X-HASSIO-KEY": os.environ.get("HASSIO_TOKEN")}

HEADERS_HA = {'Authorization': 'Bearer ' + str(os.environ.get("HASSIO_TOKEN"))}

NOTIFICATION_ID = "backup_broken"

class Hassio(object):
    """
    Stores logic for interacting with the Hass.io add-on API
    """
    def __init__(self, config):
        self.config = config
        self.wrapper = {'snapshot': None}
        self.snapshot_thread = threading.Thread(target = self._getSnapshot)
        self.snapshot_thread.daemon = True
        self.pending_snapshot = None
        self.pending_snapshot_error = None
        self.lock = threading.Lock()

    def _getSnapshot(self):
        try:
            self.pending_snapshot_error = None
            now_local = datetime.now()
            now_utc = nowutc()
            backup_name = "Full Snapshot {0}-{1:02d}-{2:02d} {3:02d}:{4:02d}:{5:02d}".format(
                                now_local.year, 
                                now_local.month, 
                                now_local.day, 
                                now_local.hour,
                                now_local.minute,
                                now_local.second)
            snapshot_url = "{0}snapshots/new/full".format(self.config.hassioBaseUrl())
            self.pending_snapshot = Snapshot(None)
            self.pending_snapshot.setPending(backup_name, now_utc)
            return_info = self._postHassioData(snapshot_url, {'name': backup_name})
            self.pending_snapshot.endPending(return_info['slug'])
        except Exception as e:
            try:
                self.lock.acquire()
                self.pending_snapshot.pendingFailed()
                self.pending_snapshot_error = e
                self.pending_snapshot = None
            finally:
                self.lock.release()

    def auth(self, user, password):
         self._postHassioData("{}auth".format(self.config.hassioBaseUrl()), {"username": user, "password": password})

    
    def newSnapshot(self):
        try:
            self.lock.acquire()
            if not self.snapshot_thread is None and self.snapshot_thread.is_alive():
                raise Exception("A snapshot is already in progress")
            self.snapshot_thread = threading.Thread(target = self._getSnapshot)
            self.snapshot_thread.start()
        finally:
            self.lock.release()
        self.snapshot_thread.join(timeout = SNAPSHOT_FASTFAIL_SECOND)
        try:
            self.lock.acquire()
            if not self.pending_snapshot_error is None:
                raise self.pending_snapshot_error # pylint: disable-msg=E0702
            elif not self.pending_snapshot is None:
                return self.pending_snapshot
            else:
                raise Exception("Unexpected circumstances, everything is null")
        finally:
            self.lock.release()

    def deleteSnapshot(self, snapshot) :
        delete_url = "{0}snapshots/{1}/remove".format(self.config.hassioBaseUrl(), snapshot.slug())
        self._postHassioData(delete_url, {})
        snapshot.ha = None

    def readSnapshots(self):
        snapshots = []
        snapshot_list = self._getHassioData(self.config.hassioBaseUrl() + "snapshots")
        for snapshot in snapshot_list['snapshots']:
            snapshot_details = self._getHassioData("{0}snapshots/{1}/info".format(self.config.hassioBaseUrl(), snapshot['slug']))
            snapshots.append(HASnapshot(snapshot_details))

        snapshots.sort(key = lambda x : x.date())
        return snapshots

    def readAddonInfo(self):    
        return self._getHassioData(self.config.hassioBaseUrl() + "addons/self/info")

    def readHostInfo(self):    
        return self._getHassioData(self.config.hassioBaseUrl() + "info")

    def downloadUrl(self, snapshot):
        return "{0}snapshots/{1}/download".format(self.config.hassioBaseUrl(), snapshot.slug())

    def _validateHassioReply(self, resp):
        if not resp.ok:
            print("Hass.io responded with: {0} {1}".format(resp, resp.text))
            raise Exception('Request to Hassio failed, HTTP error: {0} Message: {1}'.format(resp, resp.text))
        details = resp.json()
        if self.config.verbose():
            print("Hassio said: " + str(details))
        if not "result" in details or not "data" in details or details["result"] != "ok":
            if "result" in details:
                raise Exception("Hassio said: " + details["result"])
            else:
                raise Exception("Malformed response from Hassio: " + str(details))
        return details["data"]

    # Should handle both post and get
    def _getHassioData(self, url):
        if self.config.verbose():
            print("Making Hassio request: " + url)
        response = requests.get(url, headers=HEADERS)
        return self._validateHassioReply(response)

    def _postHassioData(self, url, json_data):
        if self.config.verbose():
            print("Making Hassio request: " + url)
        response = requests.post(url, headers=HEADERS, json = json_data)
        return self._validateHassioReply(response)

    def _postHaData(self, path, data):
        headers = None
        if len(self.config.haBearer()) > 0:
            headers = {'Authorization': 'Bearer ' + self.config.haBearer()}
        else:
            headers = HEADERS_HA
        try:
            if self.config.verbose():
                print("Making Ha request: " + self.config.haBaseUrl() + path)
                print("With Data: {0}".format(data))
            requests.post(self.config.haBaseUrl() + path, headers=headers, json = data).raise_for_status()
        except Exception as e:
            print(formatException(e))


    def sendNotification(self, title, message):
        data = {
            "title" : title,
            "message" : message,
            "notification_id" : NOTIFICATION_ID
        }
        self._postHaData("services/persistent_notification/create", data)

    def dismissNotification(self):
        data = {
            "notification_id" : NOTIFICATION_ID
        }
        self._postHaData("services/persistent_notification/dismiss", data)

    def updateSnapshotStaleSensor(self, state):
        data = {
            "state": state,
            "attributes":{
                "friendly_name":"Snapshots Stale",
                "other":"data"
                }
        } 
        self._postHaData("states/binary_sensor.snapshots_stale", data)

    def updateSnapshotsSensor(self, state, snapshots):
        data = {
            "state": state,
            "attributes": {
                "friendly_name":"Snapshot State",
                "last_snapshot": str(max(snapshots, key=lambda s:s.date(), default="")),
                "spanshots_in_google_drive": len(list(filter(lambda s:s.isInDrive(), snapshots))),
                "spanshots_in_hassio": len(list(filter(lambda s:s.isInHA(), snapshots))),
                "snapshots": list(map(lambda s: {"name":s.name(), "date":str(s.date()), "state":s.status()}, snapshots))
            }
        }
        self._postHaData("states/snapshot_backup.state", data)

