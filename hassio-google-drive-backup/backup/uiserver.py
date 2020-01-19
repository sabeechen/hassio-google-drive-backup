import os.path
import os
import cherrypy
import logging

from datetime import timedelta
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.client import OAuth2Credentials
from .helpers import formatTimeSince
from .helpers import formatException
from .helpers import strToBool
from .helpers import touch, asSizeString
from .exceptions import ensureKey
from .config import Config
from .snapshotname import SNAPSHOT_NAME_KEYS
from .exceptions import KnownError
from .logbase import LogBase
from typing import Dict, Any
from .model import CreateOptions
from .time import Time
from pathlib import Path
from .coordinator import Coordinator
from .const import SOURCE_GOOGLE_DRIVE, SOURCE_HA
from .harequests import HaRequests
from .hasource import PendingSnapshot, HaSource
from .snapshots import Snapshot
from .globalinfo import GlobalInfo
from .password import Password
from .trigger import Trigger
from .settings import Setting
from .color import Color
from .estimator import Estimator
from os.path import join, abspath
from urllib.parse import quote

# Used to Google's oauth verification
SCOPE: str = 'https://www.googleapis.com/auth/drive.file'
MANUAL_CODE_REDIRECT_URI: str = "urn:ietf:wg:oauth:2.0:oob"


class UIServer(Trigger, LogBase):
    def __init__(self, coord: Coordinator, ha_source: HaSource, harequests: HaRequests, time: Time, config: Config, global_info: GlobalInfo, estimator: Estimator):
        super().__init__()
        self._coord = coord
        self._time = time
        self.oauth_flow_manual: OAuth2WebServerFlow = None
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

    def name(self):
        return "UI Server"

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getstatus(self) -> Dict[Any, Any]:
        return self.handleError(self._getstatus)

    def _getstatus(self) -> Dict[Any, Any]:
        status: Dict[Any, Any] = {}
        status['folder_id'] = self._global_info.drive_folder_id
        status['snapshots'] = []
        snapshots = self._coord.snapshots()
        for snapshot in snapshots:
            status['snapshots'].append(self.getSnapshotDetails(snapshot))
        status['restore_link'] = self._ha_source.getFullRestoreLink()
        status['drive_enabled'] = self._coord.enabled()
        status['ask_error_reports'] = not self.config.isExplicit(Setting.SEND_ERROR_REPORTS)
        status['warn_ingress_upgrade'] = self._ha_source.runTemporaryServer()
        status['cred_version'] = self._global_info.credVersion
        status['free_space'] = asSizeString(self._estimator.getBytesFree())
        next = self._coord.nextSnapshotTime()
        if next is None:
            status['next_snapshot'] = "Disabled"
        elif (next < self._time.now()):
            status['next_snapshot'] = formatTimeSince(self._time.now(), self._time.now())
        else:
            status['next_snapshot'] = formatTimeSince(next, self._time.now())

        if len(snapshots) > 0:
            status['last_snapshot'] = formatTimeSince(snapshots[len(snapshots) - 1].date(), self._time.now())
        else:
            status['last_snapshot'] = "Never"

        status['last_error'] = None
        if self._global_info._last_error is not None and self._global_info.isErrorSuppressed():
            status['last_error'] = self.processError(self._global_info._last_error)
        status["firstSync"] = self._global_info._first_sync
        status["maxSnapshotsInHasssio"] = self.config.get(Setting.MAX_SNAPSHOTS_IN_HASSIO)
        status["maxSnapshotsInDrive"] = self.config.get(Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE)
        status["snapshot_name_template"] = self.config.get(Setting.SNAPSHOT_NAME)
        status['sources'] = self._coord.buildSnapshotMetrics()
        status['authenticate_url'] = self.config.get(Setting.AUTHENTICATE_URL)
        status['choose_folder_url'] = self.config.get(Setting.CHOOSE_FOLDER_URL) + "?bg={0}&ac={1}".format(quote(self.config.get(Setting.BACKGROUND_COLOR)), quote(self.config.get(Setting.ACCENT_COLOR)))
        status['dns_info'] = self._global_info.getDnsInfo()
        status['enable_drive_upload'] = self.config.get(Setting.ENABLE_DRIVE_UPLOAD)
        status['is_custom_creds'] = self._coord._model.dest.isCustomCreds()
        status['drive_client'] = self._coord._model.dest.drivebackend.cred_id
        status['is_specify_folder'] = self.config.get(Setting.SPECIFY_SNAPSHOT_FOLDER)
        return status

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

    @cherrypy.expose  # type: ignore
    @cherrypy.tools.json_out()
    def manualauth(self, code: str = "", client_id: str = "", client_secret: str = "") -> None:
        if client_id != "" and client_secret != "":
            try:
                # Redirect to the webpage that takes you to the google auth page.
                self.oauth_flow_manual = OAuth2WebServerFlow(
                    client_id=client_id.strip(),
                    client_secret=client_secret.strip(),
                    scope=SCOPE,
                    redirect_uri=MANUAL_CODE_REDIRECT_URI,
                    include_granted_scopes='true',
                    prompt='consent',
                    access_type='offline')
                return {
                    'auth_url': self.oauth_flow_manual.step1_get_authorize_url()
                }
            except Exception as e:
                return {
                    'error': "Couldn't create authorization URL, Google said:" + str(e)
                }
            raise cherrypy.HTTPError()
        elif code != "":
            try:
                self._coord.saveCreds(self.oauth_flow_manual.step2_exchange(code))
                return {
                    # TODO: this redirects back to the reauth page if user already has drive creds!
                    'auth_url': "index"
                }
            except Exception as e:
                return {
                    'error': "Couldn't create authorization URL, Google said:" + str(e)
                }
            raise cherrypy.HTTPError()

    def auth(self, realm: str, username: str, password: str) -> bool:
        if cherrypy.request.local.port == self.config.get(Setting.INGRESS_PORT):
            # Ingress port never requires auth
            return True

        if username in self.auth_cache and self.auth_cache[username]['password'] == password and self.auth_cache[username]['timeout'] > self._time.now():
            return True
        try:
            self._harequests.auth(username, password)
            self.auth_cache[username] = {'password': password, 'timeout': (self._time.now() + timedelta(minutes=10))}
            return True
        except Exception as e:
            self.error(formatException(e))
            return False

    def add_auth_header(self):
        # Basically a hack.  This lets us pretend that any request to the ingress server includes
        # a user/pass.  If the user has login turned on, this bypasses it for the ingress port.
        if cherrypy.request.local.port == self.config.get(Setting.INGRESS_PORT):
            cherrypy.request.headers['authorization'] = "basic MWfhZHRedjpPcRVuU2XzYW4l"

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def snapshot(self, custom_name=None, retain_drive=False, retain_ha=False) -> Any:
        return self.handleError(lambda: self._snapshot(custom_name, retain_drive, retain_ha))

    def _snapshot(self, custom_name=None, retain_drive=False, retain_ha=False) -> Any:
        options = CreateOptions(self._time.now(), custom_name, {
            SOURCE_GOOGLE_DRIVE: strToBool(retain_drive),
            SOURCE_HA: strToBool(retain_ha)
        })
        snapshot = self._coord.startSnapshot(options)
        return {"message": "Requested snapshot '{0}'".format(snapshot.name())}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def deleteSnapshot(self, slug: str, drive: str, ha: str) -> Any:
        return self.handleError(lambda: self._deleteSnapshot(slug, drive, ha))

    def _deleteSnapshot(self, slug: str, drive: str, ha: str) -> Any:
        self._coord.getSnapshot(slug)
        sources = []
        if strToBool(drive):
            sources.append(SOURCE_GOOGLE_DRIVE)
        if strToBool(ha):
            sources.append(SOURCE_HA)
        self._coord.delete(sources, slug)
        return {"message": "Its gone!"}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def retain(self, slug, drive, ha):
        return self.handleError(lambda: self._retain(slug, drive, ha))

    def _retain(self, slug, drive, ha):
        snapshot: Snapshot = self._coord.getSnapshot(slug)

        # override create options for future uploads
        options = CreateOptions(self._time.now(), self.config.get(Setting.SNAPSHOT_NAME), {
            SOURCE_GOOGLE_DRIVE: strToBool(drive),
            SOURCE_HA: strToBool(ha)
        })
        snapshot.setOptions(options)

        retention = {}
        if snapshot.getSource(SOURCE_GOOGLE_DRIVE) is not None:
            retention[SOURCE_GOOGLE_DRIVE] = strToBool(drive)
        if snapshot.getSource(SOURCE_HA) is not None:
            retention[SOURCE_HA] = strToBool(ha)
        self._coord.retain(retention, slug)
        return {
            'message': "Updated the snapshot's settings"
        }

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def resolvefolder(self, use_existing=False):
        return self.handleError(lambda: self._resolvefolder(strToBool(use_existing)))

    def _resolvefolder(self, use_existing: bool):
        self._global_info.resolveFolder(use_existing)
        self._global_info.suppressError()
        self._coord._model.dest.resetFolder()
        self.sync()
        return {'message': 'Done'}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def skipspacecheck(self):
        return self.handleError(lambda: self._skipspacecheck())

    def _skipspacecheck(self):
        self._global_info.setSkipSpaceCheckOnce(True)
        self.sync()
        return {'message': 'Done'}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def confirmdelete(self, always=False):
        return self.handleError(lambda: self._confirmdelete(always))

    def _confirmdelete(self, always) -> Any:
        self._global_info.allowMultipleDeletes()
        if strToBool(always):
            validated = self.config.validateUpdate({"confirm_multiple_deletes": False})
            self._updateConfiguration(validated)
            self.sync()
            return {'message': 'Configuration updated, I\'ll never ask again'}
        else:
            self.sync()
            return {'message': 'Snapshots deleted this one time'}

    @cherrypy.expose
    def log(self, format="download", catchup=False) -> Any:
        if not catchup:
            self.last_log_index = 0
        if format == "view":
            return open(self.filePath("logs.html"))
        if format == "html":
            cherrypy.response.headers['Content-Type'] = 'text/html'
        else:
            cherrypy.response.headers['Content-Type'] = 'text/plain'
            cherrypy.response.headers['Content-Disposition'] = 'attachment; filename="hassio-google-drive-backup.log"'

        def content():
            html = format == "colored"
            if format == "html":
                yield "<html><head><title>Hass.io Google Drive Backup Log</title></head><body><pre>\n"
            for line in LogBase.getHistory(self.last_log_index, html):
                self.last_log_index = line[0]
                if line:
                    yield line[1].replace("\n", "   \n") + "\n"
            if format == "html":
                yield "</pre></body>\n"
        return content()

    @cherrypy.expose
    def token(self, **kwargs: Dict[str, Any]) -> None:
        if 'creds' in kwargs:
            creds = OAuth2Credentials.from_json(kwargs['creds'])
            self._coord.saveCreds(creds)
        try:
            if cherrypy.request.local.port == self.config.get(Setting.INGRESS_PORT):
                return self.redirect(self._ha_source.getAddonUrl())
        except:  # noqa: E722
            # eat the error
            pass
        return self.redirect("/")

    @cherrypy.expose
    def changefolder(self, id: str) -> None:
        self._coord._model.dest.changeBackupFolder(id)
        self.trigger()
        try:
            if cherrypy.request.local.port == self.config.get(Setting.INGRESS_PORT):
                return self.redirect(self._ha_source.getAddonUrl())
        except:  # noqa: E722
            # eat the error
            pass
        return self.redirect("/")

    @cherrypy.expose
    def simerror(self, error: str = "") -> None:
        if len(error) == 0:
            self._coord._model.simulate_error = None
        else:
            self._coord._model.simulate_error = error
        self.trigger()

    @cherrypy.expose
    def index(self) -> Any:
        if not self._coord.enabled():
            return open(self.filePath("index.html"))
        else:
            return open(self.filePath("working.html"))

    @cherrypy.expose
    def pp(self):
        return open(self.filePath("privacy_policy.html"))

    @cherrypy.expose
    def tos(self):
        return open(self.filePath("terms_of_service.html"))

    @cherrypy.expose
    def reauthenticate(self) -> Any:
        return open(self.filePath("index.html"))

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def sync(self) -> Any:
        return self.handleError(lambda: self._sync())

    def _sync(self) -> Any:
        self._coord.sync()
        return self._getstatus()

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getconfig(self) -> Any:
        return self.handleError(lambda: self._getconfig())

    def _getconfig(self) -> Any:
        self._ha_source.refresh()
        name_keys = {}
        for key in SNAPSHOT_NAME_KEYS:
            name_keys[key] = SNAPSHOT_NAME_KEYS[key]("Full", self._time.now(), self._ha_source.host_info)
        current_config = {}
        for setting in Setting:
            current_config[setting.key()] = self.config.get(setting)
        default_config = {}
        for setting in Setting:
            default_config[setting.key()] = setting.default()
        return {
            'config': current_config,
            'addons': self._global_info.addons,
            'name_keys': name_keys,
            'defaults': default_config,
            'snapshot_folder': self._coord._model.dest._folderId,
            'is_custom_creds': self._coord._model.dest.isCustomCreds()
        }

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def errorreports(self, send: str) -> None:
        return self.handleError(lambda: self._errorreports(send))

    def _errorreports(self, send: str) -> None:
        update = {
            "send_error_reports": strToBool(send)
        }
        validated = self.config.validateUpdate(update)
        self._updateConfiguration(validated)
        return {'message': 'Configuration updated'}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def exposeserver(self, expose: str) -> None:
        return self.handleError(lambda: self._exposeserver(expose))

    def _exposeserver(self, expose: str) -> None:
        if expose == "true":
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
        self._updateConfiguration(validated)

        touch(self.config.get(Setting.INGRESS_TOKEN_FILE_PATH))
        self._ha_source.init()
        self.run()
        redirect = ""
        try:
            if cherrypy.request.local.port != self.config.get(Setting.INGRESS_PORT):
                redirect = self._ha_source.getFullAddonUrl()
        except:  # noqa: E722
            # eat the error
            pass
        return {
            'message': 'Configuration updated',
            'redirect': redirect
        }

    @cherrypy.expose
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    def saveconfig(self) -> Any:
        return self.handleError(lambda: self._saveconfig())

    def _saveconfig(self) -> Any:
        update = ensureKey("config", cherrypy.request.json, "the confgiuration update request")

        # validate the snapshot password
        Password(self.config.getConfigFor(update)).resolve()

        validated = self.config.validate(update)
        self._updateConfiguration(validated, ensureKey("snapshot_folder", cherrypy.request.json, "the confgiuration update request"))
        return {'message': 'Settings saved'}

    def _updateConfiguration(self, new_config, snapshot_folder_id=None):
        server_config_before = self._getServerOptions()

        update = {}
        for key in new_config:
            update[key.key()] = new_config[key]
        self._harequests.updateConfig(update)

        was_specify = self.config.get(Setting.SPECIFY_SNAPSHOT_FOLDER)
        self.config.update(new_config)

        is_specify = self.config.get(Setting.SPECIFY_SNAPSHOT_FOLDER)
        server_config_after = self._getServerOptions()
        if server_config_before != server_config_after:
            self.run()
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

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def upload(self, slug):
        return self.handleError(lambda: self._upload(slug))

    def _upload(self, slug):
        self._coord.uploadSnapshot(slug)
        return {'message': "Snapshot uploaded to Home Assistant"}

    @cherrypy.expose
    def redirect(self, url):
        return Path(self.filePath("redirect.html")).read_text().replace("{url}", url)

    @cherrypy.expose
    def download(self, slug):
        return self.handleError(lambda: self._download(slug))

    def _download(self, slug):
        snapshot = self._coord.getSnapshot(slug)
        stream = self._coord.download(slug)
        cherrypy.response.headers['Content-Type'] = 'application/tar'
        cherrypy.response.headers['Content-Disposition'] = 'attachment; filename="{}.tar"'.format(snapshot.name())
        cherrypy.response.headers['Content-Length'] = str(stream.size())
        return stream

    def run(self) -> None:
        self._starts += 1
        if self.running:
            self.info("Stopping server...")
            cherrypy.engine.stop()

        # unbind existing servers.
        if self.host_server is not None:
            self.host_server.unsubscribe()
            self.host_server = None

        cherrypy.tools.addauth = cherrypy.Tool('on_start_resource', self.add_auth_header)

        conf: Dict[Any, Any] = {
            'global': {
                'server.socket_port': self.config.get(Setting.INGRESS_PORT),
                'server.socket_host': '0.0.0.0',
                'engine.autoreload.on': False,
                'log.access_file': '',
                'log.error_file': '',
                'log.screen': False,
                'response.stream': True
            },
            "/": {
                'tools.addauth.on': True,
                'tools.staticdir.on': True,
                'tools.staticdir.dir': os.path.join(os.getcwd(), "www"),
                'tools.auth_basic.on': self.config.get(Setting.REQUIRE_LOGIN),
                'tools.auth_basic.realm': 'localhost',
                'tools.auth_basic.checkpassword': self.auth,
                'tools.auth_basic.accept_charset': 'UTF-8'
            }
        }

        self.info("Starting server on port {}".format(self.config.get(Setting.INGRESS_PORT)))

        cherrypy.config.update(conf)

        if self.config.get(Setting.EXPOSE_EXTRA_SERVER) or self._ha_source.runTemporaryServer():
            self.info("Starting server on port {}".format(self.config.get(Setting.PORT)))
            self.host_server = cherrypy._cpserver.Server()
            self.host_server.socket_port = self.config.get(Setting.PORT)
            self.host_server._socket_host = "0.0.0.0"
            self.host_server.subscribe()
            if self.config.get(Setting.USE_SSL):
                self.host_server.ssl_certificate = self.config.get(Setting.CERTFILE)
                self.host_server.ssl_private_key = self.config.get(Setting.KEYFILE)

        cherrypy.tree.mount(self, "/", conf)
        logging.getLogger("cherrypy.error").setLevel(logging.WARNING)
        cherrypy.engine.start()
        self.info("Server started")
        self.running = True

    def stop(self):
        cherrypy.engine.stop()
        if self.host_server is not None:
            self.host_server.unsubscribe()
        cherrypy.process.bus.exit()

    def handleError(self, call):
        try:
            return call()
        except Exception as e:
            data = self.processError(e)
            cherrypy.response.headers['Content-Type'] = 'application/json'
            cherrypy.response.status = data['http_status']
            return data

    def processError(self, e):
        if isinstance(e, KnownError):
            known: KnownError = e
            return {
                'http_status': known.httpStatus(),
                'error_type': known.code(),
                'message': known.message(),
                'details': formatException(e),
                'data': known.data()
            }
        else:
            return {
                'http_status': 500,
                'error_type': "generic_error",
                'message': "An unexpected error occurred: " + str(e),
                'details': formatException(e)
            }

    def filePath(self, name):
        return abspath(join(__file__, "..", "..", "www", name))

    def cssElement(self, selector, keys):
        ret = selector
        ret += " {\n"
        for key in keys:
            ret += "\t" + key + ": " + keys[key] + ";\n"
        ret += "}\n\n"
        return ret

    @cherrypy.expose
    def theme(self, version=""):
        cherrypy.response.headers['Content-Type'] = 'text/css'
        cherrypy.response.headers['Cache-Control'] = 'no-cache'
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
        bgshadow = "0 2px 2px 0 " + shadow1.toCss() + ", 0 3px 1px -2px " + shadow2.toCss() + ", 0 1px 5px 0 " + shadow3.toCss()

        bg_modal = background.tint(text, 0.02)
        shadow_modal = "box-shadow: 0 24px 38px 3px " + shadow1.toCss() + ", 0 9px 46px 8px " + shadow2.toCss() + ", 0 11px 15px -7px " + shadow3.toCss()

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
            'padding': '3px 5px 3px 5px',
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

        return ret
