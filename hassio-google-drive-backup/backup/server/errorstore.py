import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from datetime import datetime
from backup.config import Setting, Config
from .cloudlogger import CloudLogger
from injector import inject, singleton


@singleton
class ErrorStore():
    @inject
    def __init__(self, logger: CloudLogger, config: Config):
        try:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {
                'projectId': config.get(Setting.SERVER_PROJECT_ID),
            })
            self.db = firestore.client()
        except Exception as e:
            logger.log_struct({
                "error": "unable to initialize firestore, errors will not be logged to firestore.  If you are running this on a developer machine, this error is normal.",
                "exception": str(e)
            })
            self.db = None
        self.last_error = None

    def store(self, error_data):
        if self.db is not None:
            doc_ref = self.db.collection(u'error_reports').document(error_data.get('client', "unknown") + "-" + datetime.now().isoformat())
            doc_ref.set(error_data)
        self.last_error = error_data
