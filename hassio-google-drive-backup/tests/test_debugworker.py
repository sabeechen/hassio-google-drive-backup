import json

import pytest

from backup.config import Config, Setting
from backup.worker import DebugWorker
from backup.util import GlobalInfo
from backup.logger import getLogger
from .helpers import skipForWindows


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
async def test_send_error_report(time, debug_worker: DebugWorker, config: Config, global_info: GlobalInfo, server):
    config.override(Setting.SEND_ERROR_REPORTS, True)
    config.override(Setting.DRIVE_HOST_NAME, "localhost")
    global_info.sync()
    global_info.success()
    global_info.sync()
    global_info.success()
    global_info.sync()
    global_info.failed(Exception())
    await debug_worker.doWork()
    report = json.loads(server.last_error_report)
    assert report['version'] == "0.100.0"
    assert report['client'] == config.clientIdentifier()
    assert report['google_dns'] == debug_worker.dns_info
    assert report['syncs'] == {
        'successes': 2,
        'count': 3,
        'failures': 1,
        'last_start': time.now().isoformat(),
        'last_failure': time.now().isoformat()
    }
    assert report['error'] == getLogger("test").formatException(Exception())


@pytest.mark.asyncio
async def test_dont_send_error_report(time, debug_worker: DebugWorker, config: Config, global_info: GlobalInfo, server):
    config.override(Setting.SEND_ERROR_REPORTS, False)
    config.override(Setting.DRIVE_HOST_NAME, "localhost")
    global_info.failed(Exception())
    await debug_worker.doWork()
    assert server.last_error_report is None


@pytest.mark.asyncio
async def test_only_send_duplicates(time, debug_worker: DebugWorker, config: Config, global_info: GlobalInfo, server):
    config.override(Setting.SEND_ERROR_REPORTS, True)
    config.override(Setting.DRIVE_HOST_NAME, "localhost")
    global_info.failed(Exception("boom1"))
    firstExceptionTime = time.now()
    await debug_worker.doWork()
    report = json.loads(server.last_error_report)
    assert report["error"] == getLogger("test").formatException(Exception("boom1"))
    assert report["now"] == firstExceptionTime.isoformat()

    # Same exception shouldn't cause us to send the error report again
    time.advance(days=1)
    global_info.failed(Exception("boom1"))
    await debug_worker.doWork()
    report = json.loads(server.last_error_report)
    assert report["error"] == getLogger("test").formatException(Exception("boom1"))
    assert report["now"] == firstExceptionTime.isoformat()

    # Btu a new one will send a new report
    global_info.failed(Exception("boom2"))
    await debug_worker.doWork()
    report = json.loads(server.last_error_report)
    assert report["error"] == getLogger("test").formatException(Exception("boom2"))
    assert report["now"] == time.now().isoformat()


@pytest.mark.asyncio
async def test_send_clear(time, debug_worker: DebugWorker, config: Config, global_info: GlobalInfo, server):
    config.override(Setting.SEND_ERROR_REPORTS, True)
    config.override(Setting.DRIVE_HOST_NAME, "localhost")

    # Simulate failure
    global_info.failed(Exception("boom"))
    await debug_worker.doWork()

    # And then success
    global_info.success()
    time.advance(days=1)
    await debug_worker.doWork()
    report = json.loads(server.last_error_report)
    assert report == {
        'client': config.clientIdentifier(),
        'now': time.now().isoformat(),
        'duration': '1 day, 0:00:00'
    }
