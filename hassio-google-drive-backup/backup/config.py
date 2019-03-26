import os.path
import pprint
import json

HASSIO_OPTIONS_FILE = '/data/options.json'

DEFAULTS = {
    "max_snapshots_in_hassio": 4,
    "max_snapshots_in_google_drive": 4,
    "hassio_base_url": "http://hassio/",
    "ha_base_url": "http://hassio/homeassistant/api/",
    "path_separator": "/",
    "port": 1627,
    "days_between_snapshots": 3,

    # how many hours after startup the server will wait before starting a new snapshot automatically
    "hours_before_snapshot": 1,
    "folder_file_path": "/data/folder.dat",
    "credentials_file_path": "/data/credentials.dat",
    "seconds_between_refreshes": 60 * 60, # once per hour, refresh everythin regardless
    "seconds_between_directory_checks": 10,
    "verbose": False,
    "use_ssl": False,
    "certfile": "/ssl/fullchain.pem",
    "keyfile": "/ssl/privkey.pem",
    "require_login": False,
    "backup_directory": "/backup",
    "snapshot_stale_minutes" : 60 * 2,
    "ha_bearer" : ""
}

class Config(object):

    def __init__(self, file_paths):
        self.config = DEFAULTS
        for config_file in [HASSIO_OPTIONS_FILE, ""]:
            if os.path.isfile(config_file):
                with open(config_file) as file_handle:
                    self.config.update(json.load(file_handle))
        for config_file in file_paths:
            if os.path.isfile(config_file):
                with open(config_file) as file_handle:
                    print("Loading config from " + config_file)
                    self.config.update(json.load(file_handle))
        print("Loaded config:")
        pprint.pprint(self.config)


    def maxSnapshotsInHassio(self):
        return self.config['max_snapshots_in_hassio']


    def maxSnapshotsInGoogleDrive(self):
        return self.config['max_snapshots_in_google_drive']

        
    def hassioBaseUrl(self):
        return self.config['hassio_base_url']

    def haBaseUrl(self):
        return self.config['ha_base_url']

        
    def pathSeparator(self):
        return self.config['path_separator']

        
    def port(self):
        return self.config['port']

        
    def daysBetweenSnapshots(self):
        return self.config['days_between_snapshots']

        
    def hoursBeforeSnapshot(self):
        return self.config['hours_before_snapshot']

        
    def folderFilePath(self):
        return self.config['folder_file_path']

        
    def credentialsFilePath(self):
        return self.config['credentials_file_path']

    def secondsBetweenRefreshes(self):
        return self.config['seconds_between_refreshes']

    def secondsBetweenDirectoryChecks(self):
        return self.config['seconds_between_directory_checks']

    def verbose(self):
        return self.config['verbose']

    def useSsl(self):
        return self.config['use_ssl']

    def certFile(self):
        return self.config['certfile']

    def keyFile(self):
        return self.config['keyfile']

    def requireLogin(self):
        return self.config['require_login']

    def backupDirectory(self):
        return self.config['backup_directory']

    def snapshotStaleMinutes(self):
        return self.config['snapshot_stale_minutes']

    def haBearer(self):
        return self.config['ha_bearer']





             
