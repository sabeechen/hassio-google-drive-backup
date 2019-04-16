import os.path
import os
import cherrypy
from datetime import timedelta
from datetime import datetime
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.client import HttpAccessTokenRefreshError
from oauth2client.client import OAuth2Credentials
from .helpers import nowutc
from .helpers import formatTimeSince
from .helpers import formatException
from .engine import Engine
from .config import Config
from .knownerror import KnownError
from .logbase import LogBase
from typing import Dict, Any, Optional
from .snapshots import Snapshot
from cherrypy.lib.static import serve_file

# Used to Google's oauth verification
SCOPE: str = 'https://www.googleapis.com/auth/drive.file'
MANUAL_CODE_REDIRECT_URI: str = "urn:ietf:wg:oauth:2.0:oob"
DRIVE_FULL_MESSAGE = "The user's Drive storage quota has been exceeded"
CANT_REACH_GOOGLE_MESSAGE = "Unable to find the server at www.googleapis.com"


class Server(LogBase):
    """
    Add delete capabilities

    Make the website less sassy

    make cherrpy optionally use SSL

    Change the app credentials to use somethig more specific than philopen
    ADD Comments
    """
    def __init__(self, root: str, engine: Engine, config: Config):
        self.oauth_flow_manual: OAuth2WebServerFlow = None
        self.root: str = root
        self.engine: Engine = engine
        self.config: Config = config
        self.auth_cache: Dict[str, Any] = {}
        self.last_log_index = 0

    @cherrypy.expose  # type: ignore
    @cherrypy.tools.json_out()  # type: ignore
    def getstatus(self) -> Dict[Any, Any]:
        status: Dict[Any, Any] = {}
        status['folder_id'] = self.engine.folder_id
        status['snapshots'] = []
        last_backup: Optional[datetime] = None
        for snapshot in self.engine.snapshots:
            if (last_backup is None or snapshot.date() > last_backup):
                last_backup = snapshot.date()
            details = None
            if snapshot.ha:
                details = snapshot.ha.source
            status['snapshots'].append({
                'name': snapshot.name(),
                'slug': snapshot.slug(),
                'size': snapshot.sizeString(),
                'status': snapshot.status(),
                'date': str(snapshot.date()),
                'inDrive': snapshot.isInDrive(),
                'inHA': snapshot.isInHA(),
                'isPending': snapshot.isPending(),
                'protected': snapshot.protected(),
                'type': snapshot.version(),
                'details': details
            })
        status['ask_error_reports'] = (self.config.sendErrorReports() is None)
        status['drive_snapshots'] = self.engine.driveSnapshotCount()
        status['ha_snapshots'] = self.engine.haSnapshotCount()
        status['restore_link'] = self.getRestoreLink()
        next: Optional[datetime] = self.engine.getNextSnapshotTime()
        if not next:
            status['next_snapshot'] = "Disabled"
        elif (next < nowutc()):
            status['next_snapshot'] = formatTimeSince(nowutc())
        else:
            status['next_snapshot'] = formatTimeSince(next)

        if last_backup:
            status['last_snapshot'] = formatTimeSince(last_backup)
        else:
            status['last_snapshot'] = "Never"

        status['last_error'] = self.getError()
        status["firstSync"] = self.engine.firstSync
        return status

    def getRestoreLink(self):
        if not self.engine.homeassistant_info:
            return ""
        if self.engine.homeassistant_info['ssl']:
            url = "https://"
        else:
            url = "http://"
        url = url + "{host}:" + str(self.engine.homeassistant_info['port']) + "/hassio/snapshots"
        return url

    def getError(self) -> str:
        if self.engine.last_error is not None:
            if isinstance(self.engine.last_error, HttpAccessTokenRefreshError):
                return "creds_bad"
            if isinstance(self.engine.last_error, KnownError):
                return self.engine.last_error.message
            elif isinstance(self.engine.last_error, Exception):
                formatted = formatException(self.engine.last_error)
                if DRIVE_FULL_MESSAGE in formatted:
                    return "drive_full"
                elif CANT_REACH_GOOGLE_MESSAGE in formatted:
                    return "cant_reach_google"
                return formatted
            else:
                return str(self.engine.last_error)
        else:
            return ""

    @cherrypy.expose  # type: ignore
    @cherrypy.tools.json_out()
    def manualauth(self, code: str = "", client_id="", client_secret="") -> None:
        if client_id != "" and client_secret != "":
            try:
                # Redirect to the webpage that takes you to the google auth page.
                self.oauth_flow_manual = OAuth2WebServerFlow(
                    client_id=client_id,
                    client_secret=client_secret,
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
                    'error': "Couldn't create authorizatin URL, Google said:" + str(e)
                }
            raise cherrypy.HTTPRedirect(self.oauth_flow_manual.step1_get_authorize_url())
        elif code != "":
            try:
                self.engine.saveCreds(self.oauth_flow_manual.step2_exchange(code))
                return {
                    'auth_url': "/"
                }
            except Exception as e:
                return {
                    'error': "Couldn't create authorizatin URL, Google said:" + str(e)
                }
            raise cherrypy.HTTPRedirect("/")

    def auth(self, realm: str, username: str, password: str) -> bool:
        if username in self.auth_cache and self.auth_cache[username]['password'] == password and self.auth_cache[username]['timeout'] > nowutc():
            return True
        try:
            self.engine.hassio.auth(username, password)
            self.auth_cache[username] = {'password': password, 'timeout': (nowutc() + timedelta(minutes=10))}
            return True
        except Exception as e:
            self.error(formatException(e))
            return False

    @cherrypy.expose  # type: ignore
    @cherrypy.tools.json_out()  # type: ignore
    def triggerbackup(self) -> Dict[Any, Any]:
        try:
            for snapshot in self.engine.snapshots:
                if snapshot.isPending():
                    return {"error": "A snapshot is already in progress"}

            snapshot = self.engine.startSnapshot()
            return {"name": snapshot.name()}
        except KnownError as e:
            return {"error": e.message, "detail": e.detail}
        except Exception as e:
            return {"error": formatException(e)}

    @cherrypy.expose  # type: ignore
    @cherrypy.tools.json_out()  # type: ignore
    def deleteSnapshot(self, slug: str, drive: str, ha: str) -> Dict[Any, Any]:
        delete_drive: bool = (drive == "true")
        delete_ha: bool = (ha == "true")
        try:
            if not delete_drive and not delete_ha:
                return {"message": "Bad request, gave nothing to delete"}
            self.engine.deleteSnapshot(slug, delete_drive, delete_ha)
            return {"message": "Its gone!"}
        except Exception as e:
            self.error(formatException(e))
            return {"message": "{}".format(e), "error_details": formatException(e)}

    @cherrypy.expose  # type: ignore
    def log(self, format="download", catchup=False) -> Any:
        if not catchup:
            self.last_log_index = 0
        if format == "view":
            return open("www/logs.html")
        if format == "html":
            cherrypy.response.headers['Content-Type'] = 'text/html'
        else:
            cherrypy.response.headers['Content-Type'] = 'text/plain'
            cherrypy.response.headers['Content-Disposition'] = 'attachment; filename="hassio-google-drive-backup.log"'

        def content():
            if format == "html":
                yield "<html><head><title>Hass.io Google Drive Backup Log</title></head><body><pre>\n"
            for line in self.getHistory(self.last_log_index):
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
            self.engine.saveCreds(creds)
        raise cherrypy.HTTPRedirect("/")

    @cherrypy.expose
    def simerror(self, error: str = "") -> None:
        if len(error) == 0:
            self.engine.simulateError(None)
        else:
            self.engine.simulateError(error)

    @cherrypy.expose
    def index(self) -> Any:
        if not self.engine.driveEnabled():
            return open("www/index.html")
        else:
            return open("www/working.html")

    @cherrypy.expose  # type: ignore
    def reauthenticate(self) -> Any:
        return open("www/index.html")

    def run(self) -> None:
        self.info("Starting server...")
        conf: Dict[Any, Any] = {
            'global': {
                'server.socket_port': self.config.port(),
                'server.socket_host': '0.0.0.0',
                'engine.autoreload.on': False,
                'log.access_file': '',
                'log.error_file': '',
                'log.screen': False,
                'response.stream': True

            },
            self.config.pathSeparator(): {
                'tools.staticdir.on': True,
                'tools.staticdir.dir': os.getcwd() + self.config.pathSeparator() + self.root
            }
        }

        if self.config.requireLogin():
            conf[self.config.pathSeparator()].update({
                'tools.auth_basic.on': True,
                'tools.auth_basic.realm': 'localhost',
                'tools.auth_basic.checkpassword': self.auth,
                'tools.auth_basic.accept_charset': 'UTF-8'})

        if self.config.useSsl():
            cherrypy.server.ssl_certificate = self.config.certFile()
            cherrypy.server.ssl_private_key = self.config.keyFile()

        cherrypy.engine.stop()
        cherrypy.config.update(conf)
        cherrypy.tree.mount(self, self.config.pathSeparator(), conf)
        cherrypy.engine.start()

        self.info("Server started")

    @cherrypy.expose  # type: ignore
    @cherrypy.tools.json_out()  # type: ignore
    def backupnow(self) -> Any:
        self.engine.doBackupWorkflow()
        return self.getstatus()

    @cherrypy.expose  # type: ignore
    @cherrypy.tools.json_out()  # type: ignore
    def getconfig(self) -> Any:
        data = self.config.config.copy()
        data['addons'] = self.engine.hassio.readSupervisorInfo()['addons']
        # get the latest list of add-ons
        return data

    @cherrypy.expose
    def errorreports(self, send: str) -> None:
        if send == "true":
            self.config.setSendErrorReports(self.engine.hassio.updateConfig, True)
        else:
            self.config.setSendErrorReports(self.engine.hassio.updateConfig, False)

    @cherrypy.expose  # type: ignore
    @cherrypy.tools.json_out()  # type: ignore
    @cherrypy.tools.json_in()  # type: ignore
    def saveconfig(self, **kwargs) -> Any:
        try:
            self.config.update(self.engine.hassio.updateConfig, **kwargs)
            self.run()
            return {'message': 'Settings saved'}
        except Exception as e:
            return {
                'message': 'Failed to save settings',
                'error_details': formatException(e)
            }

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def upload(self, slug):
        try:
            found: Optional[Snapshot] = None
            for snapshot in self.engine.snapshots:
                if snapshot.slug() == slug:
                    found = snapshot
                    break

            if not found or not found.driveitem:
                raise cherrypy.HTTPError(404)

            if found.isDownloading():
                return {'message': "Snapshot is already being uploaded."}

            path = os.path.join(self.config.backupDirectory(), found.slug() + ".tar")
            self.engine.drive.downloadToFile(found.driveitem.id(), path, found)
            self.engine.hassio.refreshSnapshots()
            self.engine.doBackupWorkflow()

            if not found.isInHA():
                {'message': "Soemthing wen't wrong, Hass.io didn't recognize the snapshot."}
            return {'message': "Snapshot uploaded"}
        except Exception as e:
            return {
                'message': 'Failed to Upload snapshot',
                'error_details': formatException(e)
            }

    @cherrypy.expose
    def download(self, slug):
        found: Optional[Snapshot] = None
        for snapshot in self.engine.snapshots:
            if snapshot.slug() == slug:
                found = snapshot
                break

        if not found or (not found.ha and not found.driveitem):
            raise cherrypy.HTTPError(404)

        if found.ha:
            return serve_file(
                os.path.abspath(os.path.join(self.config.backupDirectory(), found.slug() + ".tar")),
                "application/tar",
                "attachment",
                "{}.tar".format(found.name()))
        elif found.driveitem:
            cherrypy.response.headers['Content-Type'] = 'application/tar'
            cherrypy.response.headers['Content-Disposition'] = 'attachment; filename="{}.tar"'.format(found.name())
            cherrypy.response.headers['Content-Length'] = str(found.size())

            return self.engine.drive.download(found.driveitem.id())
        else:
            raise cherrypy.HTTPError(404)
