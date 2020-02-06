#!/usr/bin/env python3
import cgi
import cgitb
import urllib
from oauth2client.client import OAuth2WebServerFlow

cgitb.enable()

SCOPE = 'https://www.googleapis.com/auth/drive.file'
AUTHORIZED_REDIRECT = "https://philosophyofpen.com/login/backup.py"
CLIENT_ID = 'FILLLATER'
CLIENT_SECRET = 'FILLLATER'

args = cgi.FieldStorage()
if 'redirectbacktoken' in args:
    # Someone is trying to authenticate with the add-on, direct them to the google auth url
    flow = OAuth2WebServerFlow(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scope=SCOPE,
        redirect_uri=AUTHORIZED_REDIRECT,
        include_granted_scopes='true',
        prompt='consent',
        access_type='offline',
        state=args.getvalue('redirectbacktoken'))
    print("Status: 303 See other")
    print("Location: " + flow.step1_get_authorize_url())
    print("")
elif 'state' in args and 'code' in args:
    # This is a reply FROM google's authentication server
    try:
        flow = OAuth2WebServerFlow(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            scope=SCOPE,
            redirect_uri=AUTHORIZED_REDIRECT,
            include_granted_scopes='true',
            prompt='consent',
            access_type='offline',
            state=args.getvalue('state'))

        creds = flow.step2_exchange(args.getvalue('code'))

        # Redirect to "state" address with serialized creentials"
        print("Status: 303 See other")
        print("Location: " + urllib.parse.unquote(args.getvalue('state')) + "?creds=" + urllib.parse.quote(creds.to_json()))
        print("")
    except Exception as e:
        print("Content-Type: text/html")
        print("")
        print("The server encountered an error while processing this request: " + str(e) + "<br/>")
        print("Please <a href='https://github.com/sabeechen/hassio-google-drive-backup/issues'>file an issue</a> on Hass.io Google Backup's GitHub page so I'm aware of this problem or attempt authorizing with Google Drive again.")
else:
    print("Status: 400 Bad Request")
    print("")
