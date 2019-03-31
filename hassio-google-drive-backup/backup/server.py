import os.path
import os
import cherrypy # type: ignore


from urllib.parse import quote
from datetime import timedelta
from datetime import datetime
from oauth2client.client import OAuth2WebServerFlow # type: ignore
from oauth2client.client import HttpAccessTokenRefreshError
from .helpers import nowutc
from .helpers import formatTimeSince
from .helpers import formatException
from .engine import Engine
from .config import Config
from .snapshots import Snapshot, HASnapshot, DriveSnapshot 
from typing import Dict, List, Any, Optional

# Used to Google's oauth verification
SCOPE: str = 'https://www.googleapis.com/auth/drive.file'
AUTHORIZED_REDIRECT: str = "https://philosophyofpen.com/hassiodrivebackup/authorize.html"
CLIENT_ID: str = '933944288016-01vb6f2do5l0992m08imi0e3fekg54as.apps.googleusercontent.com'
CLIENT_SECRET: str = '7Kdx-RdsCuJ2IreKq47UbU6g'
BAD_TOKEN_ERROR_MESSAGE: str = "Google rejected the credentials we gave it.  Please use the \"Reauthorize\" button on the right to give the Add-on permission to use Google Drive again.  This can happen if you change your account password, you revoke the add-on's access, your Google Account has been inactive for 6 months, or your system's clock is off."

CLIENT_ID_MANUAL: str = "933944288016-ut29pjreodea7ni675jp1sqr2bc630sh.apps.googleusercontent.com"
CLIENT_SECRET_MANUAL: str = "-AsQoNZbUV93JpIdKMcGHU63"
MANUAL_CODE_REDIRECT_URI: str = "urn:ietf:wg:oauth:2.0:oob"


class Server(object):
    """
    Add delete capabilities

    Make the website less sassy

    make cherrpy optionally use SSL

    Change the app credentials to use somethig more specific than philopen
    ADD Comments
    """
    def __init__(self, root: str, engine: Engine, config : Config):
        self.oauth_flow: OAuth2WebServerFlow = OAuth2WebServerFlow(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            scope=SCOPE,
            redirect_uri=AUTHORIZED_REDIRECT,
            include_granted_scopes='true',
            prompt='consent',
            access_type='offline')

        self.oauth_flow_manual: OAuth2WebServerFlow = OAuth2WebServerFlow(
            client_id=CLIENT_ID_MANUAL,
            client_secret=CLIENT_SECRET_MANUAL,
            scope=SCOPE,
            redirect_uri=MANUAL_CODE_REDIRECT_URI,
            include_granted_scopes='true',
            prompt='consent',
            access_type='offline')
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
        if last_backup:
            status['last_snapshot'] = formatTimeSince(last_backup)
        else:
            status['last_snapshot'] = "Never"

        if self.engine.last_error is not None:
            if isinstance(self.engine.last_error, HttpAccessTokenRefreshError):
                status['last_error'] = BAD_TOKEN_ERROR_MESSAGE
            elif isinstance(self.engine.last_error, Exception):
                status['last_error'] = formatException(self.engine.last_error)
            else:
                status['last_error'] = str(self.engine.last_error)
        else:
            status['last_error'] = ""
        return status

    @cherrypy.expose #type: ignore
    def authenticatewithdrive(self, redirecthost: str) -> None:
        # Redirect to the webpage that takes you to the google auth page.
        raise cherrypy.HTTPRedirect('{0}?authurl={1}&redirecturl={2}'.format(AUTHORIZED_REDIRECT, quote(self.oauth_flow.step1_get_authorize_url()), redirecthost))

    @cherrypy.expose #type: ignore
    def manualauth(self, code: str="") -> None:
        if code == "":
            # Redirect to the webpage that takes you to the google auth page.
            raise cherrypy.HTTPRedirect(self.oauth_flow_manual.step1_get_authorize_url())
        else:
            self.engine.saveCreds(self.oauth_flow_manual.step2_exchange(code))
            raise cherrypy.HTTPRedirect("/")

    def auth(self, realm: str, username: str, password: str) -> bool:
        if username in self.auth_cache and self.auth_cache[username]['password'] == password and self.auth_cache[username]['timeout'] > nowutc():
            return True
        try:
            self.engine.hassio.auth(username, password)
            self.auth_cache[username] = {'password': password, 'timeout': (nowutc() + timedelta(minutes=10))}
            return True
        except Exception as e:
            print(formatException(e))
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
            print(formatException(e))
            return {"message": "{}".format(e), "error_details": formatException(e)}

    @cherrypy.expose # type: ignore
    def token(self, **kwargs:  Dict[str, Any]) -> None:
        # fetch the token, save the credentials so we can look them up later.
        self.engine.saveCreds(self.oauth_flow.step2_exchange(kwargs['code']))
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
        if not self.config.verbose():
            conf['global']['log.screen'] = False

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
