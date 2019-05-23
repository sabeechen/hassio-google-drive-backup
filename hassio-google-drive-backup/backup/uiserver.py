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
from os.path import join, abspath

# Used to Google's oauth verification
SCOPE: str = 'https://www.googleapis.com/auth/drive.file'
MANUAL_CODE_REDIRECT_URI: str = "urn:ietf:wg:oauth:2.0:oob"


class UIServer(Trigger, LogBase):
    def __init__(self, coord: Coordinator, ha_source: HaSource, harequests: HaRequests, time: Time, config: Config, global_info: GlobalInfo):
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
        status['restore_link'] = self.getRestoreLink()
        status['drive_enabled'] = self._coord.enabled()
        # TODO: This doesn't check for key existence, won't work
        status['ask_error_reports'] = not self.config.isExplicit(Setting.SEND_ERROR_REPORTS)
        status['warn_ingress_upgrade'] = self.config.warnExposeIngressUpgrade()
        status['cred_version'] = self._global_info.credVersion
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
        if self._global_info._last_error is not None:
            status['last_error'] = self.processError(self._global_info._last_error)
        status["firstSync"] = self._global_info._first_sync
        status["maxSnapshotsInHasssio"] = self.config.get(Setting.MAX_SNAPSHOTS_IN_HASSIO)
        status["maxSnapshotsInDrive"] = self.config.get(Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE)
        status["snapshot_name_template"] = self.config.get(Setting.SNAPSHOT_NAME)
        status['sources'] = self._coord.buildSnapshotMetrics()
        status['authenticate_url'] = self.config.get(Setting.AUTHENTICATE_URL)
        status['dns_info'] = self._global_info.getDnsInfo()
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

    def getRestoreLink(self):
        if self._global_info.ha_ssl:
            protocol = "https://"
        else:
            protocol = "http://"
        return "".join([protocol, "{host}:", str(self._global_info.ha_port), "/hassio/snapshots"])

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
                if self.config.useIngress() and 'ingress_url' in self.engine.hassio.self_info:
                    return {
                        'auth_url': self.engine.hassio.self_info['ingress_url']
                    }
                else:
                    return {
                        'auth_url': "/"
                    }
            except Exception as e:
                return {
                    'error': "Couldn't create authorization URL, Google said:" + str(e)
                }
            raise cherrypy.HTTPError()

    def auth(self, realm: str, username: str, password: str) -> bool:
        if username in self.auth_cache and self.auth_cache[username]['password'] == password and self.auth_cache[username]['timeout'] > self._time.now():
            return True
        try:
            self._harequests.auth(username, password)
            self.auth_cache[username] = {'password': password, 'timeout': (self._time.now() + timedelta(minutes=10))}
            return True
        except Exception as e:
            self.error(formatException(e))
            return False

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
            for line in self.getHistory(self.last_log_index, html):
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
        if self.config.useIngress():
            return self.redirect("/hassio/ingress/" + self.engine.hassio.self_info['slug'])
        else:
            return self.redirect("/")

    @cherrypy.expose
    def error(self, error: str = "") -> None:
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
        self._ha_source.init()
        name_keys = {}
        for key in SNAPSHOT_NAME_KEYS:
            name_keys[key] = SNAPSHOT_NAME_KEYS[key]("Full", self._time.now(), self._ha_source.host_info)
        current_config = {}
        for setting in Setting:
            current_config[setting.key()] = self.config.get(setting)
        return {
            'config': current_config,
            'addons': self._global_info.addons,
            'support_ingress': self.config.useIngress(),
            'name_keys': name_keys
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
    def exposeserver(self, expose: str) -> None:
        return self.handleError(lambda: self._exposeserver(expose))

    def _exposeserver(self, expose: str) -> None:
        if expose == "true":
            self.config.setExposeAdditionalServer(self.engine.hassio.updateConfig, True)
        else:
            self.config.setExposeAdditionalServer(self.engine.hassio.updateConfig, False)
            # INGRESS: this needs to do something else for ingress
            raise Exception("Ingress isn't implemented yet")
        self.run()

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
        self._updateConfiguration(validated)
        return {'message': 'Settings saved'}

    def _updateConfiguration(self, new_config):
        server_config_before = self._getServerOptions()

        update = {}
        for key in new_config:
            update[key.key()] = new_config[key]
        self._harequests.updateConfig(update)
        self.config.update(new_config)
        server_config_after = self._getServerOptions()
        if server_config_before != server_config_after:
            self.run()
        self.trigger()
        return {'message': 'Settings saved'}

    def _getServerOptions(self):
        return {
            "ssl": self.config.get(Setting.USE_SSL),
            "login": self.config.get(Setting.REQUIRE_LOGIN),
            "certfile": self.config.get(Setting.CERTFILE),
            "keyfile": self.config.get(Setting.KEYFILE),
            "extra_server": self.config.get(Setting.EXPOSE_EXTRA_SERVER),
            "ingress": self.config.useIngress()
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

        if self.config.get(Setting.EXPOSE_EXTRA_SERVER):
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
