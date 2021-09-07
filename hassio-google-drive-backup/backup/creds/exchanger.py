import asyncio
from aiohttp import ClientSession, ClientConnectorError, ClientTimeout
from .creds import Creds, KEY_CLIENT_ID, KEY_CLIENT_SECRET, KEY_ACCESS_TOKEN, KEY_REFRESH_TOKEN, KEY_EXPIRES_IN
from ..exceptions import ensureKey, GoogleCredentialsExpired, CredRefreshGoogleError, CredRefreshMyError
from ..config import Config, Setting, VERSION
from yarl import URL
from ..time import Time
from ..logger import getLogger
from .driverequester import DriveRequester
from datetime import timedelta
from injector import singleton, inject


SCOPE = 'https://www.googleapis.com/auth/drive.file'

KEY_REDIRECT_URI = 'redirect_uri'
KEY_SCOPE = 'scope'
KEY_RESPONSE_TYPE = 'response_type'
KEY_INCLUDE_GRANTED_SCOPES = 'include_granted_scopes'
KEY_ACCESS_TYPE = 'access_type'
KEY_STATE = 'state'
KEY_PROMPT = 'prompt'
KEY_CODE = 'code'
KEY_GRANT_TYPE = 'grant_type'
KEY_VERSION = 'version'
KEY_CLIENT = 'client'

CRED_OBJECT_NAME = "credential token response"

logger = getLogger(__name__)


@singleton
class Exchanger():
    @inject
    def __init__(self,
                 time: Time,
                 session: ClientSession,
                 config: Config,
                 drive: DriveRequester,
                 client_id: str,
                 client_secret: str,
                 redirect: URL):
        self.time = time
        self.config = config
        self.session = session
        self.drive = drive
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect = redirect

    async def getAuthorizationUrl(self, state="") -> str:
        url = URL(self.config.get(Setting.DRIVE_AUTHORIZE_URL)).with_query({
            KEY_CLIENT_ID: self._client_id,
            KEY_SCOPE: SCOPE,
            KEY_RESPONSE_TYPE: 'code',
            KEY_INCLUDE_GRANTED_SCOPES: 'true',
            KEY_ACCESS_TYPE: "offline",
            KEY_STATE: state,
            KEY_REDIRECT_URI: str(self._redirect),
            KEY_PROMPT: "consent"
        })
        return str(url)

    async def exchange(self, code):
        data = {
            KEY_CLIENT_ID: self._client_id,
            KEY_CLIENT_SECRET: self._client_secret,
            KEY_CODE: code,
            KEY_REDIRECT_URI: str(self._redirect),
            KEY_GRANT_TYPE: 'authorization_code'
        }
        resp = None
        try:
            resp = await self.drive.request("post", self.config.get(Setting.DRIVE_TOKEN_URL), data=data)
            return Creds.load(self.time, await resp.json(), id=self._client_id, secret=self._client_secret)
        finally:
            if resp is not None:
                resp.release()

    async def refresh(self, creds: Creds):
        if creds.secret is not None:
            return await self._refresh_google(creds)
        else:
            return await self._refresh_default(creds)

    async def _refresh_google(self, creds: Creds):
        data = {
            KEY_CLIENT_ID: creds.id,
            KEY_CLIENT_SECRET: creds.secret,
            KEY_REFRESH_TOKEN: creds.refresh_token,
            KEY_GRANT_TYPE: 'refresh_token'
        }
        resp = None
        try:
            resp = await self.drive.request("post", self.config.get(Setting.DRIVE_REFRESH_URL), data=data)
            data = await resp.json()
            return Creds(
                self.time,
                id=creds.id,
                secret=creds.secret,
                access_token=ensureKey(KEY_ACCESS_TOKEN, data, CRED_OBJECT_NAME),
                refresh_token=creds.refresh_token,
                expiration=self._get_expiration(data))
        finally:
            if resp is not None:
                resp.release()

    async def _refresh_default(self, creds: Creds):
        data = {
            KEY_CLIENT_ID: creds.id,
            KEY_REFRESH_TOKEN: creds.refresh_token,
        }
        token_paths = self.config.getTokenServers("/drive/refresh")
        last_error = None
        for url in token_paths:
            try:
                headers = {
                    'addon_version': VERSION,
                    'client': self.config.clientIdentifier()
                }
                async with self.session.post(str(url), headers=headers, json=data, timeout=ClientTimeout(total=self.config.get(Setting.EXCHANGER_TIMEOUT_SECONDS))) as resp:
                    if resp.status < 400:
                        return Creds.load(self.time, await resp.json())
                    elif resp.status == 503:
                        json = {}
                        try:
                            json = await resp.json()
                        except BaseException:
                            pass
                        if "error" in json:
                            if "invalid_grant" in json["error"]:
                                raise GoogleCredentialsExpired()
                            else:
                                # Record the error, but still try other hosts
                                last_error = CredRefreshGoogleError(json["error"])
                        else:
                            last_error = CredRefreshMyError("HTTP 503 from " + url.host)
                    elif resp.status == 401:
                        raise GoogleCredentialsExpired()
                    else:
                        try:
                            extra = (await resp.json())["error"]
                        except BaseException:
                            extra = ""

                        # this is likely due to misconfiguration
                        logger.warning("Got {0}:{1} from {2}, trying alternate server(s)...".format(resp.status, extra, url.host))
                        last_error = CredRefreshMyError("HTTP {} {}".format(resp.status, extra))
            except ClientConnectorError:
                logger.warning("Unable to reach " + str(url.host) + ", trying alternate server(s)...")
                last_error = "Couldn't communicate with " + url.host
            except asyncio.exceptions.TimeoutError:
                logger.warning("Timed out communicating with " + str(url.host) + ", trying alternate server(s)...")
                last_error = "Timed out communicating with " + url.host
        logger.error("Unable to refresh credentials with Google Drive")
        if isinstance(last_error, str):
            raise CredRefreshMyError(last_error)
        elif isinstance(last_error, Exception):
            raise last_error
        else:
            raise Exception("Unexpected error type: " + str(last_error))

    def refreshCredentials(self, refresh_token):
        return Creds(self.time, id=self._client_id, expiration=None, access_token=None, refresh_token=refresh_token, secret=self._client_secret)

    def _get_expiration(self, data):
        return self.time.now() + timedelta(seconds=int(ensureKey(KEY_EXPIRES_IN, data, CRED_OBJECT_NAME)))
