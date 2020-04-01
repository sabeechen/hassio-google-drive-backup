from ..exceptions import ensureKey
from ..time import Time
from typing import Optional
from datetime import datetime, timedelta

KEY_REFRESH_TOKEN = 'refresh_token'
KEY_CLIENT_ID = 'client_id'
KEY_CLIENT_SECRET = 'client_secret'
KEY_EXPIRES_IN = 'expires_in'
KEY_TOKEN_EXPIRY = 'token_expiry'
KEY_ACCESS_TOKEN = 'access_token'


class Creds():
    def __init__(self, time: Time, id: str, expiration: datetime,
                 access_token: str, refresh_token: str,
                 secret: Optional[str] = None):
        self._id = id
        self.time: Time = time
        self._secret = secret
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._expiration = expiration

    @property
    def id(self):
        return self._id

    @property
    def secret(self):
        return self._secret

    @property
    def refresh_token(self):
        return self._refresh_token

    @property
    def access_token(self):
        return self._access_token

    @property
    def expiration(self):
        if self._expiration is None:
            return self.time.now()
        return self._expiration

    @property
    def is_expired(self):
        return self.time.now() >= self.expiration

    def serialize(self, include_secret=True):
        ret = {
            "client_id": self.id
        }
        if self.secret is not None and include_secret:
            ret[KEY_CLIENT_SECRET] = self.secret
        if self.refresh_token is not None:
            ret[KEY_REFRESH_TOKEN] = self.refresh_token
        if self.access_token is not None:
            ret[KEY_ACCESS_TOKEN] = self.access_token
        if self.expiration is not None:
            ret[KEY_TOKEN_EXPIRY] = self.time.asRfc3339String(self.expiration)
        return ret

    @classmethod
    def load(cls, time: Time, data, id=None, secret=None):
        if id is None:
            id = ensureKey(KEY_CLIENT_ID, data, "credentials")
        if secret is None and KEY_CLIENT_SECRET in data:
            secret = data[KEY_CLIENT_SECRET]
        refresh = ensureKey(KEY_REFRESH_TOKEN, data, "credentials")
        access = ensureKey(KEY_ACCESS_TOKEN, data, "credentials")
        expires = None
        try:
            if KEY_TOKEN_EXPIRY in data:
                expires = time.parse(data[KEY_TOKEN_EXPIRY])
            elif KEY_EXPIRES_IN in data:
                expires = time.now() + timedelta(seconds=int(data[KEY_EXPIRES_IN]))
            else:
                expires = time.now()
        except BaseException:
            expires = time.now()
        return Creds(time=time, id=id, access_token=access, refresh_token=refresh, secret=secret, expiration=expires)
