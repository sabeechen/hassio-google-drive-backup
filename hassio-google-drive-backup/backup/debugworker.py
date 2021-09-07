import asyncio
import socket
import subprocess
from datetime import datetime, timedelta

from aiohttp import ClientSession, ClientTimeout
from injector import inject, singleton

from backup.config import Config, Setting, VERSION, _DEFAULTS, PRIVATE
from backup.exceptions import KnownError
from backup.util import GlobalInfo, Resolver
from backup.time import Time
from backup.worker import Worker
from backup.logger import getLogger, getHistory
from backup.ha import HaRequests, HaSource
from backup.model import Coordinator
from yarl import URL

logger = getLogger(__name__)
ERROR_LOG_LENGTH = 30


@singleton
class DebugWorker(Worker):
    @inject
    def __init__(self, time: Time, info: GlobalInfo, config: Config, resolver: Resolver, session: ClientSession, ha: HaRequests, coord: Coordinator, ha_source: HaSource):
        super().__init__("Debug Worker", self.doWork, time, interval=10)
        self.time = time
        self._info = info
        self.config = config
        self.ha = ha
        self.ha_source = ha_source
        self.coord = coord

        self.last_dns_update = None
        self.dns_info = None

        self.last_sent_error = None
        self.last_sent_error_time = None
        self._health = None
        self.resolver = resolver
        self.session = session
        self._last_server_check = None
        self._last_server_refresh = timedelta(days=1)

    async def doWork(self):
        if not self.last_dns_update or self.time.now() > self.last_dns_update + timedelta(hours=12):
            await self.updateDns()
        if not self._last_server_check or self.time.now() > self._last_server_check + self._last_server_refresh:
            await self.updateHealthCheck()
        if self.config.get(Setting.SEND_ERROR_REPORTS):
            try:
                await self.maybeSendErrorReport()
            except Exception:
                pass

    # Once per day, query the health endpoint of the token server to see who is up.
    # This checks for broadcast messages for all users and also finds which token
    # servers are available.
    async def updateHealthCheck(self):
        headers = {
            'client': self.config.clientIdentifier(),
            'addon_version': VERSION
        }
        self._last_server_check = self.time.now()
        for host in self.config.getTokenServers():
            url = host.with_path("/health")
            try:
                async with self.session.get(url, headers=headers, timeout=ClientTimeout(total=10)) as resp:
                    resp.raise_for_status()
                    self._health = await resp.json()
                    self._last_server_refresh = timedelta(days=1)
                    return
            except:  # noqa: E722
                # ignore any error and just try a different endpoint
                pass

        # no good token host could be found, so reset it to the default and check again sooner.
        self._last_server_refresh = timedelta(minutes=1)

    async def maybeSendErrorReport(self):
        error = self._info._last_error
        if error is not None:
            if isinstance(error, KnownError):
                error = error.code()
            else:
                error = logger.formatException(error)
        if error != self.last_sent_error:
            self.last_sent_error = error
            if error is not None:
                self.last_sent_error_time = self.time.now()
                package = await self.buildErrorReport(error)
            else:
                package = self.buildClearReport()
            logger.info("Sending error report (see settings to disable)")
            headers = {
                'client': self.config.clientIdentifier(),
                'addon_version': VERSION
            }
            url = URL(self.config.get(Setting.AUTHORIZATION_HOST)).with_path("/logerror")
            async with self.session.post(url, headers=headers, json=package):
                pass

    async def updateDns(self):
        self.last_dns_update = self.time.now()
        try:
            # Resolve google's addresses
            self.dns_info = await self.getPingInfo()
            self._info.setDnsInfo(self.dns_info)
        except Exception as e:
            self.dns_info = logger.formatException(e)

    async def buildErrorReport(self, error):
        config_special = {}
        for setting in Setting:
            if self.config.get(setting) != _DEFAULTS[setting]:
                if setting in PRIVATE:
                    config_special[str(setting)] = "REDACTED"
                else:
                    config_special[str(setting)] = self.config.get(setting)
        report = {}
        report['config'] = config_special
        report['time'] = self.formatDate(self.time.now())
        report['start_time'] = self.formatDate(self._info._start_time)
        report['addon_version'] = VERSION
        report['failure_time'] = self.formatDate(self._info._last_failure_time)
        report['failure_count'] = self._info._failures
        report['sync_last_start'] = self.formatDate(self._info._last_sync_start)
        report['sync_count'] = self._info._syncs
        report['sync_success_count'] = self._info._successes
        report['sync_last_success'] = self.formatDate(self._info._last_sync_success)
        report['upload_count'] = self._info._uploads
        report['upload_last_size'] = self._info._last_upload_size
        report['upload_last_attempt'] = self.formatDate(self._info._last_upload)

        report['debug'] = self._info.debug
        report['version'] = VERSION
        report['error'] = error
        report['client'] = self.config.clientIdentifier()

        if self.ha_source.isInitialized():
            report["super_version"] = self.ha_source.host_info.get('supervisor', "None")
            report["hassos_version"] = self.ha_source.host_info.get('hassos', "None")
            report["docker_version"] = self.ha_source.host_info.get('docker', "None")
            report["machine"] = self.ha_source.host_info.get('machine', "None")
            report["supervisor_channel"] = self.ha_source.host_info.get('channel', "None")
            report["arch"] = self.ha_source.super_info.get('arch', "None")
            report["timezone"] = self.ha_source.super_info.get('timezone', "None")
            report["ha_version"] = self.ha_source.ha_info.get('version', "None")
        else:
            report["super_version"] = "Uninitialized"
            report["arch"] = "Uninitialized"
            report["timezone"] = "Uninitialized"
            report["ha_version"] = "Uninitialized"
        report["backups"] = self.coord.buildBackupMetrics()
        return report

    async def buildBugReportData(self, error):
        report = await self.buildErrorReport(error)
        report['addon_logs'] = "\n".join(b for a, b in list(getHistory(0, False))[-ERROR_LOG_LENGTH:])
        try:
            report['super_logs'] = "\n".join((await self.ha.getSuperLogs()).split("\n")[-ERROR_LOG_LENGTH:])
        except Exception as e:
            report['super_logs'] = logger.formatException(e)
        try:
            report['core_logs'] = "\n".join((await self.ha.getCoreLogs()).split("\n")[-ERROR_LOG_LENGTH:])
        except Exception as e:
            report['core_logs'] = logger.formatException(e)
        return report

    def buildClearReport(self):
        duration = self.time.now() - self.last_sent_error_time
        report = {
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
