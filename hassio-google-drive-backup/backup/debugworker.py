import json
import requests

from .worker import Worker
from .time import Time
from .globalinfo import GlobalInfo
from .config import Config
from datetime import timedelta, datetime
from .helpers import getPingInfo, formatException
from .exceptions import KnownError
from urllib.parse import quote


class DebugWorker(Worker):
    def __init__(self, time: Time, info: GlobalInfo, config: Config):
        super().__init__("Debug Worker", self.doWork, time, interval=10)
        self.time = time
        self._info = info
        self.config = config

        self.last_dns_update = None
        self.dns_info = None

        self.last_sent_error = None
        self.last_sent_error_time = None

    def doWork(self):
        if not self.last_dns_update or self.time.now() > self.last_dns_update + timedelta(hours=12):
            self.updateDns()
        if self.config.sendErrorReports():
            try:
                self.maybeSendErrorReport()
            except Exception as e:
                # just eat the error
                pass

    def maybeSendErrorReport(self):
        error = self._info._last_error
        if error is not None:
            if isinstance(error, KnownError):
                error = error.code()
            else:
                error = formatException(error)
        if error != self.last_sent_error:
            self.last_sent_error = error
            if error is not None:
                package = self.buildErrorReport(error)
            else:
                package = self.buildClearReport()
            self.info("Sending error report (see settings to disable)")
            url: str = "https://philosophyofpen.com/login/error.py?error={0}&version=1".format(quote(json.dumps(package, indent=4, sort_keys=True)))
            requests.get(url)

    def updateDns(self):
        self.last_dns_update = self.time.now()
        try:
            self.dns_info = getPingInfo(["www.googleapis.com"])
            self._info.setDnsInfo(self.dns_info)
        except Exception as e:
            self.dns_info = formatException(e)

    def buildErrorReport(self, error):
        # Someday: Get the supervisor logs
        # Someday: Get the add-on logs
        report = {}
        report['debug'] = self._info.debug
        report['google_dns'] = self.dns_info
        report['error'] = error
        report['client'] = self.config.clientIdentifier()
        report['upload'] = {
            'count': self._info._uploads,
            'last_size': self._info._last_upload_size,
            'last_attempt': self.formatDate(self._info._last_upload)
        }
        report['syncs'] = {
            'count': self._info._syncs,
            'successes': self._info._successes,
            'failures': self._info._failures,
            'last_start': self.formatDate(self._info._last_sync_start),
            'last_failure': self.formatDate(self._info._last_failure_time)
        }
        report['now'] = self.formatDate(self.time.now())
        return report

    def buildClearReport(self):
        report = {}
        report['client'] = self.config.clientIdentifier()
        report['now'] = self.formatDate(self.time.now())
        return report

    def formatDate(self, date: datetime):
        if date is None:
            return "Never"
        else:
            return date.isoformat()
