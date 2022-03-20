from datetime import datetime, timedelta

from backup.config import Config, Setting
from backup.time import Time
from backup.exceptions import GoogleCredGenerateError, KnownError, LogicError, ensureKey
from aiohttp import ClientSession
from injector import inject
from .driverequests import DriveRequester
from backup.logger import getLogger
from backup.creds import Creds
import asyncio

logger = getLogger(__name__)
SCOPE = 'https://www.googleapis.com/auth/drive.file'


class AuthCodeQuery:
    @inject
    def __init__(self, config: Config, session: ClientSession, time: Time, drive: DriveRequester):
        self.session = session
        self.config = config
        self.drive = drive
        self.time = time
        self.client_id: str = None
        self.client_secret: str = None
        self.device_code: str = None
        self.verification_url: str = None
        self.user_code: str = None
        self.check_interval: timedelta = timedelta(seconds=5)
        self.expiration: datetime = time.now()
        self.last_check = time.now()

    async def requestCredentials(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        request_data = {
            'client_id': self.client_id,
            'scope': SCOPE
        }
        resp = await self.session.post(self.config.get(Setting.DRIVE_DEVICE_CODE_URL), data=request_data, timeout=30)
        if resp.status != 200:
            raise GoogleCredGenerateError(f"Google responded with error status HTTP {resp.status}.  Please verify your credentials are set up correctly.")
        data = await resp.json()
        self.device_code = str(ensureKey("device_code", data, "Google's authorization request"))
        self.verification_url = str(ensureKey("verification_url", data, "Google's authorization request"))
        self.user_code = str(ensureKey("user_code", data, "Google's authorization request"))
        self.expiration = self.time.now() + timedelta(seconds=int(ensureKey("expires_in", data, "Google's authorization request")))
        self.check_interval = timedelta(seconds=int(ensureKey("interval", data, "Google's authorization request")))

    async def waitForPermission(self) -> Creds:
        if not self.device_code:
            raise LogicError("Please call requestCredentials() first")
        error_count = 0
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'device_code': self.device_code,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
        }
        while self.expiration > self.time.now():
            start = self.time.now()
            resp = None
            try:
                resp = await self.session.post(self.config.get(Setting.DRIVE_TOKEN_URL), data=data, timeout=self.check_interval.total_seconds())
                try:
                    reply = await resp.json()
                except Exception:
                    reply = {}
                if resp.status == 403:
                    if reply.get("error", "") == "slow_down":
                        # google wants us to chill out, so do that
                        await asyncio.sleep(self.check_interval.total_seconds())
                    else:
                        # Google says no
                        logger.error(f"Getting credentials from Google failed with HTTP 403 and error: {reply.get('error', 'unspecified')}")
                        raise GoogleCredGenerateError("Google refused the request to connect your account, either because you rejected it or they were set up incorrectly.")
                elif resp.status == 428:
                    # Google says PEBKAC
                    logger.info(f"Waiting for you to authenticate with Google at {self.verification_url}")
                elif resp.status / 100 != 2:
                    # Mysterious error
                    logger.error(f"Getting credentials from Google failed with HTTP {resp.status} and error: {reply.get('error', 'unspecified')}")
                    raise GoogleCredGenerateError("Failed unexpectedly while trying to reach Google.  See the add-on logs for details.")
                else:
                    # got the token, return it
                    return Creds.load(self.time, reply, id=self.client_id, secret=self.client_secret)
            except KnownError:
                raise
            except Exception as e:
                logger.error("Error while trying to retrieve credentials from Google")
                logger.printException(e)

                # Allowing 10 errors is arbitrary, but prevents us from just erroring out forever in the background
                error_count += 1
                if error_count > 10:
                    raise GoogleCredGenerateError("Failed unexpectedly too many times while attempting to reach Google.  See the logs for details.")
            finally:
                if resp is not None:
                    resp.release()

            # Make sure we never query more than google says we should
            remainder = self.check_interval - (self.time.now() - start)
            if remainder > timedelta(seconds=0):
                await asyncio.sleep(remainder.total_seconds())

        logger.error("Getting credentials from Google expired, please try again")
        raise GoogleCredGenerateError("Credentials expired while waiting for you to authorize with Google")
