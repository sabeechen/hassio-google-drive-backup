from abc import ABC, abstractmethod

from ..const import (DRIVE_FOLDER_URL_FORMAT, ERROR_BACKUP_FOLDER_INACCESSIBLE,
                     ERROR_BACKUP_FOLDER_MISSING, ERROR_BAD_PASSWORD_KEY,
                     ERROR_CREDS_EXPIRED, ERROR_DRIVE_FULL,
                     ERROR_EXISTING_FOLDER, ERROR_GOOGLE_CONNECT, ERROR_GOOGLE_CRED_PROCESS,
                     ERROR_GOOGLE_DNS, ERROR_GOOGLE_INTERNAL,
                     ERROR_GOOGLE_SESSION, ERROR_GOOGLE_TIMEOUT,
                     ERROR_HA_DELETE_ERROR, ERROR_INVALID_CONFIG, ERROR_LOGIC,
                     ERROR_LOW_SPACE, ERROR_MULTIPLE_DELETES, ERROR_NO_BACKUP,
                     ERROR_NOT_UPLOADABLE, ERROR_PLEASE_WAIT, ERROR_PROTOCOL,
                     ERROR_BACKUP_IN_PROGRESS, ERROR_UPLOAD_FAILED, LOG_IN_TO_DRIVE,
                     SUPERVISOR_PERMISSION, ERROR_GOOGLE_UNEXPECTED, ERROR_SUPERVISOR_TIMEOUT, ERROR_SUPERVISOR_UNEXPECTED, ERROR_SUPERVISOR_FILE_SYSTEM)


def ensureKey(key, target, name):
    if key not in target:
        raise ProtocolError(key, name, target)
    return target[key]


class KnownError(Exception, ABC):
    @abstractmethod
    def message(self) -> str:
        pass

    @abstractmethod
    def code(self) -> str:
        pass

    def httpStatus(self) -> int:
        return 500

    def data(self):
        return {}

    def retrySoon(self):
        return True


class KnownTransient(KnownError):
    pass


class SimulatedError(KnownError):
    def __init__(self, code=None):
        self._code = code

    def code(self):
        return self._code

    def message(self):
        return "Gave code " + str(self._code)


class LogicError(KnownError):
    def __init__(self, message=None):
        self._message = message

    def message(self):
        return self._message

    def code(self):
        return ERROR_LOGIC


class ProtocolError(KnownError):
    def __init__(self, parameter=None, object_name=None, debug_object=None):
        self._parameter = parameter
        self._object_name = object_name
        self._debug_object = debug_object

    def message(self):
        if self._object_name:
            return "Required key '{0}' was missing from {1}".format(self._parameter, self._object_name)
        else:
            return self._parameter

    def code(self):
        return ERROR_PROTOCOL


class BackupInProgress(KnownError):
    def message(self):
        return "A backup is already in progress"

    def code(self):
        return ERROR_BACKUP_IN_PROGRESS


class BackupPasswordKeyInvalid(KnownError):
    def message(self):
        return "Couldn't find your backup password in your secrets file.  Please check your settings."

    def code(self):
        return ERROR_BAD_PASSWORD_KEY

    def retrySoon(self):
        return False


class UploadFailed(KnownError):
    def message(self):
        return "Backup upload failed.  Please check the supervisor logs for details."

    def code(self):
        return ERROR_UPLOAD_FAILED


class GoogleCredentialsExpired(KnownError):
    def message(self):
        return "Your Google Drive credentials have expired.  Please reauthorize with Google Drive through the Web UI."

    def code(self):
        return ERROR_CREDS_EXPIRED

    def retrySoon(self):
        return False


class NoBackup(KnownError):
    def message(self):
        return "The backup doesn't exist anymore"

    def code(self):
        return ERROR_NO_BACKUP


class NotUploadable(KnownError):
    def message(self):
        return "This backup can't be uploaded to Home Assistant yet"

    def code(self):
        return ERROR_NOT_UPLOADABLE


class PleaseWait(KnownError):
    def message(self):
        return "Please wait until the sync is finished."

    def code(self):
        return ERROR_PLEASE_WAIT


class InvalidConfigurationValue(KnownError):
    def __init__(self, key=None, current=None):
        self.key = key
        self.current = current

    def message(self):
        return "'{0}' isn't a valid value for {1}".format(str(self.current), str(self.key))

    def code(self):
        return ERROR_INVALID_CONFIG


# UI Handler Done and updated

class DeleteMutlipleBackupsError(KnownError):
    def __init__(self, delete_sources=None):
        self.delete_sources = delete_sources

    def message(self):
        return "The add-on has been configured to delete more than one older backups.  Please confirm this by visiting the add-on's web UI or by setting the config option 'confirm_multiple_deletes'=false in your add-on configuration."

    def code(self):
        return ERROR_MULTIPLE_DELETES

    def data(self):
        return self.delete_sources

    def retrySoon(self):
        return False


class DriveQuotaExceeded(KnownError):
    def message(self):
        return "Google Drive is out of space"

    def code(self):
        return ERROR_DRIVE_FULL

    def retrySoon(self):
        return False


class GoogleDnsFailure(KnownError):
    def message(self):
        return "Unable to resolve host www.googleapis.com"

    def code(self):
        return ERROR_GOOGLE_DNS


class GoogleCantConnect(KnownError):
    def message(self):
        return "Unable to connect to www.googleapis.com"

    def code(self):
        return ERROR_GOOGLE_CONNECT


class GoogleInternalError(KnownTransient):
    def message(self):
        return "Google Drive returned an internal error (HTTP: 5XX)"

    def code(self):
        return ERROR_GOOGLE_INTERNAL


class GoogleTimeoutError(KnownError):
    def message(self):
        return "Timed out while trying to reach Google Drive"

    def code(self):
        return ERROR_GOOGLE_TIMEOUT

    @classmethod
    def factory(cls):
        return GoogleTimeoutError()


class GoogleRateLimitError(KnownTransient):
    def message(self):
        return "The addon has made too many requests to Google Drive, and will back off"

    def code(self):
        return "google_rate_limit"


class GoogleSessionError(KnownError):
    def message(self):
        return "Upload session with Google Drive expired.  The upload could not complete."

    def code(self):
        return ERROR_GOOGLE_SESSION


class HomeAssistantDeleteError(KnownError):
    def message(self):
        return "Home Assistant refused to delete the backup."

    def code(self):
        return ERROR_HA_DELETE_ERROR


class ExistingBackupFolderError(KnownError):
    def __init__(self, existing_id: str = None, existing_name: str = None):
        self.existing_id = existing_id
        self.existing_name = existing_name

    def message(self):
        return "A backup folder already exists.  Please visit the add-on Web UI to select where to backup."

    def code(self):
        return ERROR_EXISTING_FOLDER

    def data(self):
        return {
            "existing_url#href": DRIVE_FOLDER_URL_FORMAT.format(self.existing_id),
            "existing_name": self.existing_name
        }

    def retrySoon(self):
        return False


class BackupFolderMissingError(KnownError):
    def message(self):
        return "Please visit the add-on Web UI to select where to backup."

    def code(self):
        return ERROR_BACKUP_FOLDER_MISSING

    def retrySoon(self):
        return False


class BackupFolderInaccessible(KnownError):
    def __init__(self, existing_id: str = None):
        self.existing_id = existing_id

    def message(self):
        return "The choosen backup folder has become inaccessible.  Please visit the addon web UI to select a backup folder."

    def data(self):
        return {
            "existing_url#href": DRIVE_FOLDER_URL_FORMAT.format(self.existing_id)
        }

    def code(self):
        return ERROR_BACKUP_FOLDER_INACCESSIBLE


class GoogleDrivePermissionDenied(KnownError):
    def message(self):
        return "Google Drive denied the request due to permissions."

    def code(self):
        return "google_drive_permissions"


class LowSpaceError(KnownError):
    def __init__(self, pct_used=None, space_remaining=None):
        self.pct_used = pct_used
        self.space_remaining = space_remaining

    def message(self):
        return "Your backup folder is low on disk space.  Backups can't be created until space is available."

    def code(self):
        return ERROR_LOW_SPACE

    def data(self):
        return {
            "pct_used": self.pct_used,
            "space_remaining": self.space_remaining
        }


class SupervisorConnectionError(KnownError):
    def message(self):
        return "The addon couldn't connect to the supervisor.  Backups can't continue until the supervisor is responding."

    def code(self):
        return "supervisor_connection"


class UserCancelledError(KnownError):
    def message(self):
        return "Sync was cancelled by you"

    def code(self):
        return "cancelled"

    def retrySoon(self):
        return False


class CredRefreshGoogleError(KnownError):
    def __init__(self, from_google=None):
        self.from_google = from_google

    def message(self):
        return "Couldn't refresh your credentials with Google because: '{}'".format(self.from_google)

    def code(self):
        return "token_refresh_google_error"

    def data(self):
        return {
            "from_google": self.from_google
        }


class CredRefreshMyError(KnownError):
    def __init__(self, reason: str = None):
        self.reason = reason

    def message(self):
        return "Couldn't refresh Google Drive credentials because: {}".format(self.reason)

    def code(self):
        return "token_refresh_my_error"

    def data(self):
        return {
            "reason": self.reason
        }


class LogInToGoogleDriveError(KnownError):
    def message(self):
        return "Please visit drive.google.com to activate your Google Drive account."

    def code(self):
        return LOG_IN_TO_DRIVE

    def retrySoon(self):
        return False


class SupervisorPermissionError(KnownError):
    def message(self):
        return "The supervisor is rejecting requests from the addon.  Please visit the web-UI for guidance"

    def code(self):
        return SUPERVISOR_PERMISSION

    def retrySoon(self):
        return True


class GoogleUnexpectedError(KnownError):
    def message(self):
        return "Google gave an unexpected response"

    def code(self):
        return ERROR_GOOGLE_UNEXPECTED

    @classmethod
    def factory(cls):
        return GoogleUnexpectedError()


class SupervisorTimeoutError(KnownError):
    def message(self):
        return "A request to the supervisor timed out"

    def code(self):
        return ERROR_SUPERVISOR_TIMEOUT

    @classmethod
    def factory(cls):
        return SupervisorTimeoutError()


class SupervisorUnexpectedError(KnownError):
    def message(self):
        return "The supervisor gave an unexpected response"

    def code(self):
        return ERROR_SUPERVISOR_UNEXPECTED

    @classmethod
    def factory(cls):
        return SupervisorUnexpectedError()


class SupervisorFileSystemError(KnownError):
    def message(self):
        return "The host file system is read-only.  Please restart Home Assistant and verify you have enough free space."

    def code(self):
        return ERROR_SUPERVISOR_FILE_SYSTEM


class GoogleCredGenerateError(KnownError):
    def __init__(self, message):
        self._msg = message

    def message(self):
        return self._msg

    def code(self):
        return ERROR_GOOGLE_CRED_PROCESS
