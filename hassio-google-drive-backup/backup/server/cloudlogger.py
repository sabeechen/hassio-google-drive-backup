import os
import json
from backup.logger import getLogger, StandardLogger
from injector import inject, singleton
from google.cloud import logging
from google.auth.exceptions import DefaultCredentialsError

basic_logger = getLogger(__name__)


@singleton
class CloudLogger(StandardLogger):
    @inject
    def __init__(self):
        super().__init__(__name__)
        self.google_logger = None
        if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS') is not None:
            try:
                google_logger_client = logging.Client()
                self.googler_logger = google_logger_client.logger("refresh_server")
            except DefaultCredentialsError:
                basic_logger.error("Unable to start Google Logger, no default credentials")

    def log_struct(self, data):
        if self.google_logger is not None:
            self.google_logger.log_struct(data)
        else:
            basic_logger.info(json.dumps(data))
