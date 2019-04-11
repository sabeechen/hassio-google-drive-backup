#!/usr/bin/python3.7
import shutil
import errno
import sys
import json
from os.path import join

from typing import Dict, Any


def copy(src: str, dst: str) -> None:
    try:
        shutil.copytree(src, dst)
    except OSError as exc:
        if exc.errno == errno.ENOTDIR:
            shutil.copy(src, dst)
        else:
            raise


if __name__ == '__main__':
    docker = '--docker' in sys.argv
    remote_folder = join(sys.argv[1], "hassio-google-drive-backup")
    local_folder = "hassio-google-drive-backup"
    config_path = join(sys.argv[1], "hassio-google-drive-backup", "config.json")

    print("Deleting current addon")
    shutil.rmtree(remote_folder, ignore_errors=True)

    print("Copying new addon")
    copy(local_folder, remote_folder)
    config: Dict[str, Any] = {}

    print("updating config")
    with open(config_path) as f:
        config = json.load(f)

    # update config
    if not docker:
        print("(using docker image)")
        config.pop('image', None)
        config['version'] = "dev-local"
    config['slug'] = "hassio-google-drive-backup-local"
    config['name'] = "Hass.io Google Drive Backup (local)"

    with open(config_path, "w") as f2:
        json.dump(config, f2, indent=4)
    print("Done!")
