import json
import os
import shutil
import time
from os.path import abspath, join

import requests


def main():
    installed = get("supervisor/info")["addons"]
    is_installed = False
    for addon in installed:
        if addon['slug'] == "local_hassio_google_drive_backup":
            is_installed = True
            if addon['state'] != 'stopped':
                # Stop the addon
                print("Stopping the old addon")
                post("addons/local_hassio_google_drive_backup/stop")

    # install the addon
    if os.path.exists("/addons/hassio-google-drive-backup"):
        print("Deleting old files")
        shutil.rmtree("/addons/hassio-google-drive-backup")

    # copy in addon files
    src = abspath(join(__file__, "..", ".."))
    print("Copying new files")
    shutil.copytree(src, "/addons/hassio-google-drive-backup")

    # remove the image file
    print("Updating config.json with debug options")
    with open("/addons/hassio-google-drive-backup/config.json") as f:
        config = json.load(f)
    del config['image']
    config['envrionment'] = {'DEBUGGER': "true"}
    config['ports']['3000/tcp'] = 3000
    with open("/addons/hassio-google-drive-backup/config.json", "w+") as f:
        json.dump(config, f)

    post("addons/reload")
    if not is_installed:
        print("Installing docker image (this can take a while)")
        post("addons/local_hassio_google_drive_backup/install")
    else:
        print("Rebuilding docker image (this can take a while)")
        post("addons/local_hassio_google_drive_backup/rebuild")

    time.sleep(5)
    print("Starting addon")
    post("addons/local_hassio_google_drive_backup/start")


def get(endpoint, json=True):
    headers = {
        "X-HASSIO-KEY": os.environ.get('HASSIO_TOKEN')
    }
    resp = requests.get("http://hassio/" + endpoint, headers=headers)
    resp.raise_for_status()
    if json:
        return resp.json()['data']
    else:
        return resp.text


def post(endpoint, json=True):
    headers = {
        "X-HASSIO-KEY": os.environ.get('HASSIO_TOKEN')
    }
    resp = requests.post("http://hassio/" + endpoint, headers=headers)
    resp.raise_for_status()
    if json:
        return resp.json()['data']
    else:
        return resp.text


if __name__ == '__main__':
    main()
