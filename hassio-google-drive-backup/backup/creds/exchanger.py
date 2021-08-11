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

        for url in self.config.getTokenServers("/drive/refresh"):
            try:
                headers = {
                    'addon_version': VERSION,
                    'client': self.config.clientIdentifier()
                }
                async with self.session.post(str(url), headers=headers, json=data, timeout=ClientTimeout(total=10)) as resp:
                    if resp.status < 400:
                        self.config.setPreferredTokenHost(url.host)
                        return Creds.load(self.time, await resp.json())
                    elif resp.status == 503:
                        raise CredRefreshGoogleError((await resp.json())["error"])
                    elif resp.status == 401:
                        raise GoogleCredentialsExpired()
                    else:
                        try:
                            extra = (await resp.json())["error"]
                        except BaseException:
                            extra = ""
                        raise CredRefreshMyError("HTTP {} {}".format(resp.status, extra))
            except ClientConnectorError:
                logger.warn("Unable to communicate with " + str(url) + ", trying alternate servers...")
            except asyncio.exceptions.TimeoutError:
                # TODO: Add tests for this exception
                logger.warn("Timed out communicating with " + str(url) + ", trying alternate servers...")
        raise CredRefreshMyError("Unable to connect to https://habackup.io")

    def refreshCredentials(self, refresh_token):
        return Creds(self.time, id=self._client_id, expiration=None, access_token=None, refresh_token=refresh_token, secret=self._client_secret)

    def _get_expiration(self, data):
        return self.time.now() + timedelta(seconds=int(ensureKey(KEY_EXPIRES_IN, data, CRED_OBJECT_NAME)))
