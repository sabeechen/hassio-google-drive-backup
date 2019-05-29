#!/usr/bin/env python3
import cgi
import cgitb
import datetime
from urllib.parse import unquote

cgitb.enable()


args = cgi.FieldStorage()
if 'error' in args and 'version' in args:
    with open('/etc/user_error_log/log', "a") as log:
        log.write("\n\nWhen: {2}\nVersion: {0}\nError:{1}\n".format(
            unquote(args.getvalue('version')),
            unquote(args.getvalue('error')),
            datetime.datetime.now()))
    print("Status: 200 OK")
    print("")
    print("OK")
