import urllib
import json
import aiohttp_jinja2
import jinja2
from os.path import abspath, join
from aiohttp.web import Application, json_response, Request, TCPSite, AppRunner, post, Response, static, get
from aiohttp.client_exceptions import ClientResponseError, ClientConnectorError, ServerConnectionError, ServerDisconnectedError, ServerTimeoutError
from aiohttp.web_exceptions import HTTPBadRequest, HTTPSeeOther
from backup.creds import Exchanger
from backup.config import Config, Setting, VERSION
from backup.exceptions import GoogleCredentialsExpired, ensureKey, KnownError
from injector import ClassAssistedBuilder, inject, singleton
from .errorstore import ErrorStore
from .cloudlogger import CloudLogger


@singleton
class Server():
    @inject
    def __init__(self,
                 config: Config,
                 exchanger_builder: ClassAssistedBuilder[Exchanger],
                 logger: CloudLogger,
                 error_store: ErrorStore):
        self.exchanger = exchanger_builder.build(
            client_id=config.get(Setting.DEFAULT_DRIVE_CLIENT_ID),
            client_secret=config.get(Setting.DEFAULT_DRIVE_CLIENT_SECRET),
            redirect=config.get(Setting.AUTHENTICATE_URL))
        self.logger = logger
        self.config = config
        self.error_store = error_store
        self.base_context = {
            'version': VERSION
        }

    async def authorize(self, request: Request):
        if 'redirectbacktoken' in request.query:
            # Someone is trying to authenticate with the add-on, direct them to the google auth url
            raise HTTPSeeOther(await self.exchanger.getAuthorizationUrl(request.query.get('redirectbacktoken')))
        elif 'state' in request.query and 'code' in request.query:
            state = request.query.get('state')
            code = request.query.get('code')
            try:
                creds = (await self.exchanger.exchange(code)).serialize(include_secret=False)
                # Redirect to "state" address with serialized creentials"
                raise HTTPSeeOther(state + "?creds=" + urllib.parse.quote(json.dumps(creds)))
            except Exception as e:
                if isinstance(e, HTTPSeeOther):
                    # expected, pass this thorugh
                    raise
                self.logError(request, e)
                content = "The server encountered an error while processing this request: " + str(e) + "<br/>"
                content += "Please <a href='https://github.com/sabeechen/hassio-google-drive-backup/issues'>file an issue</a> on Home Assistant Google Backup's GitHub page so I'm aware of this problem or attempt authorizing with Google Drive again."
                return Response(status=500, body=content)
        else:
            raise HTTPBadRequest()

    async def error(self, request: Request):
        try:
            self.logReport(request, await request.json())
        except BaseException as e:
            self.logError(request, e)
        return Response()

    async def refresh(self, request: Request):
        try:
            token = ensureKey('refresh_token', await request.json(), "the request payload")
            creds = self.exchanger.refreshCredentials(token)
            new_creds = await self.exchanger.refresh(creds)
            return json_response(new_creds.serialize(include_secret=False))
        except ClientResponseError as e:
            if e.status == 401:
                return json_response({
                    "error": "expired"
                }, status=401)
            else:
                self.logError(request, e)
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
        except GoogleCredentialsExpired:
            return json_response({
                "error": "expired"
            }, status=401)
        except KnownError as e:
            return json_response({
                "error": e.message()
            }, status=503)
        except Exception as e:
            self.logError(request, e)
            return json_response({
                "error": str(e)
            }, status=500)

    @aiohttp_jinja2.template('picker.jinja2')
    async def picker(self, request: Request):
        return {
            **self.base_context,
            "client_id": self.config.get(Setting.DEFAULT_DRIVE_CLIENT_ID),
            "developer_key": self.config.get(Setting.DRIVE_PICKER_API_KEY),
            "app_id": self.config.get(Setting.DEFAULT_DRIVE_CLIENT_ID).split("-")[0]
        }

    @aiohttp_jinja2.template('server-index.jinja2')
    async def index(self, request: Request):
        return self.base_context

    def buildApp(self, app):
        path = abspath(join(__file__, "..", "..", "static"))
        app.add_routes([
            static("/static", path, append_version=True),
            get("/drive/picker", self.picker),
            get("/", self.index),
            get("/drive/authorize", self.authorize),
            post("/drive/refresh", self.refresh),
            post("/logerror", self.error)
        ])
        aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(path))
        return app

    async def start(self):
        runner = AppRunner(self.buildApp(Application()))
        await runner.setup()
        site = TCPSite(runner, "0.0.0.0", int(self.config.get(Setting.PORT)))
        await site.start()
        self.logger.info("Backup Auth Server Started")

    def logError(self, request: Request, exception: Exception):
        data = self.getRequestInfo(request)
        data['exception'] = self.logger.formatException(exception)
        self.logger.log_struct(data)

    def logReport(self, request, report):
        data = self.getRequestInfo(request)
        data['report'] = report
        self.logger.log_struct(data)
        self.error_store.store(data)

    def getRequestInfo(self, request: Request):
        return {
            'client': request.headers.get('client', "unknown"),
            'version': request.headers.get('addon_version', "unknown"),
            'address': request.remote,
            'url': str(request.url),
            'length': request.content_length
        }
