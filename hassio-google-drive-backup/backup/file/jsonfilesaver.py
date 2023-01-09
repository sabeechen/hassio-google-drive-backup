import json
import os
from backup.logger import getLogger
from os.path import exists

logger = getLogger(__name__)


class JsonFileSaver:
    """
    The envrionment Home Assistant runs in is notorious for disk-related failures, often from running completely out of space and SD card corruption.
    Both of these can leave the addon in a state where the files it need to run are either corrupted or empty.  This class attempts to mitigate that
    by writing all config files twice, first to a backup file and then to the "real" file path. Then when reading it will check both locations to try
    and find a copy of the file that isn't corrupted or deleted.
    This avoids a number of common failures, namely:
    - A power failure while writing a file can leave it empty or malformed.
    - Overwriting a file while the disk is full can truncateit without writing the new data
    - HD corruption cna make a file malformed, but its less likely to affect both files.
    """
    @classmethod
    def _read(cls, path):
        with open(path, "r") as f:
            return json.load(f)

    @classmethod
    def read(cls, path):
        try:
            return JsonFileSaver._read(path)
        except json.decoder.JSONDecodeError:
            logger.error(f"The configuration file {path} had an invalid format.  This could be caused by hard drive corruption or an unstable power event.  We'll attempt to load from a backup file instead.")
            backup = JsonFileSaver._backup_path(path)
            if not exists(backup):
                logger.error("Unable to locate a backup path")
                raise
            return JsonFileSaver._read(backup)
        except FileNotFoundError:
            logger.error(f"The configuration file {path} was not found.  This could be caused by hard drive corruption or an unstable power event.  We'll attempt to load from a backup file instead.")
            backup = JsonFileSaver._backup_path(path)
            if not exists(backup):
                logger.error("Unable to locate a backup path")
                raise
            return JsonFileSaver._read(backup)

    @classmethod
    def _write(cls, path, data):
        with open(path, "w") as f:
            json.dump(data, f, indent=4)

    @classmethod
    def write(cls, path, data):
        # Crete the backup (rcovery) file first.  This ensures its present if the subsequent write is corrupted. 
        JsonFileSaver._write(JsonFileSaver._backup_path(path), data)
        JsonFileSaver._write(path, data)

    @classmethod
    def exists(cls, path):
        if exists(path):
            return True
        return exists(JsonFileSaver._backup_path(path))

    @classmethod
    def delete(sels, path):
        if exists(JsonFileSaver._backup_path(path)):
            os.remove(JsonFileSaver._backup_path(path))
        if exists(path):
            os.remove(path)

    @classmethod
    def _backup_path(cls, path):
        return path + ".backup"

