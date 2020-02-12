import asyncio
import json
import socket
import subprocess
from datetime import datetime, timedelta
from os.path import abspath, join
from urllib.parse import quote

from aiohttp import ClientSession
from injector import inject, singleton

from ..config import Config, Setting
from ..exceptions import KnownError
from ..util import GlobalInfo, Resolver
from ..time import Time
from .worker import Worker


@singleton
class DebugWorker(Worker):
    @inject
    def __init__(self, time: Time, info: GlobalInfo, config: Config, resolver: Resolver, session: ClientSession):
        super().__init__("Debug Worker", self.doWork, time, interval=10)
        self.time = time
        self._info = info
        self.config = config

        self.last_dns_update = None
        self.dns_info = None

        self.last_sent_error = None
        self.last_sent_error_time = None
        self.resolver = resolver
        self.session = session
        self.version = None

    async def doWork(self):
        if self.version is None:
            with open(abspath(join(__file__, "..", "..", "..", "config.json"))) as f:
                addon_config = json.load(f)
                self.version = addon_config['version']
        if not self.last_dns_update or self.time.now() > self.last_dns_update + timedelta(hours=12):
            await self.updateDns()
        if self.config.get(Setting.SEND_ERROR_REPORTS):
            try:
                await self.maybeSendErrorReport()
            except Exception:
                # just eat the error
                pass

    async def maybeSendErrorReport(self):
        error = self._info._last_error
        if error is not None:
            if isinstance(error, KnownError):
                error = error.code()
            else:
                error = self.formatException(error)
        if error != self.last_sent_error:
            self.last_sent_error = error
            if error is not None:
                self.last_sent_error_time = self.time.now()
                package = self.buildErrorReport(error)
            else:
                package = self.buildClearReport()
            self.info("Sending error report (see settings to disable)")
            url: str = self.config.get(Setting.ERROR_REPORT_URL) + "?error={0}&version=1".format(
                quote(json.dumps(package, indent=4, sort_keys=True)))
            async with self.session.get(url):
                pass

    async def updateDns(self):
        self.last_dns_update = self.time.now()
        try:
            # Resolve google's addresses
            # TODO: maybe this should use the "default" resolver rather than the custom one?.
            self.dns_info = await self.getPingInfo()
            self._info.setDnsInfo(self.dns_info)
        except Exception as e:
            self.dns_info = self.formatException(e)

    def buildErrorReport(self, error):
        # Someday: Get the supervisor logs
        # Someday: Get the add-on logs
        report = {}
        report['version'] = self.version
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
        duration = self.time.now() - self.last_sent_error_time
        report = {
            'client': self.config.clientIdentifier(),
            'now': self.formatDate(self.time.now()),
            'duration': str(duration)
        }
        return report

    def formatDate(self, date: datetime):
        if date is None:
            return "Never"
        else:
            return date.isoformat()

    async def getPingInfo(self):
        who = self.config.get(Setting.DRIVE_HOST_NAME)
        ips = await self.resolve(who)
        pings = {who: {}}
        for ip in ips:
            pings[who][ip] = "Unknown"
        command = "fping -t 5000 " + " ".join(ips)

        # fping each server
        process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        stdout_data, stderr_data = await process.communicate()

        for line in stdout_data.decode().split("\n"):
            for host in pings.keys():
                for address in pings[host].keys():
                    if line.startswith(address):
                        response = line[len(address):].strip()
                        if response.startswith(":"):
                            response = response[2:].strip()
                        if response.startswith("is"):
                            response = response[3:].strip()
                        pings[host][address] = response
        return pings

    async def resolve(self, who: str):
        try:
            ret = [who]
            addresses = await self.resolver.resolve(who, 443, socket.AF_INET)
            for address in addresses:
                ret.append(address['host'])
            return ret
        except Exception:
            return [who]
