import os.path
import os
import cherrypy # type: ignore


from urllib.parse import quote
from datetime import timedelta
from datetime import datetime
from oauth2client.client import OAuth2WebServerFlow # type: ignore
from oauth2client.client import HttpAccessTokenRefreshError
from oauth2client.client import OAuth2Credentials
from .helpers import nowutc
from .helpers import formatTimeSince
from .helpers import formatException
from .engine import Engine
from .config import Config
from .snapshots import Snapshot, HASnapshot, DriveSnapshot
from .knownerror import KnownError
from .logbase import LogBase
from typing import Dict, List, Any, Optional

# Used to Google's oauth verification
SCOPE: str = 'https://www.googleapis.com/auth/drive.file'
MANUAL_CODE_REDIRECT_URI: str = "urn:ietf:wg:oauth:2.0:oob"
DRIVE_FULL_MESSAGE = "The user's Drive storage quota has been exceeded"


class Server(LogBase):
    """
    Add delete capabilities

    Make the website less sassy

    make cherrpy optionally use SSL

    Change the app credentials to use somethig more specific than philopen
    ADD Comments
    """
    def __init__(self, root: str, engine: Engine, config : Config):
        self.oauth_flow_manual: OAuth2WebServerFlow = None
        self.root: str = root
        self.engine: Engine = engine
        self.config: Config = config
        self.auth_cache: Dict[str, Any] = {}

    @cherrypy.expose #type: ignore
    @cherrypy.tools.json_out() #type: ignore
    def getstatus(self) -> Dict[Any, Any]:
        status:  Dict[Any, Any] = {}
        status['folder_id'] = self.engine.folder_id
        status['snapshots'] = []
        last_backup: Optional[datetime] = None
        for snapshot in self.engine.snapshots:
            if (last_backup is None or snapshot.date() > last_backup):
                last_backup = snapshot.date()
            status['snapshots'].append({
                'name': snapshot.name(),
                'slug': snapshot.slug(),
                'size': snapshot.sizeString(),
                'status': snapshot.status(),
                'date': str(snapshot.date()),
                'inDrive': snapshot.isInDrive(),
                'inHA': snapshot.isInHA(),
                'isPending': snapshot.isPending()
            })
        status['drive_snapshots'] = self.engine.driveSnapshotCount()
        status['ha_snapshots'] = self.engine.haSnapshotCount()
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
        return status

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
                return formatted
            else:
                return str(self.engine.last_error)
        else:
            return ""
        
    @cherrypy.expose #type: ignore
    @cherrypy.tools.json_out()
    def manualauth(self, code: str="", client_id="", client_secret="") -> None:
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

    @cherrypy.expose #type: ignore
    @cherrypy.tools.json_out() #type: ignore
    def triggerbackup(self) ->  Dict[Any, Any]:
        try:
            for snapshot in self.engine.snapshots:
                if snapshot.isPending():
                    return {"error": "A snapshot is already in progress"}

            snapshot = self.engine.startSnapshot()
            return {"name": snapshot.name()}
        except KnownError as e:
            return {"error": e.message, "detail" : e.detail}
        except Exception as e:
            return {"error": formatException(e)}

    @cherrypy.expose # type: ignore
    @cherrypy.tools.json_out() # type: ignore
    def deleteSnapshot(self, slug: str, drive: str, ha: str) ->  Dict[Any, Any]:
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

    
    @cherrypy.expose # type: ignore
    def log(self, format="download") ->  Any:
        if format == "html":
            cherrypy.response.headers['Content-Type'] = 'text/html'
        else:
            cherrypy.response.headers['Content-Type'] = 'text/plain'
            cherrypy.response.headers['Content-Disposition'] = 'attachment; filename="hassio-google-drive-backup.log"'

        def content():
            if format == "html":
                yield "<html><head><title>Hass.io Google Drive Backup Log</title></head><body><pre>\n"
            for line in self.getHistory():
                if line:
                    yield line + "\n"
            if format == "html":
                yield "</pre></body>\n"
        return content()

    @cherrypy.expose # type: ignore
    def token(self, **kwargs:  Dict[str, Any]) -> None:
        # TODO: Need to do some error handling here.  Exceptions will surface using the cherrypy default.
        if 'creds' in kwargs:
            creds = OAuth2Credentials.from_json(kwargs['creds'])
            #creds.from_json(kwargs[creds].strip("'"))
        raise cherrypy.HTTPRedirect("/")

    @cherrypy.expose # type: ignore
    def simerror(self, error: str="") -> None:
        if len(error) == 0:
            self.engine.simulateError(None)
        else:
            self.engine.simulateError(error)

    @cherrypy.expose # type: ignore
    def index(self) -> Any:
        if not self.engine.driveEnabled():
            return open("www/index.html")
        else:
            return open("www/working.html")

    @cherrypy.expose # type: ignore
    def reauthenticate(self) -> Any:
        return open("www/index.html")

    def run(self) -> None:
        self.info("Starting server...")
        conf:  Dict[Any, Any] = {
            'global': {
                'server.socket_port': self.config.port(),
                'server.socket_host': '0.0.0.0',
            },
            self.config.pathSeparator(): {
                'tools.staticdir.on': True,
                'tools.staticdir.dir': os.getcwd() + self.config.pathSeparator() + self.root
            }
        }
        conf['global']['log.access_file'] = ""
        conf['global']['log.error_file'] = ""
        conf['global']['log.screen'] = False
        conf['global']['response.stream'] = True

        if self.config.requireLogin():
            conf[self.config.pathSeparator()].update({
                'tools.auth_basic.on': True,
                'tools.auth_basic.realm': 'localhost',
                'tools.auth_basic.checkpassword': self.auth,
                'tools.auth_basic.accept_charset': 'UTF-8'})

        if self.config.useSsl():
            cherrypy.server.ssl_certificate = self.config.certFile()
            cherrypy.server.ssl_private_key = self.config.keyFile()
        cherrypy.quickstart(self, self.config.pathSeparator(), conf)

    @cherrypy.expose # type: ignore
    @cherrypy.tools.json_out() # type: ignore
    def backupnow(self) ->  Any:
        self.engine.doBackupWorkflow()
        return self.getstatus()
