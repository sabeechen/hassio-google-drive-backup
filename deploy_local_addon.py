#!/usr/bin/env python3
import shutil
import errno
import sys
import json

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
    shutil.rmtree(sys.argv[1] + "\\addons\\hassio-google-drive-backup", ignore_errors=True)
    copy("hassio-google-drive-backup", sys.argv[1] + "\\addons\\hassio-google-drive-backup")
    config_path: str = sys.argv[1] + "\\addons\\hassio-google-drive-backup\\config.json"
    config: Dict[str, Any] = {}
    with open(config_path) as f:
        config = json.load(f)

    # update config
    config.pop('image', None)
    config['version'] = "dev-local"
    config['slug'] = "hassio-google-drive-backup-local"
    config['name'] = "Hass.io Google Drive Backup (local)"

    with open(config_path, "w") as f2:
        json.dump(config, f2)
    print("Done!")
