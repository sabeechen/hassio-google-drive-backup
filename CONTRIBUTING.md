# Contributing

## About the project

The project is mostly maintained by Stephen Beechen (stephen@beechens.com) whome you can reach out to for guidance. Before digging in to this, it might be helpful to familiarize yourself with some of the technologies used in the project.

- [Developing Addons for Home Assistant](https://developers.home-assistant.io/docs/add-ons) - Useful to understand how addons work.
- [Python](https://www.python.org/) - The addon is written in python 3.8 and makes heavy use of the asyncio framework.
- [AIOHTTP](https://docs.aiohttp.org/en/stable/) - The addon serves its web interface through an AIOHTTP server, and uses the AIOHTTP client library for all web requests.
- [PyTest](https://docs.pytest.org/en/latest/) - The addon uses pytest for all of its test.
- [Visual Studio Code](https://code.visualstudio.com/) - The addon codebase is designed to work with Visual Studio code, but in practice you could use any editor (it would be harder). These instructions assume you're using VSCode, its a free cross-platform download.
- [Docker](https://www.docker.com/) - All Home Assistant addons run in their own docker cotnainer, and while you could certainly contribute without knowing much about it, knowledge of the basic commands will help.

## Approval Process
 - Please only make PR's against the [dev branch](https://github.com/sabeechen/hassio-google-drive-backup/tree/dev).  Making a PR against master/main will result in an embarrassing song-and-dance where I ignore your PR for a little while, then ask you to remake it against dev, then ignore it again for a little while out of spite.  Neither of us wants this, and you can avoid it by making it against dev in the first place.
 - If you're making a small change that fixes a bug I'm going to approve your PR quickly and heap you with praise.  If you make a huge change without talking to me first I'm going to review your PR slowly and move through it with suspicion.  A spectrum exists between those two extremes.  Please try to understand that I'm the one ultimately on the line for the addon's reputation.
   - Breaking up a large change into smaller manageable pieces make things easier.
   - You can reach out to me in any of these ways to talk about a change you're considering:
     - Preferred: [File an issue on github](https://github.com/sabeechen/hassio-google-drive-backup/issues) proposing your changes.
     - Next best: Email: stephen@beechens.com
     - Acceptable but worst: Home Assistant Forums: [@sabeechen](https://community.home-assistant.io/u/sabeechen/summary)
 - Any submissions to the dev branch get automatically built and pushed to a staging version of the addon that you can install using [this repository](https://github.com/sabeechen/hgdb-dev-staging).  Its identical to the "Production" addon but talks to [https://dev.habackup.io](https://dev.habackup.io) instead of [https://habackup.io](https://habackup.io).
 - Releases of the addon are made as-needed for bug fixes and new features.  If you've made a signifigant change to the addon, you can expect me to communicate to you when you can expect to see it released.  Important fixes will often demand an out-of-schedule rushed release.
## Setting up a Development Environment

1. Install [Visual Studio Code](https://code.visualstudio.com/)
2. Install [Python 3.8](https://www.python.org/downloads/) for your platform.
3. Install a git client. I like [GitHub Desktop](https://desktop.github.com/)
4. Clone the project repository
   ```
   https://github.com/sabeechen/hassio-google-drive-backup.git
   ```
5. Open Visual studio Code, go to the extension menu, and install the the Python extension from Microsoft. It may prompt you to choose a python interpreter (you want python 3.8) and select a test framework (you want PyTest).
6. <kbd>File</kbd> > <kbd>Open Folder</kbd> to open the cloned repository folder.
7. Open the terminal (`Ctrl` + `Shift` + <code>`</code>) and install the python packages required for development:
   ```
   > python3.8 -m pip install -r hassio-google-drive-backup/dev/requirements-dev.txt
   ```
   That should set you up!

## Helpful Pointers

Here are some pointers about how things work that might get you to where you want to get faster:

- Constructor dependencies are handled through dependency injection. You can look at the attributes defined on most any class or constructor to see how they should be defined.
- The project has almost **100% test coverage** and the expectation for all submissions (including my own) is that they will not lower that number. If you change something, your PR **must** include tests that cover it. The only exception is all the javascript, which has no unit tests.
- The web server for the addon is in `uiserver.py`.
- You'll want to make your changes to the `dev` branch, since the `master` branch is where new releases are made.

## Trying Out Changes

To try out changes locally during development, I've written a server that simulates Home Assistant, the Supervisor, habackup.io, and Google Drive HTTP endpoints that the addon expects in [simulationserver.py](https://github.com/sabeechen/hassio-google-drive-backup/blob/master/hassio-google-drive-backup/dev/simulationserver.py). Its a beast of a class and doeas a lot. It simulates the services for development and is also used to make unit tests work.

To give it a shot, open up Visual Studio's "Run" Dialog and start up `Run Mock Backend Server`. Then also run one of these options:

- `Run Addons (Dev Backends)` - This starts up the addon web server and connects it to the simulated Home Assistant, Supervisor, and Google Drive. All of the functionality of the addon is supported (creating/deleting snapshot, authenticating with Google drive, etc).
- `Run Addons (Dev Drive)` - This should be unused by contributors, as its only used for testing prior to a release by @sabeechen.
- `Run Addons (Real Drive)` - This uses a simulated Home Assistant and Supervisor, but connects to the real Google Drive. You'll have to use a real Google account to work with this configuration.

## The Staging Addon
Any submissions made to the dev branch (including PR's) get automatically built and deployed to a staging version of the addon.  You can install this by adding the repository [https://github.com/sabeechen/hgdb-dev-staging](https://github.com/sabeechen/hgdb-dev-staging) to your home assistant machine.  This addon is identical to what will be released with the next version of the addon but:
 - It is a separate "App" in Google's perspective, so it can't see any snapshots created by the "Production" addon.
 - Its not reocmmended to run it along side the "Production" addon on the same machine (it see's the same snapshots).
 - It talks to [https://dev.habackup.io](https://dev.habackup.io) instead of [https://habackup.io](https://habackup.io) to authenticate with Google Drive.
 - If you submit code to the dev branch, you should see an update to the addon show up in Home Assistant ~25 minutes later.
 - It is the "bleeding edge" of changes, so it might have bugs.  Be warned!

## Testing your local changes in Home Assistant

For some chages, just testing locally might not be enough, you may want to run it as a real addon. You can do this roughly following the instuction for [Add-on Testing](https://developers.home-assistant.io/docs/add-ons/testing#local-build). Here are the two methods I've found work best:

- ### Building a Local Addon Container in Home Assistant
  Copy the folder `hassio-google-drive-backup` (the one with `config.json` inside it) into the local addon folder (you'll need the samba addon or something similar to do so). Modify the uploaded `config.json` to remove the `"image"` line near the bottom. Then in Home Assistant Web-UI go to <kbd>Supervisor</kbd> -> <kbd>Addon-Store</kbd>, <kbd>Reload</kbd>, and the addon should show up under "Local Addons". It should includes buttons for building the container, starting/stopping etc.
- ### Building a container
  You could also build the container as a docker container locally, upload it to DockerHub, and then have Home Assistant download the image. First install docker desktop, then:
  ```bash
  > cd hassio-google-drive-backup
  > docker login
  > docker build -f Dockerfile-addon -t YOUR_DOCKER_USERNAME/hassio-google-drive-backup-amd64:dev_testing --build-arg BUILD_FROM=homeassistant/amd64-base .
  > docker push YOUR_DOCKER_USERNAME/hassio-google-drive-backup-amd64:dev-testing
  ```
  Then make a folder in the local addon directory like before, but only copy in config.json. change these two keys in config.json to match what you uploaded:
  ```json
  {
    "image": "YOUR_DOCKER_USERNAME/hassio-google-drive-backup-{arch}",
    "version": "dev-testing"
  }
  ```
  From there you should be able to see the addon in local addons, and installing will download the container from DockerHub. To make it see changes, you'll need to rebuild and reupload the container, then uninstall and reinstall the addon in Home Assistant. I've found this to be faster than rebuilding the image from scratch within Home Assistant.
  > Note: Make sure you stop any other versions of the installed addon in Home Assistant before starting it as a local addon.

I haven't tried using the Supervisor's new devcontainers for development yet (the addon predates this), let me know if you can get that working well.

## Running Tests

You should be abel to run tests from within the Visual Studio tests tab. Make sure all the tests pass before you to make a PR. You can also run them from the command line with:

```bash
> python3.8 -m pytest hassio-google-drive-backup
```

## Writing Tests

Test dependencies get injected by `pytest`, which are defined in the [conftest.py](https://github.com/sabeechen/hassio-google-drive-backup/blob/master/hassio-google-drive-backup/tests/conftest.py) file. This is resonsible for starting the simulation server, mocking necessary classes, etc.
Most classes have their own test file in the [tests](https://github.com/sabeechen/hassio-google-drive-backup/tree/master/hassio-google-drive-backup/tests) directory. If you change anything in the code, you must also submit tests with your PR that verify that change. The only exception is that all the addon's javascript, I've never found a good way to do Javascript tests.
