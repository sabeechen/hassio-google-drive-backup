from aiohttp import ClientSession, ContentTypeError, ClientConnectorError, ClientTimeout
from aiohttp.client_exceptions import ServerTimeoutError, ServerDisconnectedError, ClientOSError
from backup.exceptions import GoogleUnexpectedError, GoogleInternalError, GoogleRateLimitError, GoogleCredentialsExpired, CredRefreshGoogleError, DriveQuotaExceeded, GoogleDrivePermissionDenied, GoogleDnsFailure, GoogleCantConnect, GoogleTimeoutError
from backup.util import Resolver
from backup.logger import getLogger
from backup.config import Config, Setting
from injector import singleton, inject
from dns.exception import DNSException

RATE_LIMIT_EXCEEDED = [403]
TOO_MANY_REQUESTS = [429]
INTERNAL_ERROR = [500, 503]
PERMISSION_DENIED = [401]
REQUEST_TIMEOUT = [408]

logger = getLogger(__name__)


@singleton
class DriveRequester():
    @inject
    def __init__(self, config: Config, session: ClientSession, resolver: Resolver):
        self.session = session
        self.resolver = resolver
        self.config = config

    async def request(self, method, url, headers={}, json=None, data=None):
        try:
            # MAYBE: Exceptions here should clean up the response object
            response = await self.session.request(method, url, headers=headers, json=json, timeout=self.buildTimeout(), data=data)
            if response.status < 400:
                return response
            await self.raiseForKnownErrors(response)
            if response.status in PERMISSION_DENIED:
                raise GoogleCredentialsExpired()
            elif response.status in INTERNAL_ERROR:
                raise GoogleInternalError()
            elif response.status in RATE_LIMIT_EXCEEDED or response.status in TOO_MANY_REQUESTS:
                raise GoogleRateLimitError()
            elif response.status in REQUEST_TIMEOUT:
                raise GoogleTimeoutError()
            response.raise_for_status()
            return response
        except ClientConnectorError as e:
            logger.debug(
                "Ran into trouble reaching Google Drive's servers.  We'll use alternate DNS servers on the next attempt.")
            self.resolver.toggle()
            if "Cannot connect to host" in str(e) or "Connection reset by peer" in str(e):
                raise GoogleCantConnect()
            if e.os_error.errno == -2:
                # -2 means dns lookup failed.
                raise GoogleDnsFailure()
            elif str(e.os_error) == "Domain name not found":
                raise GoogleDnsFailure()
            elif e.os_error.errno in [99, 111, 10061, 104]:
                # 111 means connection refused
                # Can't connect
                raise GoogleCantConnect()
            elif "Could not contact DNS serve" in str(e.os_error):
                # Wish there was a better way to identify this exception
                raise GoogleDnsFailure()
            raise
        except ClientOSError as e:
            if e.errno == 1:
                raise GoogleUnexpectedError()
            raise
        except ServerTimeoutError:
            raise GoogleTimeoutError()
        except ServerDisconnectedError:
            raise GoogleUnexpectedError()
        except DNSException:
            logger.debug(
                "Ran into trouble resolving Google Drive's servers.  We'll use normal DNS servers on the next attempt.")
            self.resolver.toggle()
            raise GoogleDnsFailure()

    def buildTimeout(self):
        return ClientTimeout(
            sock_connect=self.config.get(
                Setting.GOOGLE_DRIVE_TIMEOUT_SECONDS),
            sock_read=self.config.get(Setting.GOOGLE_DRIVE_TIMEOUT_SECONDS))

    async def raiseForKnownErrors(self, response):
        try:
            message = await response.json()
        except ContentTypeError:
            return
        except ValueError:
            # parsing json failed, just give up
            return
        except TypeError:
            # Same
            return
        if "error" not in message:
            return
        error_obj = message["error"]
        if isinstance(error_obj, str):
            if error_obj == "expired":
                raise GoogleCredentialsExpired()
            else:
                raise CredRefreshGoogleError(error_obj)
        if "errors" not in error_obj:
            return
        for error in error_obj["errors"]:
            if "reason" not in error:
                continue
            if error["reason"] == "storageQuotaExceeded":
                raise DriveQuotaExceeded()
            elif error["reason"] in ["forbidden", "insufficientFilePermissions"]:
                raise GoogleDrivePermissionDenied()
