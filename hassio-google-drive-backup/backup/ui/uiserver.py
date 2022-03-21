import asyncio
import ssl
import json
import aiohttp_jinja2
import jinja2
import base64
from datetime import timedelta
from os.path import abspath, join
from typing import Any, Dict

from aiohttp import BasicAuth, hdrs, web, ClientSession, ClientResponseError
from aiohttp.web import HTTPException, Request, HTTPSeeOther, HTTPNotFound
from injector import ClassAssistedBuilder, ProviderOf, inject, singleton

from backup.config import Config, Setting, CreateOptions, BoolValidator, Startable, Version, VERSION
from backup.const import SOURCE_GOOGLE_DRIVE, SOURCE_HA, GITHUB_BUG_TEMPLATE
from backup.model import Coordinator, Backup, AbstractBackup
from backup.exceptions import KnownError, GoogleCredGenerateError, ensureKey
from backup.util import GlobalInfo, Estimator, File, DataCache, UpgradeFlags
from backup.ha import HaSource, PendingBackup, BACKUP_NAME_KEYS, HaRequests, HaUpdater
from backup.ha import Password
from backup.time import Time
from backup.worker import Trigger
from backup.logger import getLogger, getHistory, TraceLogger
from backup.creds import Exchanger, Creds
from backup.debugworker import DebugWorker
from backup.drive import FolderFinder, AuthCodeQuery
from backup.const import FOLDERS
from .debug import Debug
from yarl import URL

logger = getLogger(__name__)

# Used to Google's oauth verification
SCOPE: str = 'https://www.googleapis.com/auth/drive.file'

MIME_TEXT_HTML = "text/html"
MIME_JSON = "application/json"
VERSION_CREATION_TRACKING = Version(0, 104, 0)


@singleton
class UiServer(Trigger, Startable):
    @inject
    def __init__(self, debug: Debug, coord: Coordinator, ha_source: HaSource, harequests: HaRequests,
                 time: Time, config: Config, global_info: GlobalInfo, estimator: Estimator,
                 session: ClientSession, exchanger_builder: ClassAssistedBuilder[Exchanger],
                 debug_worker: DebugWorker, folder_finder: FolderFinder, data_cache: DataCache,
                 haupdater: HaUpdater, custom_auth_provider: ProviderOf[AuthCodeQuery]):
        super().__init__()
        # Currently running server tasks
        self.runners = []
        self.exchanger_builder = exchanger_builder
        self._coord = coord
        self._time = time
        self.custom_auth_provider = custom_auth_provider
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
        self.ignore_other_turned_on = False
        self._data_cache = data_cache
        self._haupdater = haupdater
        self._check_creds_loop: asyncio.Task = None
        self._check_creds_error: Exception = None
        self._device_code_authorizer: AuthCodeQuery = None
        self._upload_event = asyncio.Event()

    def name(self):
        return "UI Server"

    def base_context(self):
        return {
            'version': VERSION,
            'backgroundColor': self.config.get(Setting.BACKGROUND_COLOR),
            'accentColor': self.config.get(Setting.ACCENT_COLOR),
            'coordEnabled': self._coord.enabled(),
            'save_drive_creds_path': self.config.get(Setting.SAVE_DRIVE_CREDS_PATH),
            'bmc_logo_path': "static/" + VERSION + "/images/bmc.svg"
        }

    async def getstatus(self, request) -> Dict[Any, Any]:
        return web.json_response(await self.buildStatusInfo())

    async def buildStatusInfo(self):
        status: Dict[Any, Any] = {}
        status['folder_id'] = self.folder_finder.getCachedFolder()
        status['backups'] = []
        backups = self._coord.backups()
        for backup in backups:
            status['backups'].append(self.getBackupDetails(backup))
        status['ha_url_base'] = self._ha_source.getHomeAssistantUrl()
        status['restore_backup_path'] = "hassio/backups"
        status['ask_error_reports'] = not self.config.isExplicit(
            Setting.SEND_ERROR_REPORTS)
        status['warn_ingress_upgrade'] = False
        status['cred_version'] = self._global_info.credVersion
        next = self._coord.nextBackupTime()
        if next is None:
            status['next_backup_text'] = "Disabled"
            status['next_backup_machine'] = ""
            status['next_backup_detail'] = "Disabled"
        elif (next < self._time.now()):
            status['next_backup_text'] = self._time.formatDelta(
                self._time.now())
            status['next_backup_machine'] = self._time.asRfc3339String(
                self._time.now())
            status['next_backup_detail'] = self._time.toLocal(
                self._time.now()).strftime("%c")
        else:
            status['next_backup_text'] = self._time.formatDelta(next)
            status['next_backup_machine'] = self._time.asRfc3339String(next)
            status['next_backup_detail'] = self._time.toLocal(
                next).strftime("%c")
        not_ignored = list(filter(lambda s: not s.ignore(), self._coord.backups()))
        if len(not_ignored) > 0:
            latest = not_ignored[len(not_ignored) - 1].date()
            status['last_backup_text'] = self._time.formatDelta(latest)
            status['last_backup_machine'] = self._time.asRfc3339String(
                latest)
            status['last_backup_detail'] = self._time.toLocal(
                latest).strftime("%c")
        else:
            status['last_backup_text'] = "Never"
            status['last_backup_machine'] = ""
            status['last_backup_detail'] = "Never"

        status['last_error'] = None
        if self._global_info._last_error is not None and self._global_info.isErrorSuppressed():
            status['last_error'] = self.processError(
                self._global_info._last_error)
        status["last_error_count"] = self._global_info.failureCount()
        status["ignore_errors_for_now"] = self._global_info.ignoreErrorsForNow()
        status["syncing"] = self._coord.isSyncing()
        status["ignore_sync_error"] = self._coord.isWorkingThroughUpload()
        status["firstSync"] = self._global_info._first_sync
        status["backup_name_template"] = self.config.get(
            Setting.BACKUP_NAME)
        status['sources'] = self._coord.buildBackupMetrics()
        status['authenticate_url'] = str(URL(self.config.get(Setting.AUTHORIZATION_HOST)).with_path("/drive/authorize"))
        choose_url = str(URL(self.config.get(Setting.AUTHORIZATION_HOST)).with_path('/drive/picker').with_query({
            "bg": self.config.get(Setting.BACKGROUND_COLOR),
            "ac": self.config.get(Setting.ACCENT_COLOR),
            "version": VERSION
        }))
        status['choose_folder_url'] = str(choose_url)
        status['dns_info'] = self._global_info.getDnsInfo()
        status['enable_drive_upload'] = self.config.get(
            Setting.ENABLE_DRIVE_UPLOAD)
        status['is_custom_creds'] = self._coord._model.dest.isCustomCreds()
        status['is_specify_folder'] = self.config.get(
            Setting.SPECIFY_BACKUP_FOLDER)
        status['backup_cooldown_active'] = self._coord.isWaitingForStartup()
        name_keys = {}
        for key in BACKUP_NAME_KEYS:
            name_keys[key] = BACKUP_NAME_KEYS[key](
                "Full", self._time.now(), self._ha_source.getHostInfo())
        status['backup_name_keys'] = name_keys

        # Indicate the user should be notified for a specific situation where:
        #  - They recently turned on "IGNORE_OTHER_BACKUPS"
        #  - They have ignored backups created before upgrading to v0.104.0 or higher.
        upgrade_date = self._data_cache.getUpgradeTime(VERSION_CREATION_TRACKING)
        ignored = len(list(filter(lambda s: s.date() < upgrade_date, filter(Backup.ignore, self._coord.backups()))))
        status["notify_check_ignored"] = ignored > 0 and self.ignore_other_turned_on
        status["warn_backup_upgrade"] = self.config.get(Setting.CALL_BACKUP_SNAPSHOT) and not self._data_cache.checkFlag(UpgradeFlags.NOTIFIED_ABOUT_BACKUP_RENAME)
        return status

    async def bootstrap(self, request) -> Dict[Any, Any]:
        return web.Response(body="bootstrap_update_data = {0};".format(json.dumps(await self.buildStatusInfo(), indent=4)), content_type="text/javascript")

    def getBackupDetails(self, backup: Backup):
        ha = backup.getSource(SOURCE_HA)
        sources = []
        for source_key in backup.sources:
            source: AbstractBackup = backup.sources[source_key]
            sources.append({
                'name': source.name(),
                'key': source_key,
                'size': source.size(),
                'retained': source.retained(),
                'delete_next': backup.getPurges().get(source_key) or False,
                'slug': backup.slug(),
                'ignored': source.ignore(),
            })

        return {
            'name': backup.name(),
            'slug': backup.slug(),
            'size': backup.sizeString(),
            'status': backup.status(),
            'date': self._time.toLocal(backup.date()).strftime("%c"),
            'createdAt': self._time.formatDelta(backup.date()),
            'isPending': ha is not None and type(ha) is PendingBackup,
            'protected': backup.protected(),
            'type': backup.backupType(),
            'folders': backup.details().get("folders", []),
            'addons': self.formatAddons(backup.details()),
            'sources': sources,
            'haVersion': backup.version(),
            'uploadable': backup.getSource(SOURCE_HA) is None and len(backup.sources) > 0,
            'restorable': backup.getSource(SOURCE_HA) is not None,
            'status_detail': backup.getStatusDetail(),
            'upload_info': backup.getUploadInfo(self._time),
            'ignored': backup.ignore(),
            'timestamp': backup.date().timestamp(),
        }

    def formatAddons(self, backup_data):
        addons = []
        for addon in backup_data.get("addons", []):
            addons.append({
                'name': addon.get('name', "Unknown"),
                'slug': addon.get("slug", "unknown"),
                'version': addon.get("version", ""),
                # The supervisor stores backup size in MB
                'size': self._estimator.asSizeString(float(addon.get("size", 0)) * 1024 * 1024),
            })
        return addons

    async def manualCredCheckLoop(self, auth: AuthCodeQuery):
        try:
            creds = await auth.waitForPermission()
            self._coord.saveCreds(creds)
        except asyncio.CancelledError:
            # Cancelled, thats fine
            pass
        except Exception as e:
            self._check_creds_error = e

    async def checkManualAuth(self, request: Request):
        if self._check_creds_error is not None:
            raise self._check_creds_error
        elif self._device_code_authorizer is not None:
            return web.json_response({
                'message': "Waiting for you to authorize the add-on.",
                'auth_url': self._device_code_authorizer.verification_url,
                'code': self._device_code_authorizer.user_code,
                'expires': self._time.formatDelta(self._device_code_authorizer.expiration)
            })
        else:
            return web.json_response({
                'message': "No request for authorization is in progress."
            })

    async def manualauth(self, request: Request) -> None:
        client_id = request.query.get("client_id", "")
        client_secret = request.query.get("client_secret", "")
        if client_id == "" or client_secret == "":
            raise GoogleCredGenerateError("Invalid information provided")

        if self._check_creds_loop is not None and not self._check_creds_loop.done():
            self._check_creds_loop.cancel()
            await self._check_creds_loop
        self._device_code_authorizer = self.custom_auth_provider.get()
        await self._device_code_authorizer.requestCredentials(client_id, client_secret)
        self._check_creds_error = None
        self._check_creds_loop = asyncio.create_task(self.manualCredCheckLoop(self._device_code_authorizer))
        return web.json_response({
            'auth_url': self._device_code_authorizer.verification_url,
            'code': self._device_code_authorizer.user_code,
            'expires': self._time.formatDelta(self._device_code_authorizer.expiration),
        })

    async def backup(self, request: Request) -> Any:
        custom_name = request.query.get("custom_name", None)
        retain_drive = BoolValidator.strToBool(
            request.query.get("retain_drive", False))
        retain_ha = BoolValidator.strToBool(
            request.query.get("retain_ha", False))
        options = CreateOptions(self._time.now(), custom_name, {
            SOURCE_GOOGLE_DRIVE: retain_drive,
            SOURCE_HA: retain_ha
        })
        backup = await self._coord.startBackup(options)
        return web.json_response({"message": "Requested backup '{0}'".format(backup.name())})

    async def deleteSnapshot(self, request: Request):
        data = await request.json()
        # Check to make sure the slug is valid.
        self._coord.getBackup(data['slug'])
        await self._coord.delete(data['sources'], data['slug'])
        return web.json_response({"message": "Deleted from {0} place(s)".format(len(data['sources']))})

    async def ignore(self, request: Request):
        data = await request.json()
        # Check to make sure the slug is valid.
        backup = self._coord.getBackup(data['slug'])
        await self._coord.ignore(data['slug'], data['ignore'])
        await self.startSync(request)
        if data['ignore']:
            return web.json_response({"message": "'{0}' will be ignored.".format(backup.name())})
        else:
            return web.json_response({"message": "'{0}' will be included.".format(backup.name())})

    async def retain(self, request: Request):
        data = await request.json()
        slug = data['slug']

        self._coord.getBackup(slug)
        await self._coord.retain(data['sources'], slug)
        return web.json_response({'message': "Updated the backup's settings"})

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
            return web.json_response({'message': 'Backups deleted this one time'})

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
        self._global_info.setIngoreErrorsForNow(True)
        creds_deserialized = json.loads(str(base64.b64decode(request.query.get('creds').encode("utf-8")), 'utf-8'))
        creds = Creds.load(self._time, creds_deserialized)
        self._coord.saveCreds(creds)

        # Build the redirect url
        if 'host' in request.query:
            redirect = request.query.get('host')
        else:
            redirect = self._ha_source.getAddonUrl()
        if MIME_JSON in request.headers[hdrs.ACCEPT]:
            return web.json_response({'redirect': str(redirect)})
        else:
            raise HTTPSeeOther(redirect)

    async def changefolder(self, request: Request) -> None:
        # update config to specify backup folder
        await self._updateConfiguration(self.config.validateUpdate({Setting.SPECIFY_BACKUP_FOLDER: True}))

        id = request.query.get("id", None)
        await self.folder_finder.save(id)
        self._global_info.setIngoreErrorsForNow(True)
        self.trigger()
        return web.json_response({})

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
        current_config = {}
        for setting in Setting:
            current_config[setting.key()] = self.config.getForUi(setting)
        default_config = {}
        for setting in Setting:
            default_config[setting.key()] = setting.default()
        return web.json_response({
            'config': current_config,
            'addons': self._global_info.addons,
            'folders': FOLDERS,
            'defaults': default_config,
            'backup_folder': self.folder_finder.getCachedFolder(),
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

    async def callbackupsnapshot(self, request: Request):
        switch = BoolValidator.strToBool(request.query.get("switch", False))

        if switch:
            validated = self.config.validateUpdate({Setting.CALL_BACKUP_SNAPSHOT: False})
            await self._updateConfiguration(validated)
            self._data_cache.addFlag(UpgradeFlags.NOTIFIED_ABOUT_BACKUP_RENAME)
        self._data_cache.addFlag(UpgradeFlags.NOTIFIED_ABOUT_BACKUP_RENAME)
        self._data_cache.saveIfDirty()
        return web.json_response({'message': 'Configuration updated'})

    async def ignorestartupcooldown(self, request: Request):
        self._coord.ignoreStartupDelay()
        return await self.sync(request)

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
        update = ensureKey("config", data, "the configuration update request")

        # validate the backup password
        Password(self.config.getConfigFor(update)).resolve()

        validated, needUpdate = self.config.validate(update)
        message = await self._updateConfiguration(validated, ensureKey("backup_folder", data, "the configuration update request"), trigger=False)
        try:
            await self.cancelSync(request)
            await self.startSync(request)
        except:  # noqa: E722
            # eat the error, just cancel optimistically
            pass
        return web.json_response(message)

    async def ackignorecheck(self, request: Request):
        self.ignore_other_turned_on = False
        return web.json_response({'message': "Acknowledged."})

    async def _updateConfiguration(self, new_config, backup_folder_id=None, trigger=True):
        update = {}
        for key in new_config:
            update[key.key()] = new_config[key]
        old_drive_option = self.config.get(Setting.ENABLE_DRIVE_UPLOAD)
        old_ignore_others_option = self.config.get(Setting.IGNORE_OTHER_BACKUPS)
        await self._harequests.updateConfig(update)

        self.config.update(new_config)

        if not old_ignore_others_option and self.config.get(Setting.IGNORE_OTHER_BACKUPS):
            self.ignore_other_turned_on = True
        self._haupdater.triggerRefresh()
        if self.config.get(Setting.SPECIFY_BACKUP_FOLDER) and backup_folder_id is not None and len(backup_folder_id):
            await self.folder_finder.save(backup_folder_id)
        if trigger:
            self.trigger()
        return {
            'message': 'Settings saved',
            'reload_page': self.config.get(Setting.ENABLE_DRIVE_UPLOAD) != old_drive_option
        }

    async def waitForUpload(self):
        await self._upload_event.wait()

    async def _doUpload(self, slug):
        await self._coord.uploadBackups(slug)
        self._upload_event.set()

    async def upload(self, request: Request):
        slug = request.query.get("slug", "")
        asyncio.create_task(self._doUpload(slug))
        return web.json_response({'message': "Uploading backup in the background"})

    async def redirect(self, request, url):
        context = {
            **self.base_context(),
            'url': url
        }
        return aiohttp_jinja2.render_template("redirect.jinja2",
                                              request,
                                              context)

    async def addonLogo(self, request: Request):
        slug = request.match_info.get('slug')
        if not self._ha_source.addonHasLogo(slug):
            raise HTTPNotFound()
        try:
            (content_type, data) = await self._harequests.getAddonLogo(slug)
            return web.Response(headers={hdrs.CONTENT_TYPE: content_type}, body=data)
        except ClientResponseError as e:
            return web.Response(status=e.status)

    async def download(self, request: Request):
        slug = request.query.get("slug", "")
        backup = self._coord.getBackup(slug)
        stream = await self._coord.download(slug)
        await stream.setup()
        resp = web.StreamResponse()
        resp.content_type = 'application/tar'
        resp.headers['Content-Disposition'] = 'attachment; filename="{}.tar"'.format(
            backup.name())
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
            [web.static('/static/' + VERSION, abspath(join(__file__, "..", "..", "static")), append_version=True)])
        app.add_routes([web.get('/', self.index)])
        app.add_routes([web.get('/index.html', self.index)])
        app.add_routes([web.get('/index', self.index)])
        app.add_routes([web.get('/favicon.ico', self.favicon)])
        app.add_routes([web.get('/logo/{slug}', self.addonLogo)])
        self._addRoute(app, self.reauthenticate)
        self._addRoute(app, self.bootstrap)
        self._addRoute(app, self.tos)
        self._addRoute(app, self.pp)

        self._addRoute(app, self.getstatus)
        self._addRoute(app, self.backup)
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
        self._addRoute(app, self.ignorestartupcooldown)
        self._addRoute(app, self.callbackupsnapshot)
        self._addRoute(app, self.ignore)
        self._addRoute(app, self.ackignorecheck)
        self._addRoute(app, self.checkManualAuth)

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
            if isinstance(ex, HTTPException):
                raise
            logger.error("Error serving %s %s", request.method, request.url)
            logger.error(logger.formatException(ex))
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
                'navBarTitle': 'Backups'
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

    async def favicon(self, request: Request):
        return web.FileResponse(abspath(join(__file__, "..", "..", "static", "images", "favicon.png")))

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
