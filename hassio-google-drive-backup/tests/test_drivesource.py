import os
import json
from time import sleep
from wsgiref.util import setup_testing_defaults

import pytest
import asyncio
from yarl import URL
from aiohttp.client_exceptions import ClientResponseError
from backup.config import Config, Setting
from dev.simulationserver import SimulationServer
from dev.simulated_google import SimulatedGoogle, URL_MATCH_UPLOAD_PROGRESS, URL_MATCH_FILE
from dev.request_interceptor import RequestInterceptor
from backup.drive import DriveSource, FolderFinder, DriveRequests, RETRY_SESSION_ATTEMPTS, UPLOAD_SESSION_EXPIRATION_DURATION, URL_START_UPLOAD
from backup.drive.driverequests import (BASE_CHUNK_SIZE, CHUNK_UPLOAD_TARGET_SECONDS)
from backup.drive.drivesource import FOLDER_MIME_TYPE
from backup.exceptions import (BackupFolderInaccessible, BackupFolderMissingError,
                               DriveQuotaExceeded, ExistingBackupFolderError,
                               GoogleCantConnect, GoogleCredentialsExpired,
                               GoogleInternalError,
                               GoogleSessionError, GoogleTimeoutError, CredRefreshMyError, CredRefreshGoogleError)
from backup.creds import Creds
from backup.model import DriveBackup, DummyBackup
from .faketime import FakeTime
from .helpers import compareStreams, createBackupTar

RETRY_EXHAUSTION_SLEEPS = [2, 4, 8, 16, 32]


class BackupHelper():
    def __init__(self, uploader, time):
        self.time = time
        self.uploader = uploader

    async def createFile(self, size=1024 * 1024 * 2, slug="testslug", name="Test Name"):
        from_backup: DummyBackup = DummyBackup(
            name, self.time.toUtc(self.time.local(1985, 12, 6)), "fake source", slug)
        data = await self.uploader.upload(createBackupTar(slug, name, self.time.now(), size))
        return from_backup, data


@pytest.fixture
def backup_helper(uploader, time):
    return BackupHelper(uploader, time)


@pytest.mark.asyncio
async def test_sync_empty(drive) -> None:
    assert len(await drive.get()) == 0


@pytest.mark.asyncio
async def test_CRUD(backup_helper, drive, time, session) -> None:
    from_backup, data = await backup_helper.createFile()
    backup: DriveBackup = await drive.save(from_backup, data)
    assert backup.name() == "Test Name"
    assert backup.date() == time.local(1985, 12, 6)
    assert not backup.retained()
    assert backup.size() == data.size()
    assert backup.slug() == "testslug"
    assert len(backup.id()) > 0
    assert backup.backupType() == from_backup.backupType()
    assert backup.protected() == from_backup.protected()
    from_backup.addSource(backup)

    # downlaod the item, its bytes should match up
    download = await drive.read(from_backup)
    data.position(0)
    await compareStreams(data, download)

    # read the item, make sure its data matches up
    backups = await drive.get()
    assert len(backups) == 1
    backup = backups[from_backup.slug()]
    assert backup.name() == "Test Name"
    assert backup.date() == time.local(1985, 12, 6)
    assert not backup.retained()
    assert backup.size() == data.size()
    assert backup.slug() == "testslug"
    assert len(backup.id()) > 0
    assert backup.backupType() == from_backup.backupType()
    assert backup.protected() == from_backup.protected()

    # update retention
    assert not backup.retained()
    await drive.retain(from_backup, True)
    assert (await drive.get())[from_backup.slug()].retained()
    await drive.retain(from_backup, False)
    assert not (await drive.get())[from_backup.slug()].retained()

    # Delete the item, make sure its gone
    await drive.delete(from_backup)
    backups = await drive.get()
    assert len(backups) == 0


@pytest.mark.asyncio
async def test_folder_creation(drive, time, config):
    assert len(await drive.get()) == 0

    folderId = await drive.getFolderId()
    assert len(folderId) > 0

    item = await drive.drivebackend.get(folderId)
    assert not item["trashed"]
    assert item["name"] == "Home Assistant Backups"
    assert item["mimeType"] == FOLDER_MIME_TYPE
    assert item["appProperties"]['backup_folder'] == 'true'

    # sync again, assert the folder is reused
    time.advanceDay()
    os.remove(config.get(Setting.FOLDER_FILE_PATH))
    assert len(await drive.get()) == 0
    assert await drive.getFolderId() == folderId

    # trash the folder, assert we create a new one on sync
    await drive.drivebackend.update(folderId, {"trashed": True})
    assert (await drive.drivebackend.get(folderId))["trashed"] is True
    assert len(await drive.get()) == 0
    time.advanceDay()
    assert await drive.getFolderId() != folderId

    # delete the folder, assert we create a new one
    folderId = await drive.getFolderId()
    await drive.drivebackend.delete(folderId)
    time.advanceDay()
    assert len(await drive.get()) == 0
    time.advanceDay()
    assert await drive.getFolderId() != folderId


@pytest.mark.asyncio
async def test_folder_selection(drive, time):
    folder_metadata = {
        'name': "Junk Data",
        'mimeType': FOLDER_MIME_TYPE,
        'appProperties': {
            "backup_folder": "true",
        },
    }

    # create two fodlers at different times
    id_old = (await drive.drivebackend.createFolder(folder_metadata))['id']
    sleep(2)
    id_new = (await drive.drivebackend.createFolder(folder_metadata))['id']

    # Verify we use the newest
    await drive.get()
    assert await drive.getFolderId() == id_new
    assert await drive.getFolderId() != id_old


@pytest.mark.asyncio
async def test_bad_auth_creds(drive: DriveSource, time):
    drive.drivebackend.creds._refresh_token = "not_allowed"
    with pytest.raises(GoogleCredentialsExpired):
        await drive.get()
    assert time.sleeps == []


@pytest.mark.asyncio
async def test_out_of_space(backup_helper, drive: DriveSource, google: SimulatedGoogle):
    google.setDriveSpaceAvailable(100)
    from_backup, data = await backup_helper.createFile()
    with pytest.raises(DriveQuotaExceeded):
        await drive.save(from_backup, data)


@pytest.mark.asyncio
async def test_drive_dns_resolution_error(drive: DriveSource, config: Config, time):
    config.override(Setting.DRIVE_URL,
                    "http://fsdfsdasdasdf.saasdsdfsdfsd.com:2567")
    with pytest.raises(GoogleCantConnect):
        await drive.get()
    assert time.sleeps == []


@pytest.mark.asyncio
async def test_drive_connect_error(drive: DriveSource, config: Config, time):
    config.override(Setting.DRIVE_URL, "http://localhost:1034")
    with pytest.raises(GoogleCantConnect):
        await drive.get()
    assert time.sleeps == []


@pytest.mark.asyncio
async def test_upload_session_expired(drive, time, backup_helper, interceptor: RequestInterceptor):
    from_backup, data = await backup_helper.createFile()
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, status=404)
    with pytest.raises(GoogleSessionError):
        await drive.save(from_backup, data)
    assert time.sleeps == []


@pytest.mark.asyncio
async def test_upload_resume(drive: DriveSource, time, backup_helper: BackupHelper, google: SimulatedGoogle, interceptor: RequestInterceptor):
    from_backup, data = await backup_helper.createFile()
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, fail_after=1, status=500)

    # Upload, which will fail
    with pytest.raises(GoogleInternalError):
        await drive.save(from_backup, data)

    # Verify we uploaded one chunk
    assert google.chunks == [BASE_CHUNK_SIZE]

    # Retry the upload, which shoudl now pass
    interceptor.clear()
    data.position(0)
    drive_backup = await drive.save(from_backup, data)
    from_backup.addSource(drive_backup)
    assert google.chunks == [BASE_CHUNK_SIZE,
                             BASE_CHUNK_SIZE, (data.size()) - BASE_CHUNK_SIZE * 2]

    # Verify the data is correct
    data.position(0)
    await compareStreams(data, await drive.read(from_backup))


def test_chunk_size(drive: DriveSource, config: Config):
    max = config.get(Setting.MAXIMUM_UPLOAD_CHUNK_BYTES)
    assert drive.drivebackend._getNextChunkSize(
        1000000000, 0) == max
    assert drive.drivebackend._getNextChunkSize(
        1, CHUNK_UPLOAD_TARGET_SECONDS) == BASE_CHUNK_SIZE
    assert drive.drivebackend._getNextChunkSize(
        1000000000, CHUNK_UPLOAD_TARGET_SECONDS) == max
    assert drive.drivebackend._getNextChunkSize(
        BASE_CHUNK_SIZE, CHUNK_UPLOAD_TARGET_SECONDS) == BASE_CHUNK_SIZE
    assert drive.drivebackend._getNextChunkSize(
        BASE_CHUNK_SIZE, 1) == BASE_CHUNK_SIZE * CHUNK_UPLOAD_TARGET_SECONDS
    assert drive.drivebackend._getNextChunkSize(
        BASE_CHUNK_SIZE, 1.01) == BASE_CHUNK_SIZE * (CHUNK_UPLOAD_TARGET_SECONDS - 1)


def test_chunk_size_limits(drive: DriveSource, config: Config):
    config.override(Setting.MAXIMUM_UPLOAD_CHUNK_BYTES, 1)
    assert drive.drivebackend._getNextChunkSize(1000000000, 0) == BASE_CHUNK_SIZE
    assert drive.drivebackend._getNextChunkSize(1, 1000000) == BASE_CHUNK_SIZE

    config.override(Setting.MAXIMUM_UPLOAD_CHUNK_BYTES, BASE_CHUNK_SIZE * 1.5)
    assert drive.drivebackend._getNextChunkSize(1000000000, 0) == BASE_CHUNK_SIZE
    assert drive.drivebackend._getNextChunkSize(1, 1000000) == BASE_CHUNK_SIZE

    config.override(Setting.MAXIMUM_UPLOAD_CHUNK_BYTES, BASE_CHUNK_SIZE * 3.5)
    assert drive.drivebackend._getNextChunkSize(1000000000, 0) == BASE_CHUNK_SIZE * 3
    assert drive.drivebackend._getNextChunkSize(1, 1000000) == BASE_CHUNK_SIZE



@pytest.mark.asyncio
async def test_working_through_upload(drive: DriveSource, server: SimulationServer, backup_helper: BackupHelper, interceptor: RequestInterceptor):
    assert not drive.isWorking()

    # Let a single chunk upload, then wait
    matcher = interceptor.setWaiter(URL_MATCH_UPLOAD_PROGRESS, attempts=1)
    from_backup, data = await backup_helper.createFile(size=1024 * 1024 * 10)
    save_task = asyncio.create_task(drive.save(from_backup, data))
    await matcher.waitForCall()
    assert drive.isWorking()

    # let it complete
    matcher.clear()
    await save_task
    assert not drive.isWorking()


@pytest.mark.asyncio
async def test_drive_timeout(drive, config, time: FakeTime):
    # Ensure we have credentials
    await drive.get()

    config.override(Setting.GOOGLE_DRIVE_TIMEOUT_SECONDS, 0.000001)
    with pytest.raises(GoogleTimeoutError):
        await drive.get()
    assert time.sleeps == []


@pytest.mark.asyncio
async def test_resume_upload_attempts_exhausted(drive: DriveSource, time, backup_helper, interceptor: RequestInterceptor, google: SimulatedGoogle):
    # Allow an upload to update one chunk and then fail.
    from_backup, data = await backup_helper.createFile()
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, fail_after=1, status=500)
    with pytest.raises(GoogleInternalError):
        await drive.save(from_backup, data)
    assert google.chunks == [BASE_CHUNK_SIZE]

    # Verify we have a cached location
    assert drive.drivebackend.last_attempt_location is not None
    assert drive.drivebackend.last_attempt_count == 1
    last_location = drive.drivebackend.last_attempt_location

    for x in range(1, RETRY_SESSION_ATTEMPTS):
        data.position(0)
        with pytest.raises(GoogleInternalError):
            await drive.save(from_backup, data)
        assert drive.drivebackend.last_attempt_count == x + 1

    # We should still be using the same location url
    assert drive.drivebackend.last_attempt_location == last_location

    # Another attempt should use another location url
    with pytest.raises(GoogleInternalError):
        data.position(0)
        await drive.save(from_backup, data)
    assert drive.drivebackend.last_attempt_count == 0
    assert drive.drivebackend.last_attempt_location is not None
    assert drive.drivebackend.last_attempt_location != last_location

    # Now let it succeed
    interceptor.clear()
    data.position(0)
    drive_backup = await drive.save(from_backup, data)
    from_backup.addSource(drive_backup)

    # And verify the bytes are correct
    data.position(0)
    await compareStreams(data, await drive.read(from_backup))


@pytest.mark.asyncio
async def test_google_internal_error(drive, server, time: FakeTime, interceptor: RequestInterceptor):
    interceptor.setError(URL_MATCH_FILE, 500)
    with pytest.raises(GoogleInternalError):
        await drive.get()
    assert time.sleeps == RETRY_EXHAUSTION_SLEEPS
    time.clearSleeps()

    interceptor.clear()
    interceptor.setError(URL_MATCH_FILE, 500)
    with pytest.raises(GoogleInternalError):
        await drive.get()
    assert time.sleeps == RETRY_EXHAUSTION_SLEEPS


@pytest.mark.asyncio
async def test_check_time(drive: DriveSource, drive_creds: Creds):
    assert not drive.check()
    drive.saveCreds(drive_creds)
    assert drive.check()


@pytest.mark.asyncio
async def test_disable_upload(drive: DriveSource, config: Config):
    assert drive.upload()
    config.override(Setting.ENABLE_DRIVE_UPLOAD, False)
    assert not drive.upload()


@pytest.mark.asyncio
async def test_resume_session_abandoned_on_http4XX(time, drive: DriveSource, config: Config, server, backup_helper, interceptor: RequestInterceptor):
    from_backup, data = await backup_helper.createFile()

    # Configure the upload to fail after the first upload chunk
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, 402, 1)
    with pytest.raises(ClientResponseError):
        await drive.save(from_backup, data)

    # Verify a requst was made to start the upload but not cached
    assert server.wasUrlRequested(
        "/upload/drive/v3/files/?uploadType=resumable&supportsAllDrives=true")
    assert drive.drivebackend.last_attempt_count == 1
    assert drive.drivebackend.last_attempt_location is None
    assert drive.drivebackend.last_attempt_metadata is None

    # upload again, which should retry
    server.urls.clear()
    interceptor.clear()
    data.position(0)
    backup = await drive.save(from_backup, data)
    assert server.wasUrlRequested(URL_START_UPLOAD)

    # Verify the uploaded bytes are identical
    from_backup.addSource(backup)
    download = await drive.read(from_backup)
    data.position(0)
    await compareStreams(data, download)


@pytest.mark.asyncio
async def test_resume_session_abandoned_after_a_long_time(time: FakeTime, drive: DriveSource, config: Config, server: SimulationServer, backup_helper, interceptor: RequestInterceptor):
    from_backup, data = await backup_helper.createFile()

    # Configure the upload to fail after the first upload chunk
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, 501, 1)
    with pytest.raises(ClientResponseError):
        await drive.save(from_backup, data)

    # Verify it reuses the session a few times
    assert server.wasUrlRequested(URL_START_UPLOAD)
    assert drive.drivebackend.last_attempt_count == 1
    assert drive.drivebackend.last_attempt_location is not None
    assert drive.drivebackend.last_attempt_metadata is not None

    data.position(0)
    with pytest.raises(ClientResponseError):
        await drive.save(from_backup, data)
    assert drive.drivebackend.last_attempt_count == 2
    assert drive.drivebackend.last_attempt_location is not None
    assert drive.drivebackend.last_attempt_metadata is not None
    last_location = drive.drivebackend.last_attempt_location

    # Fast forward a lot, then verify the session is restarted
    server.urls.clear()
    interceptor.clear()
    time.advance(duration=UPLOAD_SESSION_EXPIRATION_DURATION)
    data.position(0)
    await drive.save(from_backup, data)
    assert interceptor.urlWasCalled(URL_START_UPLOAD)
    assert not interceptor.urlWasCalled(last_location)


@pytest.mark.asyncio
async def test_chunk_upload_resets_attempt_counter(time: FakeTime, drive: DriveSource, config: Config, server: SimulationServer, backup_helper: BackupHelper, interceptor: RequestInterceptor):
    from_backup, data = await backup_helper.createFile(size=1024 * 1024 * 10)

    # Configure the upload to fail after the first upload chunk
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, 501, 1)
    with pytest.raises(ClientResponseError):
        await drive.save(from_backup, data)

    data.position(0)
    with pytest.raises(ClientResponseError):
        await drive.save(from_backup, data)

    # Verify the session was started
    assert interceptor.urlWasCalled(URL_START_UPLOAD)
    assert interceptor.urlWasCalled(URL_MATCH_UPLOAD_PROGRESS)
    assert drive.drivebackend.last_attempt_count == 2
    location = drive.drivebackend.last_attempt_location
    assert location is not None

    # Allow one more chunk to succeed
    interceptor.clear()
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, 501, 2)
    data.position(0)
    with pytest.raises(ClientResponseError):
        await drive.save(from_backup, data)

    # Verify the session was reused and the attempt counter was reset
    assert not interceptor.urlWasCalled(URL_START_UPLOAD)
    assert interceptor.urlWasCalled(URL_MATCH_UPLOAD_PROGRESS)
    assert interceptor.urlWasCalled(URL(location).path)
    assert drive.drivebackend.last_attempt_count == 1
    assert drive.drivebackend.last_attempt_location == location


@pytest.mark.asyncio
async def test_resume_session_reused_on_http5XX(time, drive: DriveSource, config: Config, server, backup_helper, interceptor: RequestInterceptor):
    await verify_upload_resumed(time, drive, config, server, interceptor, 550, backup_helper)


@pytest.mark.asyncio
async def test_resume_session_reused_abonded_after_retries(time, drive: DriveSource, config: Config, server: SimulationServer, backup_helper, interceptor: RequestInterceptor):
    from_backup, data = await backup_helper.createFile()

    # Configure the upload to fail after the first upload chunk
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, 501, 1)
    with pytest.raises(ClientResponseError):
        await drive.save(from_backup, data)

    # Verify a requst was made to start the upload but not cached
    assert server.wasUrlRequested(URL_START_UPLOAD)
    assert drive.drivebackend.last_attempt_count == 1
    assert drive.drivebackend.last_attempt_location is not None
    assert drive.drivebackend.last_attempt_metadata is not None
    last_location = drive.drivebackend.last_attempt_location

    for x in range(1, RETRY_SESSION_ATTEMPTS):
        server.urls.clear()
        interceptor.clear()
        interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, 501)
        data.position(0)
        with pytest.raises(ClientResponseError):
            await drive.save(from_backup, data)
        assert not server.wasUrlRequested(URL_START_UPLOAD)
        assert server.wasUrlRequested(last_location)
        assert drive.drivebackend.last_attempt_count == x + 1
        assert drive.drivebackend.last_attempt_location is last_location
        assert drive.drivebackend.last_attempt_metadata is not None

    # Next attempt should give up and restart the upload
    server.urls.clear()
    interceptor.clear()
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, 501, 1)
    data.position(0)
    with pytest.raises(ClientResponseError):
        await drive.save(from_backup, data)
    assert server.wasUrlRequested(URL_START_UPLOAD)
    assert not server.wasUrlRequested(last_location)
    assert drive.drivebackend.last_attempt_count == 1

    # upload again, which should retry
    server.urls.clear()
    interceptor.clear()
    data.position(0)
    backup = await drive.save(from_backup, data)
    assert not server.wasUrlRequested(URL_START_UPLOAD)

    # Verify the uploaded bytes are identical
    from_backup.addSource(backup)
    download = await drive.read(from_backup)
    data.position(0)
    await compareStreams(data, download)


async def verify_upload_resumed(time, drive: DriveSource, config: Config, server: SimulationServer, interceptor: RequestInterceptor, status, backup_helper, expected=ClientResponseError):
    from_backup, data = await backup_helper.createFile()

    # Configure the upload to fail after the first upload chunk
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, status, 1)
    with pytest.raises(expected):
        await drive.save(from_backup, data)

    # Verify a requst was made to start the upload
    assert server.wasUrlRequested(URL_START_UPLOAD)
    assert drive.drivebackend.last_attempt_location is not None
    assert drive.drivebackend.last_attempt_metadata is not None
    last_location = drive.drivebackend.last_attempt_location

    # Retry the upload and let is succeed
    server.urls.clear()
    interceptor.clear()
    data.position(0)
    backup = await drive.save(from_backup, data)

    # We shoudl nto see the upload "initialize" url
    assert not server.wasUrlRequested(URL_START_UPLOAD)

    # We should see the last location url (which has a unique token) reused to resume the upload
    assert server.wasUrlRequested(last_location)

    # The saved metadata should be cleared out.
    assert drive.drivebackend.last_attempt_count == 1
    assert drive.drivebackend.last_attempt_location is None
    assert drive.drivebackend.last_attempt_metadata is None

    # Verify the uploaded bytes are identical
    from_backup.addSource(backup)
    download = await drive.read(from_backup)
    data.position(0)
    await compareStreams(data, download)


@pytest.mark.asyncio
async def test_recreate_folder_when_deleted(time, drive: DriveSource, config: Config, backup_helper, folder_finder: FolderFinder):
    await drive.get()
    id = await drive.getFolderId()
    await drive.drivebackend.delete(id)
    assert len(await drive.get()) == 0
    assert id != await drive.getFolderId()


@pytest.mark.asyncio
async def test_recreate_folder_when_losing_permissions(time, drive: DriveSource, config: Config, backup_helper, google: SimulatedGoogle):
    await drive.get()
    id = await drive.getFolderId()
    google.lostPermission.append(id)
    assert len(await drive.get()) == 0
    assert id != await drive.getFolderId()


@pytest.mark.asyncio
async def test_folder_missing_on_upload(time, drive: DriveSource, config: Config, backup_helper):
    # Make the folder
    await drive.get()

    # Require a specified folder so we don't query
    config.override(Setting.SPECIFY_BACKUP_FOLDER, True)

    # Delete the folder
    await drive.drivebackend.delete(await drive.getFolderId())

    # Then try to make one
    from_backup, data = await backup_helper.createFile()

    # Configure the upload to fail after the first upload chunk
    with pytest.raises(BackupFolderInaccessible):
        await drive.save(from_backup, data)


@pytest.mark.asyncio
async def test_folder_error_on_upload_lost_permission(time, drive: DriveSource, config: Config, google: SimulatedGoogle, backup_helper, session):
    # Make the folder
    await drive.get()

    # Require a specified folder so we don't query
    config.override(Setting.SPECIFY_BACKUP_FOLDER, True)

    # Make the folder inaccessible
    google.lostPermission.append(await drive.getFolderId())
    time.advanceDay()

    # Fail to upload
    with pytest.raises(BackupFolderInaccessible):
        await drive.save(*await backup_helper.createFile())


@pytest.mark.asyncio
async def test_folder_error_on_upload_lost_permission_custom_client(time, drive: DriveSource, config: Config, google: SimulatedGoogle, backup_helper, session):
    # Make the folder
    await drive.get()

    # Require a specified folder so we don't query
    config.override(Setting.SPECIFY_BACKUP_FOLDER, True)

    google._client_id_hack = config.get(Setting.DEFAULT_DRIVE_CLIENT_ID)
    config.override(Setting.DEFAULT_DRIVE_CLIENT_ID, "something-else")

    # Make the folder inaccessible
    google.lostPermission.append(await drive.getFolderId())
    time.advanceDay()

    # Fail to upload
    with pytest.raises(BackupFolderInaccessible):
        await drive.save(*await backup_helper.createFile())


@pytest.mark.asyncio
async def test_folder_error_on_query_lost_permission(time, drive: DriveSource, config: Config, google: SimulatedGoogle):
    # Make the folder
    await drive.get()

    # Require a specified folder so we don't query
    config.override(Setting.SPECIFY_BACKUP_FOLDER, "true")
    config.override(Setting.DEFAULT_DRIVE_CLIENT_ID, "something")

    # Make the folder inaccessible
    google.lostPermission.append(await drive.getFolderId())

    # It shoudl fail!
    with pytest.raises(BackupFolderInaccessible):
        await drive.get()


@pytest.mark.asyncio
async def test_folder_error_on_query_deleted(time, drive: DriveSource, config: Config, server):
    # Make the folder
    await drive.get()

    # Require a specified folder so we don't query
    config.override(Setting.SPECIFY_BACKUP_FOLDER, "true")
    config.override(Setting.DEFAULT_DRIVE_CLIENT_ID, "something")

    # Delete the folder
    await drive.drivebackend.delete(await drive.getFolderId())

    # It should fail!
    with pytest.raises(BackupFolderInaccessible):
        await drive.get()


@pytest.mark.asyncio
async def test_backup_folder_not_specified(time, drive: DriveSource, config: Config, server, backup_helper):
    config.override(Setting.SPECIFY_BACKUP_FOLDER, "true")

    with pytest.raises(BackupFolderMissingError):
        await drive.get()

    from_backup, data = await backup_helper.createFile()
    with pytest.raises(BackupFolderMissingError):
        await drive.save(from_backup, data)

    config.override(Setting.DEFAULT_DRIVE_CLIENT_ID, "something")
    with pytest.raises(BackupFolderMissingError):
        await drive.get()
    with pytest.raises(BackupFolderMissingError):
        await drive.save(from_backup, data)


@pytest.mark.asyncio
async def test_folder_invalid_when_specified(time, drive: DriveSource, config: Config, server):
    await drive.get()

    config.override(Setting.SPECIFY_BACKUP_FOLDER, "true")
    await drive.drivebackend.update(await drive.getFolderId(), {"trashed": True})

    time.advanceDay()

    with pytest.raises(BackupFolderInaccessible):
        await drive.get()


@pytest.mark.asyncio
async def test_no_folder_when_required(time, drive: DriveSource, config: Config):
    config.override(Setting.SPECIFY_BACKUP_FOLDER, "true")
    with pytest.raises(BackupFolderMissingError):
        await drive.get()


@pytest.mark.asyncio
async def test_existing_folder_already_exists(time, drive: DriveSource, config: Config, folder_finder: FolderFinder):
    await drive.get()
    drive.checkBeforeChanges()

    # Reset folder, try again
    folder_finder.reset()
    await drive.get()
    with pytest.raises(ExistingBackupFolderError):
        drive.checkBeforeChanges()


@pytest.mark.asyncio
async def test_existing_resolved_use_existing(time, drive: DriveSource, config: Config, folder_finder: FolderFinder):
    await drive.get()
    drive.checkBeforeChanges()

    folder_id = await drive.getFolderId()

    # Reset folder, try again
    folder_finder.reset()
    await drive.get()
    with pytest.raises(ExistingBackupFolderError):
        drive.checkBeforeChanges()

    folder_finder.resolveExisting(True)
    await drive.get()
    drive.checkBeforeChanges()
    assert await drive.getFolderId() == folder_id


@pytest.mark.asyncio
async def test_existing_resolved_create_new(time, drive: DriveSource, config: Config, folder_finder: FolderFinder):
    await drive.get()
    drive.checkBeforeChanges()

    folder_id = await drive.getFolderId()

    # Reset folder, try again
    folder_finder.reset()
    await drive.get()
    with pytest.raises(ExistingBackupFolderError):
        drive.checkBeforeChanges()

    folder_finder.resolveExisting(False)
    await drive.get()
    drive.checkBeforeChanges()
    assert await drive.getFolderId() != folder_id


@pytest.mark.asyncio
async def test_cred_refresh_with_secret(drive: DriveSource, google: SimulatedGoogle, time: FakeTime, config: Config):
    google.resetDriveAuth()
    with open(config.get(Setting.CREDENTIALS_FILE_PATH), "w") as f:
        creds = google.creds()
        creds._secret = config.get(Setting.DEFAULT_DRIVE_CLIENT_SECRET)
        json.dump(creds.serialize(), f)
    drive.drivebackend.tryLoadCredentials()
    await drive.get()
    old_creds = drive.drivebackend.creds

    # valid creds should be reused
    await drive.get()
    assert old_creds.access_token == drive.drivebackend.creds.access_token

    # then refreshed when they expire
    time.advanceDay()
    await drive.get()
    assert old_creds.access_token != drive.drivebackend.creds.access_token

    # verify the client_secret is kept
    with open(config.get(Setting.CREDENTIALS_FILE_PATH)) as f:
        assert "client_secret" in json.load(f)


@pytest.mark.asyncio
async def test_cred_refresh_no_secret(drive: DriveSource, google: SimulatedGoogle, time: FakeTime, config: Config):
    drive.saveCreds(google.creds())
    await drive.get()
    old_creds = drive.drivebackend.creds
    await drive.get()
    assert old_creds.access_token == drive.drivebackend.creds.access_token
    time.advanceDay()
    await drive.get()
    assert old_creds.access_token != drive.drivebackend.creds.access_token
    with open(config.get(Setting.CREDENTIALS_FILE_PATH)) as f:
        assert "client_secret" not in json.load(f)


@pytest.mark.asyncio
async def test_cred_refresh_upgrade_default_client(drive: DriveSource, server: SimulationServer, time: FakeTime, config: Config):
    return
    # TODO: Enable this when we start removing the default client_secret
    config.override(Setting.DEFAULT_DRIVE_CLIENT_ID, server.getSetting("drive_client_id"))
    creds = server.getCurrentCreds()
    creds_with_secret = server.getCurrentCreds()
    creds_with_secret._secret = server.getSetting("drive_client_secret")
    with open(config.get(Setting.CREDENTIALS_FILE_PATH), "w") as f:
        json.dump(creds_with_secret.serialize(), f)

    # reload the creds
    drive.drivebackend.tryLoadCredentials()

    # Verify the "client secret" was removed
    with open(config.get(Setting.CREDENTIALS_FILE_PATH)) as f:
        saved_creds = json.load(f)
        assert saved_creds == creds.serialize()

    await drive.get()
    old_creds = drive.drivebackend.cred_bearer
    await drive.get()
    assert old_creds == drive.drivebackend.cred_bearer
    time.advanceDay()
    await drive.get()
    assert old_creds != drive.drivebackend.cred_bearer


@pytest.mark.asyncio
async def test_cant_reach_refresh_server(drive: DriveSource, server: SimulationServer, config: Config, time):
    config.override(Setting.TOKEN_SERVER_HOSTS, "http://lkasdpoiwehjhcty.com")
    drive.drivebackend.creds._secret = None
    time.advanceDay()
    with pytest.raises(CredRefreshMyError) as error:
        await drive.get()
    assert error.value.data() == {"reason": "Couldn't communicate with lkasdpoiwehjhcty.com"}


@pytest.mark.asyncio
async def test_refresh_problem_with_google(drive: DriveSource, interceptor: RequestInterceptor, config: Config, time):
    time.advanceDay()
    interceptor.setError(".*/oauth2/v4/token.*", status=510)
    drive.drivebackend.creds._secret = None
    with pytest.raises(CredRefreshGoogleError) as error:
        await drive.get()
    assert error.value.data() == {"from_google": "Google returned HTTP 510"}


@pytest.mark.asyncio
async def test_ignore_trashed_backups(time, drive: DriveSource, config: Config, server, backup_helper):
    backup = await backup_helper.createFile()
    drive_backup = await drive.save(*backup)

    assert len(await drive.get()) == 1
    await drive.drivebackend.update(drive_backup.id(), {"trashed": True})

    assert len(await drive.get()) == 0


@pytest.mark.asyncio
async def test_download_timeout(time, drive: DriveSource, config: Config, interceptor: RequestInterceptor, backup_helper):
    config.override(Setting.DOWNLOAD_TIMEOUT_SECONDS, 0.1)
    from_backup, data = await backup_helper.createFile()
    backup = await drive.save(from_backup, data)

    # Verify the uploaded bytes are identical
    from_backup.addSource(backup)
    interceptor.setSleep(URL_MATCH_FILE, sleep=100)
    download = await drive.read(from_backup)
    data.position(0)

    with pytest.raises(GoogleTimeoutError):
        await compareStreams(data, download)


@pytest.mark.asyncio
async def test_resume_session_reused_on_http410(time, drive: DriveSource, config: Config, server: SimulationServer, backup_helper: BackupHelper, interceptor: RequestInterceptor):
    from_backup, data = await backup_helper.createFile()

    # Configure the upload to fail
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, 500)
    with pytest.raises(GoogleInternalError):
        await drive.save(from_backup, data)

    # Verify a requst was made to start the upload
    assert server.wasUrlRequested(URL_START_UPLOAD)
    assert drive.drivebackend.last_attempt_location is not None

    server.urls.clear()
    interceptor.clear()
    data.position(0)

    interceptor.setError(drive.drivebackend.last_attempt_location, 0, 410)
    await drive.save(from_backup, data)


@pytest.mark.asyncio
async def test_resume_session_reused_on_http408(time, drive: DriveSource, config: Config, server: SimulationServer, backup_helper: BackupHelper, interceptor: RequestInterceptor):
    from_backup, data = await backup_helper.createFile()

    # Configure the upload to fail
    interceptor.setError(URL_MATCH_UPLOAD_PROGRESS, 408)
    with pytest.raises(GoogleTimeoutError):
        await drive.save(from_backup, data)

    # Verify a requst was made to start the upload
    assert server.wasUrlRequested(URL_START_UPLOAD)
    location = drive.drivebackend.last_attempt_location
    assert location is not None

    server.urls.clear()
    interceptor.clear()
    data.position(0)

    await drive.save(from_backup, data)
    assert interceptor.urlWasCalled(URL(location).path)


@pytest.mark.asyncio
async def test_shared_drive_manager(drive: DriveSource, time: FakeTime, folder_finder: FolderFinder, backup_helper: BackupHelper, drive_requests: DriveRequests):
    # Make a shared drive folder
    folder_metadata = {
        'name': "Shared Drive",
        'mimeType': FOLDER_MIME_TYPE,
        'driveId': "test_shared_drive_id",
        'appProperties': {
            "backup_folder": "true",
        },
    }
    shared_drive_folder_id = (await drive.drivebackend.createFolder(folder_metadata))['id']
    await folder_finder.save(shared_drive_folder_id)

    # Save a backup
    from_backup, data = await backup_helper.createFile()
    backup = await drive.save(from_backup, data)
    assert len(await drive.get()) == 1
    from_backup.addSource(backup)

    # Delete the backup, and verify it was deleted instead of trashed
    await drive.delete(from_backup)
    assert len(await drive.get()) == 0
    with pytest.raises(ClientResponseError) as exc:
        await drive_requests.get(backup.id())
    assert exc.value.code == 404


@pytest.mark.asyncio
async def test_shared_drive_content_manager(drive: DriveSource, time: FakeTime, folder_finder: FolderFinder, backup_helper: BackupHelper, drive_requests: DriveRequests):
    # Make a shared drive folder where the user has capabilities consistent with a "content manager" role.
    folder_metadata = {
        'name': "Shared Drive",
        'mimeType': FOLDER_MIME_TYPE,
        'driveId': "test_shared_drive_id",
        'appProperties': {
            "backup_folder": "true",
        },
        'capabilities': {
            'canDeleteChildren': False,
            'canTrashChildren': True,
            'canDelete': False,
            'canTrash': True,
        }
    }

    shared_drive_folder_id = (await drive.drivebackend.createFolder(folder_metadata))['id']
    await folder_finder.save(shared_drive_folder_id)

    # Save a backup
    from_backup, data = await backup_helper.createFile()
    backup = await drive.save(from_backup, data)
    assert len(await drive.get()) == 1
    from_backup.addSource(backup)

    # Delete the backup, and verify it was onyl trashed
    await drive.delete(from_backup)
    assert len(await drive.get()) == 0
    assert (await drive_requests.get(backup.id()))['trashed']
