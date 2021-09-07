import pytest

from backup.config import Config, Setting
from backup.debugworker import DebugWorker
from backup.util import GlobalInfo
from backup.logger import getLogger
from dev.simulationserver import SimulationServer
from .helpers import skipForWindows
from backup.server import ErrorStore
from .conftest import FakeTime


@pytest.mark.asyncio
async def test_dns_info(debug_worker: DebugWorker, config: Config):
    skipForWindows()
    config.override(Setting.SEND_ERROR_REPORTS, True)
    config.override(Setting.DRIVE_HOST_NAME, "localhost")
    await debug_worker.doWork()
    assert debug_worker.dns_info == {
        'localhost': {
            '127.0.0.1': 'alive',
            'localhost': 'alive'
        }
    }


@pytest.mark.asyncio
async def test_bad_host(debug_worker: DebugWorker, config: Config):
    skipForWindows()
    config.override(Setting.DRIVE_HOST_NAME, "dasdfdfgvxcvvsoejbr.com")
    await debug_worker.doWork()
    assert debug_worker.dns_info == {
        'dasdfdfgvxcvvsoejbr.com': {
            'dasdfdfgvxcvvsoejbr.com': "Name or service not known"
        }
    }


@pytest.mark.asyncio
async def test_send_error_report(time, debug_worker: DebugWorker, config: Config, global_info: GlobalInfo, server, error_store: ErrorStore):
    config.override(Setting.SEND_ERROR_REPORTS, True)
    config.override(Setting.DRIVE_HOST_NAME, "localhost")
    global_info.sync()
    global_info.success()
    global_info.sync()
    global_info.success()
    global_info.sync()
    global_info.failed(Exception())
    await debug_worker.doWork()
    report = error_store.last_error
    assert report['report']['sync_success_count'] == 2
    assert report['report']['sync_count'] == 3
    assert report['report']['failure_count'] == 1
    assert report['report']['sync_last_start'] == time.now().isoformat()
    assert report['report']['failure_time'] == time.now().isoformat()
    assert report['report']['error'] == getLogger("test").formatException(Exception())


@pytest.mark.asyncio
async def test_dont_send_error_report(time, debug_worker: DebugWorker, config: Config, global_info: GlobalInfo, server: SimulationServer, error_store: ErrorStore):
    config.override(Setting.SEND_ERROR_REPORTS, False)
    config.override(Setting.DRIVE_HOST_NAME, "localhost")
    global_info.failed(Exception())
    await debug_worker.doWork()
    assert error_store.last_error is None


@pytest.mark.asyncio
async def test_only_send_duplicates(time, debug_worker: DebugWorker, config: Config, global_info: GlobalInfo, server, error_store: ErrorStore):
    config.override(Setting.SEND_ERROR_REPORTS, True)
    config.override(Setting.DRIVE_HOST_NAME, "localhost")
    global_info.failed(Exception("boom1"))
    firstExceptionTime = time.now()
    await debug_worker.doWork()
    report = error_store.last_error
    assert report['report']["error"] == getLogger("test").formatException(Exception("boom1"))
    assert report['report']["time"] == firstExceptionTime.isoformat()

    # Same exception shouldn't cause us to send the error report again
    time.advance(days=1)
    global_info.failed(Exception("boom1"))
    await debug_worker.doWork()
    report = error_store.last_error
    assert report['report']["error"] == getLogger("test").formatException(Exception("boom1"))
    assert report['report']["time"] == firstExceptionTime.isoformat()

    # Btu a new one will send a new report
    global_info.failed(Exception("boom2"))
    await debug_worker.doWork()
    report = error_store.last_error
    assert report['report']["error"] == getLogger("test").formatException(Exception("boom2"))
    assert report['report']["time"] == time.now().isoformat()


@pytest.mark.asyncio
async def test_send_clear(time, debug_worker: DebugWorker, config: Config, global_info: GlobalInfo, server, error_store: ErrorStore):
    config.override(Setting.SEND_ERROR_REPORTS, True)
    config.override(Setting.DRIVE_HOST_NAME, "localhost")

    # Simulate failure
    global_info.failed(Exception("boom"))
    await debug_worker.doWork()

    # And then success
    global_info.success()
    time.advance(days=1)
    await debug_worker.doWork()
    report = error_store.last_error
    assert report['report'] == {
        'duration': '1 day, 0:00:00'
    }


@pytest.mark.asyncio
async def test_health_check_timing_success(server_url, time: FakeTime, debug_worker: DebugWorker, config: Config, server: SimulationServer):
    # Only do successfull checks once a day
    await debug_worker.doWork()
    assert server.interceptor.urlWasCalled("/health")
    server.interceptor.clear()

    await debug_worker.doWork()
    assert not server.interceptor.urlWasCalled("/health")

    time.advance(hours=23)
    await debug_worker.doWork()
    assert not server.interceptor.urlWasCalled("/health")

    time.advance(hours=2)
    await debug_worker.doWork()
    assert server.interceptor.urlWasCalled("/health")


@pytest.mark.asyncio
async def test_health_check_timing_failure(server_url, time: FakeTime, debug_worker: DebugWorker, config: Config, server: SimulationServer):
    # Failed helath checks retry after a minute
    server.interceptor.setError("/health", 500)

    await debug_worker.doWork()
    assert server.interceptor.urlWasCalled("/health")
    server.interceptor.clear()

    await debug_worker.doWork()
    assert not server.interceptor.urlWasCalled("/health")

    time.advance(seconds=59)
    await debug_worker.doWork()
    assert not server.interceptor.urlWasCalled("/health")

    time.advance(seconds=2)
    await debug_worker.doWork()
    assert server.interceptor.urlWasCalled("/health")
