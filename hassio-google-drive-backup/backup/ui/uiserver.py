import asyncio
import ssl
import json
import aiohttp_jinja2
import jinja2
from datetime import timedelta
from os.path import abspath, join
from typing import Any, Dict
from urllib.parse import quote

from aiohttp import BasicAuth, hdrs, web, ClientSession
from aiohttp.web import HTTPBadRequest, HTTPException, Request
from injector import ClassAssistedBuilder, inject, singleton

from backup.config import Config, Setting, CreateOptions, BoolValidator, Startable, VERSION
from backup.const import SOURCE_GOOGLE_DRIVE, SOURCE_HA, GITHUB_BUG_TEMPLATE
from backup.model import Coordinator, Snapshot
from backup.exceptions import KnownError, ensureKey
from backup.util import GlobalInfo, Estimator, File
from backup.ha import HaSource, PendingSnapshot, SNAPSHOT_NAME_KEYS, HaRequests
from backup.ha import Password
from backup.time import Time
from backup.worker import Trigger
from backup.logger import getLogger, getHistory, TraceLogger
from backup.creds import Exchanger, MANUAL_CODE_REDIRECT_URI, Creds
from backup.debugworker import DebugWorker
from backup.drive import FolderFinder

from .debug import Debug

logger = getLogger(__name__)

# Used to Google's oauth verification
SCOPE: str = 'https://www.googleapis.com/auth/drive.file'


@singleton
class UiServer(Trigger, Startable):
    @inject
    def __init__(self, debug: Debug, coord: Coordinator, ha_source: HaSource, harequests: HaRequests,
                 time: Time, config: Config, global_info: GlobalInfo, estimator: Estimator,
                 session: ClientSession, exchanger_builder: ClassAssistedBuilder[Exchanger], debug_worker: DebugWorker, folder_finder: FolderFinder):
        super().__init__()
        # Currently running server tasks
        self.runners = []
        self.exchanger_builder = exchanger_builder
        self._coord = coord
        self._time = time
        self.manual_exchanger: Exchanger = None
        self.config: Config = config
        self.auth_cache: Dict[str, Any] = {}
        self.last_log_index = 0
        self.host_server = None
        self.ingress_server = None
        self.running = False
        self._harequests = harequests
        self._global_info = global_info
        self._ha_source = ha_source
        self._starts = 0
        self._estimator = estimator
        self._debug = debug
        self.session = session
        self.debug_worker = debug_worker
        self.folder_finder = folder_finder

    def name(self):
        return "UI Server"

    def base_context(self):
        return {
            'version': VERSION,
            'backgroundColor': self.config.get(Setting.BACKGROUND_COLOR),
            'accentColor': self.config.get(Setting.ACCENT_COLOR),
            'coordEnabled': self._coord.enabled()
        }

    async def getstatus(self, request) -> Dict[Any, Any]:
        status: Dict[Any, Any] = {}
        status['folder_id'] = self.folder_finder.getCachedFolder()
        status['snapshots'] = []
        snapshots = self._coord.snapshots()
        for snapshot in snapshots:
            status['snapshots'].append(self.getSnapshotDetails(snapshot))
        status['restore_link'] = self._ha_source.getFullRestoreLink()
        status['drive_enabled'] = self._coord.enabled()
        status['ask_error_reports'] = not self.config.isExplicit(
            Setting.SEND_ERROR_REPORTS)
        status['warn_ingress_upgrade'] = False
        status['cred_version'] = self._global_info.credVersion
        status['free_space'] = Estimator.asSizeString(
            self._estimator.getBytesFree())
        next = self._coord.nextSnapshotTime()
        if next is None:
            status['next_snapshot_text'] = "Disabled"
            status['next_snapshot_machine'] = ""
            status['next_snapshot_detail'] = "Disabled"
        elif (next < self._time.now()):
            status['next_snapshot_text'] = self._time.formatDelta(
                self._time.now())
            status['next_snapshot_machine'] = self._time.asRfc3339String(
                self._time.now())
            status['next_snapshot_detail'] = self._time.toLocal(
                self._time.now()).strftime("%c")
        else:
            status['next_snapshot_text'] = self._time.formatDelta(next)
            status['next_snapshot_machine'] = self._time.asRfc3339String(next)
            status['next_snapshot_detail'] = self._time.toLocal(
                next).strftime("%c")

        if len(snapshots) > 0:
            latest = snapshots[len(snapshots) - 1].date()
            status['last_snapshot_text'] = self._time.formatDelta(latest)
            status['last_snapshot_machine'] = self._time.asRfc3339String(
                latest)
            status['last_snapshot_detail'] = self._time.toLocal(
                latest).strftime("%c")
        else:
            status['last_snapshot_text'] = "Never"
            status['last_snapshot_machine'] = ""
            status['last_snapshot_detail'] = "Never"

        status['last_error'] = None
        if self._global_info._last_error is not None and self._global_info.isErrorSuppressed():
            status['last_error'] = self.processError(
                self._global_info._last_error)
        status["last_error_count"] = self._global_info.failureCount()
        status["ignore_errors_for_now"] = self._global_info.ignoreErrorsForNow()
        status["syncing"] = self._coord.isSyncing()
        status["ignore_sync_error"] = self._coord.isWorkingThroughUpload()
        status["firstSync"] = self._global_info._first_sync
        status["maxSnapshotsInHasssio"] = self.config.get(
            Setting.MAX_SNAPSHOTS_IN_HASSIO)
        status["maxSnapshotsInDrive"] = self.config.get(
            Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE)
        status["snapshot_name_template"] = self.config.get(
            Setting.SNAPSHOT_NAME)
        status['sources'] = self._coord.buildSnapshotMetrics()
        status['authenticate_url'] = self.config.get(Setting.AUTHENTICATE_URL)
        status['choose_folder_url'] = self.config.get(Setting.CHOOSE_FOLDER_URL) + "?bg={0}&ac={1}".format(
            quote(self.config.get(Setting.BACKGROUND_COLOR)), quote(self.config.get(Setting.ACCENT_COLOR)))
        status['dns_info'] = self._global_info.getDnsInfo()
        status['enable_drive_upload'] = self.config.get(
            Setting.ENABLE_DRIVE_UPLOAD)
        status['is_custom_creds'] = self._coord._model.dest.isCustomCreds()
        status['is_specify_folder'] = self.config.get(
            Setting.SPECIFY_SNAPSHOT_FOLDER)
        return web.json_response(status)

    def getSnapshotDetails(self, snapshot: Snapshot):
        drive = snapshot.getSource(SOURCE_GOOGLE_DRIVE)
        ha = snapshot.getSource(SOURCE_HA)
        return {
            'name': snapshot.name(),
            'slug': snapshot.slug(),
            'size': snapshot.sizeString(),
            'status': snapshot.status(),
            'date': self._time.toLocal(snapshot.date()).strftime("%c"),
            'inDrive': drive is not None,
            'inHA': ha is not None,
            'isPending': ha is not None and type(ha) is PendingSnapshot,
            'protected': snapshot.protected(),
            'type': snapshot.snapshotType(),
            'details': snapshot.details(),
            'deleteNextDrive': snapshot.getPurges().get(SOURCE_GOOGLE_DRIVE) or False,
            'deleteNextHa': snapshot.getPurges().get(SOURCE_HA) or False,
            'driveRetain': drive.retained() if drive else False,
            'haRetain': ha.retained() if ha else False
        }

    async def manualauth(self, request: Request) -> None:
        client_id = request.query.get("client_id", "")
        code = request.query.get("code", "")
        client_secret = request.query.get("client_secret", "")
        if client_id != "" and client_secret != "":
            try:
                # Redirect to the webpage that takes you to the google auth page.
                self.manual_exchanger = self.exchanger_builder.build(
                    client_id=client_id.strip(),
                    client_secret=client_secret.strip(),
                    redirect=MANUAL_CODE_REDIRECT_URI)
                return web.json_response({
                    'auth_url': await self.manual_exchanger.getAuthorizationUrl()
                })
            except Exception as e:
                return web.json_response({
                    'error': "Couldn't create authorization URL, Google said:" + str(e)
                })
        elif code != "":
            try:
                self._coord.saveCreds(await self.manual_exchanger.exchange(code))
                self._global_info.setIngoreErrorsForNow(True)
                return web.json_response({'auth_url': "index?fresh=true"})
            except KnownError as e:
                return web.json_response({'error': e.message()})
            except Exception as e:
                return web.json_response({'error': "Couldn't authorize with Google Drive, Google said:" + str(e)})
        raise HTTPBadRequest()

    async def snapshot(self, request: Request) -> Any:
        custom_name = request.query.get("custom_name", None)
        retain_drive = BoolValidator.strToBool(
            request.query.get("retain_drive", False))
        retain_ha = BoolValidator.strToBool(
            request.query.get("retain_ha", False))
        options = CreateOptions(self._time.now(), custom_name, {
            SOURCE_GOOGLE_DRIVE: retain_drive,
            SOURCE_HA: retain_ha
        })
        snapshot = await self._coord.startSnapshot(options)
        return web.json_response({"message": "Requested snapshot '{0}'".format(snapshot.name())})

    async def deleteSnapshot(self, request: Request):
        drive = BoolValidator.strToBool(request.query.get("drive", False))
        ha = BoolValidator.strToBool(request.query.get("ha", False))
        slug = request.query.get("slug", "")
        self._coord.getSnapshot(slug)
        sources = []
        messages = []
        if drive:
            messages.append("Google Drive")
            sources.append(SOURCE_GOOGLE_DRIVE)
        if ha:
            messages.append("Home Assistant")
            sources.append(SOURCE_HA)
        await self._coord.delete(sources, slug)
        return web.json_response({"message": "Deleted from " + " and ".join(messages)})

    async def retain(self, request: Request):
        drive = BoolValidator.strToBool(request.query.get("drive", False))
        ha = BoolValidator.strToBool(request.query.get("ha", False))
        slug = request.query.get("slug", "")

        snapshot: Snapshot = self._coord.getSnapshot(slug)

        # override create options for future uploads
        options = CreateOptions(self._time.now(), self.config.get(Setting.SNAPSHOT_NAME), {
            SOURCE_GOOGLE_DRIVE: BoolValidator.strToBool(drive),
            SOURCE_HA: BoolValidator.strToBool(ha)
        })
        snapshot.setOptions(options)

        retention = {}
        if snapshot.getSource(SOURCE_GOOGLE_DRIVE) is not None:
            retention[SOURCE_GOOGLE_DRIVE] = BoolValidator.strToBool(drive)
        if snapshot.getSource(SOURCE_HA) is not None:
            retention[SOURCE_HA] = BoolValidator.strToBool(ha)
        await self._coord.retain(retention, slug)
        return web.json_response({'message': "Updated the snapshot's settings"})

    async def resolvefolder(self, request: Request):
        use_existing = BoolValidator.strToBool(
            request.query.get("use_existing", False))
        self.folder_finder.resolveExisting(use_existing)
        self._global_info.suppressError()
        self._global_info.setIngoreErrorsForNow(True)
        await self.sync()
        return web.json_response({'message': 'Done'})

    async def skipspacecheck(self, request: Request):
        self._global_info.setSkipSpaceCheckOnce(True)
        self._global_info.setIngoreErrorsForNow(True)
        await self.startSync(request)
        return web.json_response({'message': 'Done'})

    async def confirmdelete(self, request: Request):
        always = BoolValidator.strToBool(request.query.get("always", False))
        self._global_info.allowMultipleDeletes()
        self._global_info.setIngoreErrorsForNow(True)
        if always:
            validated = self.config.validateUpdate(
                {"confirm_multiple_deletes": False})
            await self._updateConfiguration(validated)
            await self.sync()
            return web.json_response({'message': 'Configuration updated, I\'ll never ask again'})
        else:
            await self.sync()
            return web.json_response({'message': 'Snapshots deleted this one time'})

    async def log(self, request: Request) -> Any:
        format = request.query.get("format", "download")
        catchup = BoolValidator.strToBool(
            request.query.get("catchup", "False"))
        if not catchup:
            self.last_log_index = 0
        if format == "view":
            context = self.base_context()
            return aiohttp_jinja2.render_template("logs.jinja2",
                                                  request,
                                                  context)
        resp = web.StreamResponse()
        if format == "html":
            resp.content_type = 'text/html'
        else:
            resp.content_type = 'text/plain'
            resp.headers['Content-Disposition'] = 'attachment; filename="home-assistant-google-drive-backup.log"'

        await resp.prepare(request)

        def content():
            html = format == "colored"
            if format == "html":
                yield "<html><head><title>Home Assistant Google Drive Backup Log</title></head><body><pre>\n"
            for line in getHistory(self.last_log_index, html):
                self.last_log_index = line[0]
                if line:
                    yield line[1].replace("\n", "   \n") + "\n"
            if format == "html":
                yield "</pre></body>\n"

        for line in content():
            await resp.write(line.encode())
        await resp.write_eof()

    async def token(self, request: Request) -> None:
        if 'creds' in request.query:
            self._global_info.setIngoreErrorsForNow(True)
            self._coord.saveCreds(Creds.load(
                self._time, json.loads(request.query['creds'])))
        try:
            if request.url.port != self.config.get(Setting.PORT):
                return await self.redirect(request, self._ha_source.getAddonUrl())
        except:  # noqa: E722
            # eat the error
            pass
        return await self.redirect(request, "/")

    async def changefolder(self, request: Request) -> None:
        # update config to specify snapshot folder
        await self._updateConfiguration(self.config.validateUpdate({Setting.SPECIFY_SNAPSHOT_FOLDER: True}))

        id = request.query.get("id", None)
        await self.folder_finder.save(id)
        self._global_info.setIngoreErrorsForNow(True)
        self.trigger()
        try:
            if request.url.port != self.config.get(Setting.PORT):
                return await self.redirect(request, self._ha_source.getAddonUrl())
        except:  # noqa: E722
            # eat the error
            pass
        return await self.redirect(request, "/")

    async def sync(self, request: Request = None) -> Any:
        await self._coord.sync()
        return await self.getstatus(request)

    async def startSync(self, request) -> Any:
        asyncio.create_task(self._coord.sync(), name="Sync from web request")
        await self._coord._sync_start.wait()
        return await self.getstatus(request)

    async def cancelSync(self, request: Request):
        await self._coord.cancel()
        return await self.getstatus(request)

    async def getconfig(self, request: Request):
        await self._ha_source.refresh()
        name_keys = {}
        for key in SNAPSHOT_NAME_KEYS:
            name_keys[key] = SNAPSHOT_NAME_KEYS[key](
                "Full", self._time.now(), self._ha_source.getHostInfo())
        current_config = {}
        for setting in Setting:
            current_config[setting.key()] = self.config.getForUi(setting)
        default_config = {}
        for setting in Setting:
            default_config[setting.key()] = setting.default()
        return web.json_response({
            'config': current_config,
            'addons': self._global_info.addons,
            'name_keys': name_keys,
            'defaults': default_config,
            'snapshot_folder': self.folder_finder.getCachedFolder(),
            'is_custom_creds': self._coord._model.dest.isCustomCreds()
        })

    async def errorreports(self, request: Request):
        send = BoolValidator.strToBool(request.query.get("send", False))

        update = {
            "send_error_reports": send
        }
        validated = self.config.validateUpdate(update)
        await self._updateConfiguration(validated)
        return web.json_response({'message': 'Configuration updated'})

    async def exposeserver(self, request: Request):
        expose = BoolValidator.strToBool(request.query.get("expose", False))
        if expose:
            update = {
                Setting.EXPOSE_EXTRA_SERVER: True
            }
        else:
            update = {
                Setting.EXPOSE_EXTRA_SERVER: False,
                Setting.USE_SSL: False,
                Setting.REQUIRE_LOGIN: False
            }
        validated = self.config.validateUpdate(update)
        await self._updateConfiguration(validated)

        File.touch(self.config.get(Setting.INGRESS_TOKEN_FILE_PATH))
        await self._ha_source.init()

        redirect = ""
        try:
            if request.url.port != self.config.get(Setting.INGRESS_PORT):
                redirect = self._ha_source.getFullAddonUrl()
        except:  # noqa: E722
            # eat the error
            pass
        return web.json_response({
            'message': 'Configuration updated',
            'redirect': redirect
        })

    async def makeanissue(self, request: Request):
        if self._global_info._last_error is not None:
            error = logger.formatException(self._global_info._last_error)
        else:
            error = "No error could be identified automatically."
        data = await self.debug_worker.buildBugReportData(error)
        body = GITHUB_BUG_TEMPLATE
        for key in data:
            if isinstance(data[key], dict):
                body = body.replace(
                    "{" + key + "}", json.dumps(data[key], indent=4))
            else:
                body = body.replace("{" + key + "}", str(data[key]))
        return web.json_response({'markdown': body})

    async def saveconfig(self, request: Request) -> Any:
        data = await request.json()
        update = ensureKey("config", data, "the confgiuration update request")

        # validate the snapshot password
        Password(self.config.getConfigFor(update)).resolve()

        validated = self.config.validate(update)
        await self._updateConfiguration(validated, ensureKey("snapshot_folder", data, "the configuration update request"), trigger=False)
        try:
            await self.cancelSync(request)
            await self.startSync(request)
        except:  # noqa: E722
            # eat the error, just cancel optimistically
            pass
        return web.json_response({'message': 'Settings saved'})

    async def _updateConfiguration(self, new_config, snapshot_folder_id=None, trigger=True):
        update = {}
        for key in new_config:
            update[key.key()] = new_config[key]
        await self._harequests.updateConfig(update)

        was_specify = self.config.get(Setting.SPECIFY_SNAPSHOT_FOLDER)
        self.config.update(new_config)

        is_specify = self.config.get(Setting.SPECIFY_SNAPSHOT_FOLDER)

        if not was_specify and is_specify and not self._coord._model.dest.isCustomCreds():
            # Delete the reset the saved backup folder, since the preference
            # for specifying the folder changed from false->true
            self.folder_finder.reset()
        if self.config.get(Setting.SPECIFY_SNAPSHOT_FOLDER) and self._coord._model.dest.isCustomCreds() and snapshot_folder_id is not None and len(snapshot_folder_id):
            await self.folder_finder.save(snapshot_folder_id)
        if trigger:
            self.trigger()
        return {'message': 'Settings saved'}

    def _getServerOptions(self):
        return {
            "ssl": self.config.get(Setting.USE_SSL),
            "login": self.config.get(Setting.REQUIRE_LOGIN),
            "certfile": self.config.get(Setting.CERTFILE),
            "keyfile": self.config.get(Setting.KEYFILE),
            "extra_server": self.config.get(Setting.EXPOSE_EXTRA_SERVER)
        }

    async def upload(self, request: Request):
        slug = request.query.get("slug", "")
        await self._coord.uploadSnapshot(slug)
        return web.json_response({'message': "Snapshot uploaded to Home Assistant"})

    async def redirect(self, request, url):
        context = {
            **self.base_context(),
            'url': url
        }
        return aiohttp_jinja2.render_template("redirect.jinja2",
                                              request,
                                              context)

    async def download(self, request: Request):
        slug = request.query.get("slug", "")
        snapshot = self._coord.getSnapshot(slug)
        stream = await self._coord.download(slug)
        await stream.setup()
        resp = web.StreamResponse()
        resp.content_type = 'application/tar'
        resp.headers['Content-Disposition'] = 'attachment; filename="{}.tar"'.format(
            snapshot.name())
        resp.headers['Content-Length'] = str(stream.size())

        await resp.prepare(request)

        # SOMEDAY: consider re-streaming a decrypted tar file for the sake of convenience

        async for chunk in stream.generator(self.config.get(Setting.DEFAULT_CHUNK_SIZE)):
            await resp.write(chunk)

        await resp.write_eof()

    async def run(self) -> None:
        await self.stop()

        # Create the ingress server
        app = web.Application(middlewares=[self.error_middleware])
        aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(self.filePath()))
        self._addRoutes(app)

        # The ingress port is considered secured by Home Assistant, so it doesn't get SSL or basic HTTP auth
        logger.info("Starting server on port {}".format(
            self.config.get(Setting.INGRESS_PORT)))
        await self._start_site(app, self.config.get(Setting.INGRESS_PORT))

        try:
            if self.config.get(Setting.EXPOSE_EXTRA_SERVER):
                ssl_context = None
                if self.config.get(Setting.USE_SSL):
                    ssl_context = ssl.create_default_context(
                        ssl.Purpose.CLIENT_AUTH)
                    ssl_context.load_cert_chain(self.config.get(
                        Setting.CERTFILE), self.config.get(Setting.KEYFILE))
                middleware = [self.error_middleware]
                if self.config.get(Setting.REQUIRE_LOGIN):
                    middleware.append(HomeAssistantLoginAuth(
                        self._time, self._harequests))

                extra_app = web.Application(middlewares=middleware)
                aiohttp_jinja2.setup(extra_app, loader=jinja2.FileSystemLoader(self.filePath()))
                self._addRoutes(extra_app)
                logger.info("Starting server on port {}".format(
                    self.config.get(Setting.PORT)))
                await self._start_site(extra_app, self.config.get(Setting.PORT), ssl_context=ssl_context)
        except FileNotFoundError:
            logger.error("The configured SSL key or certificate files couldn't be found and so \nan SSL server couldn't be started, please check your settings. \nThe addon web-ui is still available through ingress.")
        except ssl.SSLError:
            logger.error("Your SSL certificate or key couldn't be loaded and so an SSL server couldn't be started.  Please verify that your SSL settings are correctly configured.  The addon web-ui is still available through ingress.")
        logger.info("Server started")
        self.running = True
        self._starts += 1

    def _addRoutes(self, app):
        app.add_routes(
            [web.static('/static', abspath(join(__file__, "..", "..", "static")), append_version=True)])
        app.add_routes([web.get('/', self.index)])
        app.add_routes([web.get('/index.html', self.index)])
        app.add_routes([web.get('/index', self.index)])
        self._addRoute(app, self.reauthenticate)
        self._addRoute(app, self.tos)
        self._addRoute(app, self.pp)

        self._addRoute(app, self.getstatus)
        self._addRoute(app, self.snapshot)
        self._addRoute(app, self.manualauth)
        self._addRoute(app, self.token)

        self._addRoute(app, self.log)

        self._addRoute(app, self.sync)
        self._addRoute(app, self.startSync)
        self._addRoute(app, self.cancelSync)

        self._addRoute(app, self.getconfig)
        self._addRoute(app, self.errorreports)
        self._addRoute(app, self.exposeserver)
        self._addRoute(app, self.saveconfig)
        self._addRoute(app, self.changefolder)
        self._addRoute(app, self.confirmdelete)
        self._addRoute(app, self.resolvefolder)
        self._addRoute(app, self.skipspacecheck)

        self._addRoute(app, self.upload)
        self._addRoute(app, self.download)
        self._addRoute(app, self.deleteSnapshot)
        self._addRoute(app, self.retain)

        self._addRoute(app, self._debug.simerror)
        self._addRoute(app, self._debug.getTasks)
        self._addRoute(app, self.makeanissue)

    def _addRoute(self, app, method):
        app.add_routes([
            web.get("/" + method.__name__, method),
            web.post("/" + method.__name__, method)
        ])

    async def start(self):
        await self.run()

    async def _start_site(self, app, port, ssl_context=None):
        aiohttp_logger = TraceLogger("aiohttp.access")
        runner = web.AppRunner(app, logger=aiohttp_logger, access_log=aiohttp_logger,
                               access_log_format='%a %t "%r" %s %b "%{Referer}i" "%{User-Agent}i (%Tfs)"')
        self.runners.append(runner)
        await runner.setup()
        # maybe host should be 0.0.0.0
        site = web.TCPSite(runner, "0.0.0.0", port, ssl_context=ssl_context)
        await site.start()

    async def stop(self):
        # Stop pending requests for all available servers
        for runner in self.runners:
            try:
                await runner.shutdown()
            except Exception as e:
                logger.error(
                    "Error while trying to shut down server: " + str(e))
            try:
                await runner.cleanup()
            except Exception as e:
                logger.error(
                    "Error while trying to shut down server: " + str(e))
        self.runners = []

    async def shutdown(self):
        await self.stop()

    @web.middleware
    async def error_middleware(self, request: Request, handler):
        try:
            logger.trace("Serving %s %s to %s", request.method,
                         request.url, request.remote)
            handled = await handler(request)
            logger.trace("Completed %s %s", request.method, request.url)
            return handled
        except Exception as ex:
            logger.trace("Error serving %s %s", request.method, request.url)
            logger.trace(logger.formatException(ex))
            if isinstance(ex, HTTPException):
                raise
            data = self.processError(ex)
            return web.json_response(data, status=data['http_status'])

    def processError(self, e):
        if isinstance(e, KnownError):
            known: KnownError = e
            return {
                'http_status': known.httpStatus(),
                'error_type': known.code(),
                'message': known.message(),
                'details': logger.formatException(e),
                'data': known.data()
            }
        else:
            return {
                'http_status': 500,
                'error_type': "generic_error",
                'message': "An unexpected error occurred: " + str(e),
                'details': logger.formatException(e)
            }

    def filePath(self, name=None):
        if name is None:
            return abspath(join(__file__, "..", "..", "static"))
        else:
            return abspath(join(__file__, "..", "..", "static", name))

    def cssElement(self, selector, keys):
        ret = selector
        ret += " {\n"
        for key in keys:
            ret += "\t" + key + ": " + keys[key] + ";\n"
        ret += "}\n\n"
        return ret

    async def index(self, request: Request):
        if not self._coord.enabled():
            template = "index.jinja2"
            context = {
                **self.base_context(),
                'showOpenDriveLink': True
            }
        else:
            template = "working.jinja2"
            context = {
                **self.base_context(),
                'showOpenDriveLink': True,
                'navBarTitle': 'Snapshots'
            }
        response = aiohttp_jinja2.render_template(template,
                                                  request,
                                                  context)
        response.headers['cache-control'] = 'no-store'
        return response

    @aiohttp_jinja2.template('privacy_policy.jinja2')
    async def pp(self, request: Request):
        return self.base_context()

    @aiohttp_jinja2.template('terms_of_service.jinja2')
    async def tos(self, request: Request):
        return self.base_context()

    @aiohttp_jinja2.template('index.jinja2')
    async def reauthenticate(self, request: Request) -> Any:
        return {
            **self.base_context(),
            'showOpenDriveLink': True
        }


@web.middleware
class HomeAssistantLoginAuth():
    def __init__(self, time, harequests):
        self._time = time
        self._harequests = harequests
        self.auth_cache: Dict[str, Any] = {}
        self.realm = "Home Assistant Login"

    def parse_auth_header(self, request):
        auth_header = request.headers.get(hdrs.AUTHORIZATION)
        if not auth_header:
            return None
        try:
            auth = BasicAuth.decode(auth_header=auth_header)
        except ValueError:
            auth = None
        return auth

    async def authenticate(self, request):
        auth = self.parse_auth_header(request)
        return (auth is not None and await self.check_credentials(auth.login, auth.password))

    async def check_credentials(self, username, password):
        if username is None:
            raise ValueError('username is None')  # pragma: no cover

        if password is None:
            raise ValueError('password is None')  # pragma: no cover

        if username in self.auth_cache and self.auth_cache[username]['password'] == password and self.auth_cache[username]['timeout'] > self._time.now():
            return True
        try:
            await self._harequests.auth(username, password)
            self.auth_cache[username] = {'password': password, 'timeout': (
                self._time.now() + timedelta(minutes=10))}
            return True
        except Exception as e:
            logger.printException(e)
            return False

    def challenge(self):
        return web.Response(
            body=b'', status=401, reason='UNAUTHORIZED',
            headers={
                hdrs.WWW_AUTHENTICATE: 'Basic realm="%s"' % self.realm,
                hdrs.CONTENT_TYPE: 'text/html; charset=utf-8',
                hdrs.CONNECTION: 'keep-alive'
            }
        )

    async def __call__(self, request, handler):
        if await self.authenticate(request):
            return await handler(request)
        else:
            return self.challenge()
