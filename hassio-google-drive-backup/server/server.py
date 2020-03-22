import os
import urllib
import json
from os.path import abspath, join
from aiohttp.web import Application, json_response, Request, TCPSite, AppRunner, post, Response, static, FileResponse, get
from aiohttp.client import ClientSession
from aiohttp.client_exceptions import ClientResponseError, ClientConnectorError, ServerConnectionError, ServerDisconnectedError, ServerTimeoutError
from aiohttp.web_exceptions import HTTPBadRequest, HTTPSeeOther
from yarl import URL

SCOPE = 'https://www.googleapis.com/auth/drive.file'
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
DEFAULT_REDIRECT = os.environ.get("AUTHORIZED_REDIRECT", "https://backup.beechens.com/drive/authorize")
URL_REFRESH = "https://www.googleapis.com/oauth2/v4/token"
URL_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"


class Server():
    # TODO: really should log request info here, client-iedntifier, etc
    def __init__(self, session: ClientSession, url_refresh=URL_REFRESH,
                 url_authorize=URL_AUTHORIZE, url_token=URL_TOKEN,
                 client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
                 authorized_redirect=DEFAULT_REDIRECT):
        self.session = session
        self.url_token = url_token
        self.url_authorize = url_authorize
        self.url_refresh = url_refresh
        self.client_id = client_id
        self.client_secret = client_secret
        self.authorized_redirect = authorized_redirect

    async def authorize(self, request: Request):
        if 'redirectbacktoken' in request.query:
            state = request.query.get('redirectbacktoken')
            url = URL(self.url_authorize).with_query({
                'client_id': self.client_id,
                'scope': SCOPE,
                'response_type': 'code',
                'include_granted_scopes': 'true',
                'access_type': "offline",
                'state': state,
                'redirect_uri': self.authorized_redirect,
                'prompt': "consent"
            })
            # Someone is trying to authenticate with the add-on, direct them to the google auth url
            raise HTTPSeeOther(str(url))
        elif 'state' in request.query and 'code' in request.query:
            state = request.query.get('state')
            code = request.query.get('code')
            try:
                data = urllib.parse.urlencode({
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'code': code,
                    'redirect_uri': self.authorized_redirect,
                    'grant_type': 'authorization_code'
                })

                async with self.session.post(self.url_token, headers={"content-type": "application/x-www-form-urlencoded"}, data=data) as resp:
                    resp.raise_for_status()
                    creds = await resp.json()
                sent_creds = {
                    'access_token': creds['access_token'],
                    'refresh_token': creds['refresh_token'],
                    'client_id': creds['client_id'],
                    'token_expiry': creds['token_expiry'],
                }

                # Redirect to "state" address with serialized creentials"
                raise HTTPSeeOther(state + "?creds=" + urllib.parse.quote(json.dumps(sent_creds)))
            except Exception as e:
                if isinstance(e, HTTPSeeOther):
                    # expected, pass this thorugh
                    raise
                content = "The server encountered an error while processing this request: " + str(e) + "<br/>"
                content += "Please <a href='https://github.com/sabeechen/hassio-google-drive-backup/issues'>file an issue</a> on Hass.io Google Backup's GitHub page so I'm aware of this problem or attempt authorizing with Google Drive again."
                return Response(status=500, body=content)
        else:
            raise HTTPBadRequest()

    async def error(self, request: Request):
        # TODO: Implement cloud storage for errors
        return Response()

    async def refresh(self, request: Request):
        data = {
            'client_id': request.query.get("client_id"),
            'client_secret': self.client_secret,
            'refresh_token': request.query.get("refresh_token"),
            'grant_type': 'refresh_token'
        }
        try:
            async with self.session.post(self.url_refresh, data=data) as resp:
                resp.raise_for_status()
                reply = await resp.json()
                return json_response({
                    "expires_in": reply["expires_in"],
                    "access_token": reply["access_token"]
                })
        except ClientResponseError as e:
            if e.status == 401:
                return json_response({
                    "error": "expired"
                }, status=401)
            else:
                # TODO: Make a special user visible error for this
                return json_response({
                    "error": "Google returned HTTP {}".format(e.status)
                }, status=503)
        except ClientConnectorError:
            return json_response({
                "error": "Couldn't connect to Google's servers"
            }, status=503)
        except ServerConnectionError:
            return json_response({
                "error": "Couldn't connect to Google's servers"
            }, status=503)
        except ServerDisconnectedError:
            return json_response({
                "error": "Couldn't connect to Google's servers"
            }, status=503)
        except ServerTimeoutError:
            return json_response({
                "error": "Google's servers timed out"
            }, status=503)
        except Exception as e:
            # TODO: log this
            return json_response({
                "error": str(e)
            }, status=500)

    async def picker(self, request: Request):
        path = abspath(join(__file__, "..", "static", "picker.html"))
        return FileResponse(path)

    async def index(self, request: Request):
        path = abspath(join(__file__, "..", "static", "index.html"))
        return FileResponse(path)

    def buildApp(self, app):
        path = abspath(join(__file__, "..", "static"))
        app.add_routes([
            static("/static", path, append_version=True),
            get("/drive/picker", self.picker),
            get("/", self.index),
            get("/drive/authorize", self.authorize),
            post("/drive/refresh", self.refresh),
            post("/logerror", self.error)
        ])
        return app

    async def start(self):
        runner = AppRunner(self.buildApp(Application()))
        await runner.setup()
        site = TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT")))
        await site.start()
        print("Server Started")
