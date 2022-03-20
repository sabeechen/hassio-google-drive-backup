# Using Custom/Personal Google Credentials
You've arrived here because you'd like to use your own client ID and client secret to authenticate the add-on with Google Drive.  I'll caution that this is a very detailed and complicated process geared more toward developers than end users, so if you'd like to do it the easy way, go back to your add-on (typically http://homeassistant.local:8123/hassio/ingress/hassio_google_drive_backup) and click the "Authenticate with Google Drive" button.  These instructions will have you create a project on Google's Developer Cloud console, generate your own credentials, and use them to authenticate with Google Drive.  You can expect this to take about 15 minutes.  Typically this is what would be done by a developer when releasing a project that serveral users would use, but in this case you will be the only user.  This workflow is for you if:
* You'd like to avoid having your account's credentials go through a server maintained by the developer of this addon.  The typical authentication workflow never sees your Google account password, but it does recieve a token from Google that, if I were malicious, I could use to see the backups you've uploaded to Google Drive.  I don't store this token anywhere and instead just pass it back to you, but becase of how Google oauth tokens are generated there is no way you could verify that.  I tip my tinfoil hat to yours and respect your desire to protect your personal information :)
* The typical authentication flow didn't work.  This may be because of a bug, or because the server I set up to handle it is down or broken.  Its just me back here providing this as a free service to the community, so applogogies if things fall into disrepair.

These instructions are current as of March 2022.  If you do this and notice they're out of date, Please file an issue on this project's issue page so I can be made aware of it.  Thanks!
## Step 0 - Check addon version
You must be runnign version 0.106.1 or greater of the add-on for this to work.  In Feb 2022 Google changed how some of their authentication APIs work which broke the way the addon did it before that version
## Step 1 - Create a Google Cloud Project
* Go to http://console.developers.google.com and log in with your Google account.
* Click "Select Project" on the top left.
* Click "New Project" to create a project.
* Give the project any name you like, and click "Create Project".  Don't worry about billing or location information, you won't be charged for anything we're doing here.
![](images/step1.png)

## Step 2 - Enable the Drive API
With your project now created:
* Go to https://console.developers.google.com/apis/library
* Search for "Google Drive API", and click "Enable".  This is necessary because the "Project" you're creating will use the [Google Drive API](https://developers.google.com/drive/api/v3/reference). 

## Step 3 - Create a Consent Screen
Before creating credentials, you'll need to create a consent screen.  Normally this is what people would see when they request to allow your new application to access their Google Drive, but because you're creating it just for yourself this is basically just a necessary formality.
* Go back to http://console.developers.google.com and ensure the project name you created earlier is displayed in the upper left.
* In the menu on the upper left, click **APIs & Services** then *OAuth Consent Screen*.
* Select *External* for the user type and then click "Create".  Even though you're probably making these credentials with the same account you'll be using to authenticate the addon, you'll still be considered an *External* user.  
* On the next screen "App Information", fill in all the required fields, *App Name*, *Support Email*, and *Developer Email*.  Then click Continue.  What you enter here doesn't really matter, but a good App Name is something that will make you laugh if you ever have to see this again, like "Buy the name-brand SD Card this time, maybe?"
* On the next screen, click **Add OR Remove Scopes**.  In the dialog that pops up check the box for "../auth/drive.file" and then click "Add".  You might have to search for "drive.file" to make it show up.  This part is very important since it gives the credentials we're about to create permission to see files in Google Drive.  If you don't see this in the dialog that comes up, make sure you did step 2.
* You can leave the rest of this form blank, just click **Save**  or **Continue** for any other screens.
* Once its created, either click **Go Back to Dashboard** or click **OAuth Consent Screen** on the left.  Under **Publishing status** click **Publish App** and then **Confirm**.  This dialog will warn that the app will be available to all users, but in our case it will still only be you if you keep the credentials you create later just to yourself.  This step is necessary because "Testing" credentials would require you to manually re-authorize the addon ever 7 days, which is a pain.

## Step 4 - Create Credentials
Now you've set up everything necessary to actually create credentials.
* From http://console.developers.google.com, click **APIs & Services** then **Credentials** on the left.
* Click **+ Create Credentials** at the top of the page.
* Select "OAuth client ID" form the drop down.
This should have opened a dialog titled "Create OAuth client ID".
* Select **TVs and Limited Input Devices** for **Application Type**.  Home Assistant might not seem like a "Limited Input Device" but is is necessary because its the only OAuth authentication method Google provides that doesn't require you to maintain a public SSL encrpted web service. 
* Give the credentials a **Name**, anything will do and it doesn't matter.
![](images/step4.png)
* Click "Create"


## Step 5 - Copy your credentials
This should have opened a new dialog with your generated client ID and client secret.  Take these back to the Add-on, and paste them into the appropriate fields of the add-on web-UI, and follow the instructions from there.
![](images/step5.png)
