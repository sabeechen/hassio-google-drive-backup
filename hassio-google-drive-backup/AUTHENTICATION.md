# Authentication with Google Drive
This document describes how the addon (Home Assistant Google Drive Backup) authenticates with Google Drive and stores your credentials.  It's geared toward those who wish to know more detail and is not necessary to take advantage of the full features of the addon.  The document is provided in the interest of providing full transparency into how the add-on works.  I've tried to describe this as plainly as possible, but it is technical and therefore may not be understandable to everyone.  Feedback on its clarity is appreciated.

 > This document describes how authentication works if you use the big blue "AUTHENTICATE WITH GOOGLE DRIVE" button in the addon.  If you're using [your own Google Drive credentials](https://github.com/sabeechen/hassio-google-drive-backup/blob/master/LOCAL_AUTH.md), then none of this applies.

## Your Credentials and the Needed Permission 
To have access to any information in Google Drive, Google's authentication servers must be told that the add-on has the permission.  The add-on uses [Google Drive's Rest API (v3)](https://developers.google.com/drive/api/v3/about-sdk) for communication and requests the [drive.file](https://developers.google.com/drive/api/v3/about-auth) permission *scope*.  This *scope* means the add-on has access to files and folders that the add-on created, but nothing else.  It can't see files you've added to Google Drive through their web interface or anywhere else.  Google Drive's Rest API allows the addon to periodically check what backups are uploaded and upload new ones if necessary by making requests over the internet.  

## Authentication with Google Services
For reference, Google's documentation for how to authenticate users with the Google Drive REST API is [here](https://developers.google.com/drive/api/v3/about-auth).  Authentication is handled through [OAuth 2.0](https://developers.google.com/identity/protocols/OAuth2), which means that the add-on never actually sees your Google username and password, only an opaque [security token](https://en.wikipedia.org/wiki/Access_token) used to verify that the addon has been given permission.  More detail is provided about what that token is and where it is stored later in this document.

The way a web-based application would normally authenticate with a Google service (eg Google Drive) looks something like this:
1. User navigates to the app's webpage, eg http://examplegoogleapp.com
2. The app generates a URL to Google's servers (https://accounts.google.com) used to grant the app permission.
3. User navigates there, enters their Google username and password, and confirms the intention to give the app some permission (eg one or more *scopes*).
4. Google redirects the user back to the app's webpage with an access token appended to the URL (eg http://examplegoogleapp.com/authenticate?token=0x12345678)
5. The app stores the access token (0x12345678 in this example), and then passes it back to Google whenever it wishes to make access the API on behalf of the user who logged in.

This access token allows the app to act as if it is the user who created it.  In the case of this add-on, the permission granted by the drive.file scope allows it to create folders, upload backups, and retrieve the previously created folders.  Because the add-on only ever sees the access token (not the username/password), and the access token only grants limited permissions, the add-on doesn't have a way to elevate its permission further to access other information in Google Drive or your Google account.

## Authentication for the Add-on

Google puts some limitations on how the access token must be generated that will be important for understanding how the add-on authenticates in reality:
* When the user is redirected to https://accounts.google.com (step 2), the redirect must be from a known public website associated with the app.
* When the user is redirected back to the app after authorization (step 4), the redirect must be a statically addressed and publicly accessible website.

These limitations make a technical problem for the addon because most people's Home Assistant instances aren't publicly accessible and the address is different for each one. Performing the authentication workflow exactly as described above won't work.  To get around this, I (the developer of this addon) set up a website, https://habackup.io, which serves as the known public and statically addressable website that Google redirects from/to.  The source code for this server is available within the add-on's GitHub repository.

So when you authenticate the add-on, the workflow looks like this:
1. You start at the add-on's web interface, something like https://homeassistant.local:8123/ingress/hassio_google_drive_backup
2.  You click the "Authenticate With Google Drive" button, which takes note of the address of your Home Assistant installation (https://homeassistant.local:8123 in this case) and sends you to https://habackup.io/drive/authorize
3. https://habackup.io immediately generates the Google login URL for you and redirects you to https://accounts.google.com
4.  You log in with your Google credentials on Google's domain, and confirm you want to give the add-on permission to see files and folders it creates (the drive.file scope)
5.  Google redirects you back to https://habackup.io, along with the access token that will be used for future authentication.
6.  https://habackup.io redirects you back to your add-on web-UI (which is kept track of in step 2) along with the access token.
7.  The addon (on your local Home Assistant installation) persists the access token and uses it in the future any time it needs to talk to Google Drive.

Notably, your access token isn't persisted at https://habackup.io, it is only passed through back to your local add-on installation.  I do this because:
- It ensures your information is only ever stored on your machine, which is reassuring from the user's perspective (eg you).  
- If my server (https://habackup.io) ever gets compromised, there isn't any valuable information stored there that compromises you as well.
- This is practicing a form of [defense-in-depth](https://en.wikipedia.org/wiki/Defense_in_depth_%28computing%29) security, where-in [personal data](https://en.wikipedia.org/wiki/Personal_data) is only stored in the places where it is strictly critical.
- It makes the server more simple since it is a stateless machine that doesn't require a database (eg to store your token).  

After your token is generated and stored on your machine, it needs to be *refreshed* periodically with Google Drive.  To do this, the addon will again ask https://habackup.io who will relay the request with Google Drive.
