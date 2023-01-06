

from backup.model import DestinationPrecache, Model, Coordinator
from backup.config import Config, Setting
from tests.faketime import FakeTime
from dev.request_interceptor import RequestInterceptor
from dev.simulated_google import URL_MATCH_DRIVE_API
from backup.drive import DriveSource
from datetime import timedelta
import pytest


@pytest.mark.asyncio
async def test_no_caching_before_cache_time(server, precache: DestinationPrecache, model: Model, drive: DriveSource, interceptor: RequestInterceptor, coord: Coordinator, time: FakeTime) -> None:
    await coord.sync()

    interceptor.clear()
    await precache.checkForSmoothing()
    assert precache.getNextWarmDate() > time.now()
    assert not interceptor.urlWasCalled(URL_MATCH_DRIVE_API)
    assert precache.cached(drive.name(), time.now()) is None


@pytest.mark.asyncio
async def test_no_caching_after_sync_time(server, precache: DestinationPrecache, model: Model, drive: DriveSource, interceptor: RequestInterceptor, coord: Coordinator, time: FakeTime) -> None:
    await coord.sync()

    time.setNow(coord.nextSyncAttempt())
    interceptor.clear()
    await precache.checkForSmoothing()
    assert precache.getNextWarmDate() < time.now()
    assert not interceptor.urlWasCalled(URL_MATCH_DRIVE_API)
    assert precache.cached(drive.name(), time.now()) is None


@pytest.mark.asyncio
async def test_cache_after_warm_date(server, precache: DestinationPrecache, model: Model, drive: DriveSource, interceptor: RequestInterceptor, coord: Coordinator, time: FakeTime) -> None:
    await coord.sync()
    interceptor.clear()
    assert precache.getNextWarmDate() < coord.nextSyncAttempt()

    time.setNow(precache.getNextWarmDate())
    await precache.checkForSmoothing()
    assert interceptor.urlWasCalled(URL_MATCH_DRIVE_API)
    assert precache.cached(drive.name(), time.now()) is not None


async def test_no_double_caching(server, precache: DestinationPrecache, model: Model, drive: DriveSource, interceptor: RequestInterceptor, coord: Coordinator, time: FakeTime) -> None:
    await coord.sync()
    interceptor.clear()

    time.setNow(precache.getNextWarmDate())
    await precache.checkForSmoothing()
    assert precache.cached(drive.name(), time.now()) is not None

    interceptor.clear()
    time.setNow(precache.getNextWarmDate() + (coord.nextSyncAttempt() - precache.getNextWarmDate()) / 2)
    await precache.checkForSmoothing()
    assert not interceptor.urlWasCalled(URL_MATCH_DRIVE_API)
    assert precache.cached(drive.name(), time.now()) is not None


async def test_cache_expiration(server, precache: DestinationPrecache, model: Model, drive: DriveSource, interceptor: RequestInterceptor, coord: Coordinator, time: FakeTime) -> None:
    await coord.sync()

    time.setNow(precache.getNextWarmDate())
    await precache.checkForSmoothing()
    assert precache.cached(drive.name(), time.now()) is not None

    time.setNow(coord.nextSyncAttempt() + timedelta(minutes=2))
    assert precache.cached(drive.name(), time.now()) is None


async def test_cache_clear(server, precache: DestinationPrecache, model: Model, drive: DriveSource, interceptor: RequestInterceptor, coord: Coordinator, time: FakeTime) -> None:
    await coord.sync()

    time.setNow(precache.getNextWarmDate())
    await precache.checkForSmoothing()
    assert precache.cached(drive.name(), time.now()) is not None

    precache.clear()
    assert precache.cached(drive.name(), time.now()) is None


async def test_cache_error_backoff(server, precache: DestinationPrecache, model: Model, drive: DriveSource, interceptor: RequestInterceptor, coord: Coordinator, time: FakeTime) -> None:
    await coord.sync()

    time.setNow(precache.getNextWarmDate())
    interceptor.setError(URL_MATCH_DRIVE_API, status=503)
    await precache.checkForSmoothing()

    assert precache.cached(drive.name(), time.now()) is None
    delta = precache.getNextWarmDate() - time.now()
    assert delta >= timedelta(days=1)


async def test_cache_warm_date_stability(server, precache: DestinationPrecache, model: Model, drive: DriveSource, interceptor: RequestInterceptor, coord: Coordinator, time: FakeTime) -> None:
    await coord.sync()

    # The warm date shouldn't change
    last_warm = precache.getNextWarmDate()
    assert precache.getNextWarmDate() == last_warm
    time.setNow(last_warm - timedelta(minutes=1))
    assert precache.getNextWarmDate() == last_warm

    # Until the cached is warmed
    time.setNow(last_warm)
    await precache.checkForSmoothing()
    assert precache.cached(drive.name(), time.now()) is not None
    assert precache.getNextWarmDate() != last_warm


async def test_disable_caching(server, precache: DestinationPrecache, model: Model, drive: DriveSource, interceptor: RequestInterceptor, coord: Coordinator, time: FakeTime, config: Config) -> None:
    await coord.sync()
    config.override(Setting.CACHE_WARMUP_MAX_SECONDS, 0)

    time.setNow(precache.getNextWarmDate())
    await precache.checkForSmoothing()
    assert precache.cached(drive.name(), time.now()) is None
