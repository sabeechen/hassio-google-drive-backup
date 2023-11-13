import os
import json
from time import sleep

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
                               GoogleInternalError, GoogleUnexpectedError,
                               GoogleSessionError, GoogleTimeoutError, CredRefreshMyError, CredRefreshGoogleError)
from backup.creds import Creds
from backup.model import DriveBackup, DummyBackup
from ..faketime import FakeTime
from ..helpers import compareStreams, createBackupTar


class BackupHelper():
    def __init__(self, uploader, time):
        self.time = time
        self.uploader = uploader

    async def createFile(self, size=1024 * 1024 * 2, slug="testslug", name="Test Name", note=None):
        from_backup: DummyBackup = DummyBackup(
            name, self.time.toUtc(self.time.local(1985, 12, 6)), "fake source", slug, note=note, size=size)
        data = await self.uploader.upload(createBackupTar(slug, name, self.time.now(), size))
        return from_backup, data


@pytest.mark.asyncio
async def test_minimum_chunk_size(drive_requests: DriveRequests, time: FakeTime, backup_helper: BackupHelper, config: Config):
    config.override(Setting.UPLOAD_LIMIT_BYTES_PER_SECOND, BASE_CHUNK_SIZE)
    from_backup, data = await backup_helper.createFile(BASE_CHUNK_SIZE * 10)
    async with data:
        async for progress in drive_requests.create(data, {}, "unused"):
            assert time.sleeps[-1] == 1
    assert len(time.sleeps) == 11


@pytest.mark.asyncio
async def test_lower_chunk_size(drive_requests: DriveRequests, time: FakeTime, backup_helper: BackupHelper, config: Config):
    config.override(Setting.UPLOAD_LIMIT_BYTES_PER_SECOND, BASE_CHUNK_SIZE / 2)
    from_backup, data = await backup_helper.createFile(BASE_CHUNK_SIZE * 10)

    # It should still upload in 256 kb chunks, just with more delay
    async with data:
        async for progress in drive_requests.create(data, {}, "unused"):
            assert time.sleeps[-1] == 2
    assert len(time.sleeps) == 11


@pytest.mark.asyncio
async def test_higher_speed_limit(drive_requests: DriveRequests, time: FakeTime, backup_helper: BackupHelper, config: Config):
    config.override(Setting.UPLOAD_LIMIT_BYTES_PER_SECOND, BASE_CHUNK_SIZE * 2)
    from_backup, data = await backup_helper.createFile(BASE_CHUNK_SIZE * 10)

    # It should still upload in 256 kb chunks, just with more delay
    async with data:
        async for progress in drive_requests.create(data, {}, "unused"):
            assert time.sleeps[-1] == 0.5
    assert len(time.sleeps) == 11

