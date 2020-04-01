# Authentication with Google Drive
This document describes how the addon (Home Assistant Google Drive Backup) authenticates with Google Drive and stores you credentials.  It's geared toward those who wish to know more detail and is not necessary to take advantage of the full features of the addon.  The document is provided in the interest of providing full transparency into how the add-on works.  I've tried to describe this as plainly as possible, but it is technical in nature and therefore may not be understandable to everyone.  Feedback on its clarity is appreciated.

## Your Credentials and the Needed Permission 
In order to have access to any information in Google Drive, Google's authentication servers must be told that the add-on has some permissions.  The addon uses [Google Drive's Rest API (v3)](https://developers.google.com/drive/api/v3/about-sdk) for communication and requests the [drive.file](https://developers.google.com/drive/api/v3/about-auth) permission *scope*.  This *scope* means the add-on has access to files and folders that the add-on creates, but nothing else.  It can't see files you've added to Google Drive through their web interface or anywhere else.  Google Drive's Rest API allows the addon to periodically check what snapshots are backed up and upload new ones if necessary by making requests over the internet.  

## Authentication with Google Services
For reference, Google's documentation for how to authenticate users with the Google drive REST API is [here](https://developers.google.com/drive/api/v3/about-auth).  Authentication is handled through [OAuth 2.0](https://developers.google.com/identity/protocols/OAuth2), which means that the add-on never actually sees your Google username and password, only an opaque token used to verify that the addon has been given permission.  More detail is provided about what that token is and where its stored later in this document.

The way a web-based application would normally authenticate with a Google service (eg Google Drive) looks something like this:
1. User navigates to the app's webpage, eg http://examplegoogleapp.com
2. The app generates a url to Google's servers (https://accounts.google.com) used to granted the app permission.
3. User navigates here, enters their Google username and password, and confirms the intention to give the app some permission (eg one or more *scopes*).
4. Google redirects the user back to the app's webpage with an access token appended to the url (eg http://examplegoogleapp.com/authenticate?token=0x12345678)
5. The app stores the access token (0x12345678 in this example), and then passes it back to Google whenever it wishes to make access the API on behalf of the user.

This access token allows to app to act as if it were the user who created it.  In the case of this add-on, the permission granted by the drive.file scope allows it to create folders, upload snapshots, and retrieve the previously created folders.  Because the add-on only ever sees the access token (not the username/password), and the access token only grants limited permissions, the add-on doesn't have a way to elevate its permission futher to access other information in Google Drive or your Google account.

## Authentication for the Add-on

Google puts some limitations on how the access token must be generated that will be important for understanding how the add-on authenticates in reality:
* When the user is redirected to https://accounts.google.com (step 2), the redirect must be from a known public website associated with the app.
* When the user is redirected back to the app after authorization (step 4), the redirect must be a statically addressed and publicly accessible website.

These limitations make a problem because most people's Home Assistant instances aren't publicly accessible and the address is different for each one so performing the authentication workflow described above won't work.  To get around this, I (your friendly developer) have set up a website, philosophyofpen.com, which serves as the known public website that Google redirects from/to.  Some have asked why it has the URL it does, and its honestly just a domain I had lying around.  My wife does [pen turning](https://www.youtube.com/results?search_query=pen+turning) for a hobby, and someday that website will host her work.

So when you authenticate the add-on, the workflow actually looks like this:
1. You start out at the add-on's web interface, something like https://hassio.local:8123/ingress/hassio_google_drive_backup
2.  You click the "Authenticate With Google Drive" button, which takes note of the address of your Home Assistant installation (https://hassio.local:8123 in the case) a sends you to https://philosophyofpen.com/login
3. https://philosophyofpen.com immediately generates the Google login url for you and redirects you to https://accounts.google.com
4.  You login with your Google credentials, and confirm you want to give the add-on permission to see files and folders it creates (the drive.file scope)
5.  Google redirects you back to https://philosophyofpen.com, along with the access token that will be used for future authentication.
6.  https://philosophyofpen.com redirects you back to your add-on web-UI (which it kept track of in step 2) along with the access token.
7.  The addon (on your local Home Assistant installation) persists the access token and uses it in the future any time it needs to talk to Google Drive.

Noteably, your access token isn't persisted at https:/philosophyofpen.com, its only passed through back to you local add-on installation.  Id do this because I don't wan to be in the business of storing any information that could make someone vulnerable if my server were compromised.  After authentication, the add-on onyl communicates directly with Google Drive to sync your snapshots, as https://philosophyofpen.com is onyl necessary to generate the acces token initially.
