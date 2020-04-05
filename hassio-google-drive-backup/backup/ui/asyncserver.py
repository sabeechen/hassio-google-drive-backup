import asyncio
import ssl
import json
from datetime import timedelta
from os.path import abspath, join
from typing import Any, Dict
from urllib.parse import quote

import aiofiles
from aiohttp import BasicAuth, hdrs, web, ClientSession
from aiohttp.web import HTTPBadRequest, HTTPException, Request
from injector import ClassAssistedBuilder, inject, singleton

from backup.config import Config, Setting, CreateOptions, BoolValidator, Startable
from backup.const import SOURCE_GOOGLE_DRIVE, SOURCE_HA
from backup.model import Coordinator, Snapshot
from backup.exceptions import KnownError, ensureKey
from backup.util import GlobalInfo, Estimator, Color, File
from backup.ha import HaSource, PendingSnapshot, SNAPSHOT_NAME_KEYS, HaRequests
from backup.ha import Password
from backup.time import Time
from backup.worker import Trigger
from backup.logger import getLogger, getHistory
from backup.creds import Exchanger, MANUAL_CODE_REDIRECT_URI, Creds

from .debug import Debug

logger = getLogger(__name__)

# Used to Google's oauth verification
SCOPE: str = 'https://www.googleapis.com/auth/drive.file'


@singleton
class AsyncServer(Trigger, Startable):
    @inject
    def __init__(self, debug: Debug, coord: Coordinator, ha_source: HaSource, harequests: HaRequests,
                 time: Time, config: Config, global_info: GlobalInfo, estimator: Estimator,
                 session: ClientSession, exchanger_builder: ClassAssistedBuilder[Exchanger]):
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

    def name(self):
        return "UI Server"

    async def getstatus(self, request) -> Dict[Any, Any]:
        status: Dict[Any, Any] = {}
        status['folder_id'] = self._global_info.drive_folder_id
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
        status['free_space'] = Estimator.asSizeString(self._estimator.getBytesFree())
        next = self._coord.nextSnapshotTime()
        if next is None:
            status['next_snapshot'] = "Disabled"
        elif (next < self._time.now()):
            status['next_snapshot'] = self._time.formatDelta(self._time.now())
        else:
            status['next_snapshot'] = self._time.formatDelta(next)

        if len(snapshots) > 0:
            latest = snapshots[len(snapshots) - 1].date()
            status['last_snapshot'] = self._time.formatDelta(latest)
        else:
            status['last_snapshot'] = "Never"

        status['last_error'] = None
        if self._global_info._last_error is not None and self._global_info.isErrorSuppressed():
            status['last_error'] = self.processError(
                self._global_info._last_error)
        status["last_error_count"] = self._global_info.failureCount()
        status["ignore_errors_for_now"] = self._global_info.ignoreErrorsForNow()
        status["syncing"] = self._coord.isSyncing()
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
            'date': snapshot.date().isoformat(),
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
                    redirect_uri=MANUAL_CODE_REDIRECT_URI)
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
                # TODO: this redirects back to the reauth page if user already has drive creds!
                return web.json_response({'auth_url': "index"})
            except Exception as e:
                return web.json_response({'error': "Couldn't create authorization URL, Google said:" + str(e)})
        raise HTTPBadRequest()

    async def snapshot(self, request: Request) -> Any:
        custom_name = request.query.get("custom_name", None)
        retain_drive = BoolValidator.strToBool(request.query.get("retain_drive", False))
        retain_ha = BoolValidator.strToBool(request.query.get("retain_ha", False))
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
        use_existing = BoolValidator.strToBool(request.query.get("use_existing", False))
        self._global_info.resolveFolder(use_existing)
        self._global_info.suppressError()
        self._coord._model.dest.resetFolder()
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
        catchup = BoolValidator.strToBool(request.query.get("catchup", "False"))

        if not catchup:
            self.last_log_index = 0
        if format == "view":
            return web.FileResponse(self.filePath("logs.html"))

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
            self._coord.saveCreds(Creds.load(self._time, json.loads(request.query['creds'])))
        try:
            if request.url.port == self.config.get(Setting.INGRESS_PORT):
                return await self.redirect(self._ha_source.getAddonUrl())
        except:  # noqa: E722
            # eat the error
            pass
        return await self.redirect("/")

    async def changefolder(self, request: Request) -> None:
        id = request.query.get("id", None)
        self._coord._model.dest.changeBackupFolder(id)
        self._global_info.setIngoreErrorsForNow(True)
        self.trigger()
        try:
            if request.url.port == self.config.get(Setting.INGRESS_PORT):
                return await self.redirect(self._ha_source.getAddonUrl())
        except:  # noqa: E722
            # eat the error
            pass
        return await self.redirect("/")

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
            'snapshot_folder': self._coord._model.dest._folderId,
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

    async def saveconfig(self, request: Request) -> Any:
        data = await request.json()
        update = ensureKey("config", data, "the confgiuration update request")

        # validate the snapshot password
        Password(self.config.getConfigFor(update)).resolve()

        validated = self.config.validate(update)
        await self._updateConfiguration(validated, ensureKey("snapshot_folder", data, "the confgiuration update request"))
        return web.json_response({'message': 'Settings saved'})

    async def _updateConfiguration(self, new_config, snapshot_folder_id=None):
        update = {}
        for key in new_config:
            update[key.key()] = new_config[key]
        await self._harequests.updateConfig(update)

        was_specify = self.config.get(Setting.SPECIFY_SNAPSHOT_FOLDER)
        self.config.update(new_config)

        is_specify = self.config.get(Setting.SPECIFY_SNAPSHOT_FOLDER)

        if is_specify and not was_specify:
            # Delete the reset the saved backup folder, since the preference
            # for specifying the folder changed from false->true
            self._coord._model.dest.resetFolder()
        if self.config.get(Setting.SPECIFY_SNAPSHOT_FOLDER) and self._coord._model.dest.isCustomCreds() and snapshot_folder_id is not None:
            if len(snapshot_folder_id) > 0:
                self._coord._model.dest.changeBackupFolder(snapshot_folder_id)
            else:
                self._coord._model.dest.resetFolder()
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

    async def redirect(self, url):
        async with aiofiles.open(self.filePath("redirect.html"), mode='r') as f:
            contents = (await f.read(1024 * 1024 * 2)).replace("{url}", url)
        return web.Response(body=contents, content_type="text/html")

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
        self._addRoute(app, self.reauthenticate)
        self._addRoute(app, self.tos)
        self._addRoute(app, self.pp)
        self._addRoute(app, self.theme)

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

    def _addRoute(self, app, method):
        app.add_routes([
            web.get("/" + method.__name__, method),
            web.post("/" + method.__name__, method)
        ])

    async def start(self):
        await self.run()

    async def _start_site(self, app, port, ssl_context=None):
        runner = web.AppRunner(app)
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
                logger.error("Error while trying to shut down server: " + str(e))
            try:
                await runner.cleanup()
            except Exception as e:
                logger.error("Error while trying to shut down server: " + str(e))
        self.runners = []

    async def shutdown(self):
        await self.stop()

    @web.middleware
    async def error_middleware(self, request, handler):
        try:
            return await handler(request)
        except Exception as ex:
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

    def filePath(self, name):
        return abspath(join(__file__, "..", "..", "static", name))

    def cssElement(self, selector, keys):
        ret = selector
        ret += " {\n"
        for key in keys:
            ret += "\t" + key + ": " + keys[key] + ";\n"
        ret += "}\n\n"
        return ret

    async def theme(self, request: Request):
        background = Color.parse(self.config.get(Setting.BACKGROUND_COLOR))
        accent = Color.parse(self.config.get(Setting.ACCENT_COLOR))

        text = background.textColor()
        accent_text = accent.textColor()
        link_accent = accent
        contrast_threshold = 4.5

        contrast = background.contrast(accent)
        if (contrast < contrast_threshold):
            # do some adjustment to make the UI more readable if the contrast is really bad
            scale = 1 - (contrast - 1) / (contrast_threshold - 1)
            link_accent = link_accent.tint(text, scale * 0.5)

        focus = accent.saturate(1.2)
        help = text.tint(background, 0.25)

        shadow1 = text.withAlpha(0.14)
        shadow2 = text.withAlpha(0.12)
        shadow3 = text.withAlpha(0.2)
        shadowbmc = background.withAlpha(0.2)
        bgshadow = "0 2px 2px 0 " + shadow1.toCss() + ", 0 3px 1px -2px " + \
            shadow2.toCss() + ", 0 1px 5px 0 " + shadow3.toCss()

        bg_modal = background.tint(text, 0.02)
        shadow_modal = "box-shadow: 0 24px 38px 3px " + shadow1.toCss() + ", 0 9px 46px 8px " + \
            shadow2.toCss() + ", 0 11px 15px -7px " + shadow3.toCss()

        ret = ""
        ret += self.cssElement("html", {
            'background-color': background.toCss(),
            'color': text.toCss()
        })

        ret += self.cssElement("label", {
            'color': text.toCss()
        })

        ret += self.cssElement("a", {
            'color': link_accent.toCss()
        })

        ret += self.cssElement("input", {
            'color': text.toCss()
        })

        ret += self.cssElement(".helper-text", {
            'color': help.toCss()
        })

        ret += self.cssElement(".ha-blue", {
            'background-color': accent.toCss(),
            'color': accent_text.toCss()
        })

        ret += self.cssElement("nav .brand-logo", {
            'color': accent_text.toCss()
        })

        ret += self.cssElement("nav ul a", {
            'color': accent_text.toCss()
        })

        ret += self.cssElement(".accent-title", {
            'color': accent_text.toCss()
        })

        ret += self.cssElement("footer a:link", {
            'text-decoration': 'underline',
            'color': accent_text.textColor().tint(accent_text, 0.95).toCss()
        })

        ret += self.cssElement(".accent-text", {
            'color': accent_text.textColor().tint(accent_text, 0.95).toCss()
        })

        ret += self.cssElement(".btn", {
            'background-color': accent.toCss()
        })

        ret += self.cssElement(".btn:hover, .btn-large:hover, .btn-small:hover", {
            'background-color': accent.toCss(),
            'color': accent_text.toCss()
        })

        ret += self.cssElement(".btn:focus, .btn-large:focus, .btn-small:focus, .btn-floating:focus", {
            'background-color': focus.toCss(),
        })

        ret += self.cssElement(".modal .modal-footer .btn, .modal .modal-footer .btn-large, .modal .modal-footer .btn-small, .modal .modal-footer .btn-flat", {
            'margin': '6px 0',
            'background-color': accent.toCss(),
            'color': accent_text.toCss()
        })

        ret += self.cssElement(".dropdown-content", {
            'background-color': background.toCss(),
            'box-shadow': bgshadow,
            'webkit-box-shadow': bgshadow,
        })

        ret += self.cssElement(".dropdown-content li > a", {
            'color': text.tint(background, 0.5).toCss()
        })

        ret += self.cssElement(".modal", {
            'background-color': bg_modal.toCss(),
            'box-shadow': shadow_modal
        })

        ret += self.cssElement(".modal .modal-footer", {
            'background-color': bg_modal.toCss()
        })

        ret += self.cssElement(".modal.modal-fixed-footer .modal-footer", {
            'border-top': '1px solid ' + text.withAlpha(0.1).toCss()
        })

        ret += self.cssElement(".modal-overlay", {
            'background': text.toCss()
        })

        ret += self.cssElement("[type=\"checkbox\"].filled-in:checked + span:not(.lever)::before", {
            'border-right': '2px solid ' + text.toCss(),
            'border-bottom': '2px solid ' + text.toCss()
        })

        ret += self.cssElement("[type=\"checkbox\"].filled-in:checked + span:not(.lever)::after", {
            'border': '2px solid ' + text.toCss(),
            'background-color': accent.darken(0.2).saturate(1.2).toCss()
        })

        ret += self.cssElement(".input-field .prefix.active", {
            'color': accent.toCss()
        })

        ret += self.cssElement(".input-field > label", {
            'color': help.toCss()
        })

        ret += self.cssElement(".input-field .helper-text", {
            'color': help.toCss()
        })

        ret += self.cssElement("input:not([type]):focus:not([readonly]) + label, input[type=\"text\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"password\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"email\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"url\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"time\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"date\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"datetime\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"datetime-local\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"tel\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"number\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"search\"]:not(.browser-default):focus:not([readonly]) + label, textarea.materialize-textarea:focus:not([readonly]) + label", {
            'color': text.toCss()
        })

        ret += self.cssElement("input.valid:not([type]), input.valid:not([type]):focus, input[type=\"text\"].valid:not(.browser-default), input[type=\"text\"].valid:not(.browser-default):focus, input[type=\"password\"].valid:not(.browser-default), input[type=\"password\"].valid:not(.browser-default):focus, input[type=\"email\"].valid:not(.browser-default), input[type=\"email\"].valid:not(.browser-default):focus, input[type=\"url\"].valid:not(.browser-default), input[type=\"url\"].valid:not(.browser-default):focus, input[type=\"time\"].valid:not(.browser-default), input[type=\"time\"].valid:not(.browser-default):focus, input[type=\"date\"].valid:not(.browser-default), input[type=\"date\"].valid:not(.browser-default):focus, input[type=\"datetime\"].valid:not(.browser-default), input[type=\"datetime\"].valid:not(.browser-default):focus, input[type=\"datetime-local\"].valid:not(.browser-default), input[type=\"datetime-local\"].valid:not(.browser-default):focus, input[type=\"tel\"].valid:not(.browser-default), input[type=\"tel\"].valid:not(.browser-default):focus, input[type=\"number\"].valid:not(.browser-default), input[type=\"number\"].valid:not(.browser-default):focus, input[type=\"search\"].valid:not(.browser-default), input[type=\"search\"].valid:not(.browser-default):focus, textarea.materialize-textarea.valid, textarea.materialize-textarea.valid:focus, .select-wrapper.valid > input.select-dropdown", {
            'border-bottom': '1px solid ' + accent.toCss(),
            ' -webkit-box-shadow': ' 0 1px 0 0 ' + accent.toCss(),
            'box-shadow': '0 1px 0 0 ' + accent.toCss()
        })

        ret += self.cssElement("input:not([type]):focus:not([readonly]), input[type=\"text\"]:not(.browser-default):focus:not([readonly]), input[type=\"password\"]:not(.browser-default):focus:not([readonly]), input[type=\"email\"]:not(.browser-default):focus:not([readonly]), input[type=\"url\"]:not(.browser-default):focus:not([readonly]), input[type=\"time\"]:not(.browser-default):focus:not([readonly]), input[type=\"date\"]:not(.browser-default):focus:not([readonly]), input[type=\"datetime\"]:not(.browser-default):focus:not([readonly]), input[type=\"datetime-local\"]:not(.browser-default):focus:not([readonly]), input[type=\"tel\"]:not(.browser-default):focus:not([readonly]), input[type=\"number\"]:not(.browser-default):focus:not([readonly]), input[type=\"search\"]:not(.browser-default):focus:not([readonly]), textarea.materialize-textarea:focus:not([readonly])", {
            'border-bottom': '1px solid ' + accent.toCss(),
            '-webkit-box-shadow': '0 1px 0 0 ' + accent.toCss(),
            'box-shadow': '0 1px 0 0 ' + accent.toCss()
        })

        ret += self.cssElement(".card", {
            'background-color': background.toCss(),
            'box-shadow': "0 2px 2px 0 " + shadow1.toCss() + ", 0 3px 1px -2px " + shadow2.toCss() + ", 0 1px 5px 0 " + shadow3.toCss()
        })

        ret += self.cssElement("nav a", {
            'color': accent_text.toCss()
        })

        ret += self.cssElement(".btn, .btn-large, .btn-small", {
            'color': accent_text.toCss()
        })

        ret += self.cssElement(".bmc-button img", {
            'width': '15px',
            'margin-bottom': '1px',
            'box-shadow': 'none',
            'border': 'none',
            'vertical-align': 'middle'
        })

        ret += self.cssElement(".bmc-button", {
            'line-height': '15px',
            'height': '25px',
            'text-decoration': 'none',
            'display': 'inline-flex',
            'background-color': background.toCss(),
            'border-radius': '3px',
            'border': '1px solid transparent',
            'padding': '3px 2px 3px 2px',
            'letter-spacing': '0.6px',
            'box-shadow': '0px 1px 2px ' + shadowbmc.toCss(),
            '-webkit-box-shadow': '0px 1px 2px 2px ' + shadowbmc.toCss(),
            'margin': '0 auto',
            'font-family': "'Cookie', cursive",
            '-webkit-box-sizing': 'border-box',
            'box-sizing': 'border-box',
            '-o-transition': '0.3s all linear',
            '-webkit-transition': '0.3s all linear',
            '-moz-transition': '0.3s all linear',
            '-ms-transition': '0.3s all linear',
            'transition': '0.3s all linear',
            'font-size': '17px'
        })

        ret += self.cssElement(".bmc-button span", {'color': text.toCss()})

        return web.Response(text=ret, content_type='text/css')

    async def index(self, request: Request):
        if not self._coord.enabled():
            return web.FileResponse(self.filePath("index.html"), headers={'cache-control': 'no-store'})
        else:
            return web.FileResponse(self.filePath("working.html"), headers={'cache-control': 'no-store'})

    async def pp(self, request: Request):
        return web.FileResponse(self.filePath("privacy_policy.html"))

    async def tos(self, request: Request):
        return web.FileResponse(self.filePath("terms_of_service.html"))

    async def reauthenticate(self, request: Request) -> Any:
        return web.FileResponse(self.filePath("index.html"))


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
