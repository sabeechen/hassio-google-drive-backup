import json

import pytest

from backup.config import Config, Setting
from backup.debugworker import DebugWorker
from backup.util import GlobalInfo
from backup.logger import getLogger, getLast
from dev.simulationserver import SimulationServer
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
    report = json.loads(getLast().msg)
    assert report['report']['google_dns'] == debug_worker.dns_info
    assert report['report']['syncs'] == {
        'successes': 2,
        'count': 3,
        'failures': 1,
        'last_start': time.now().isoformat(),
        'last_failure': time.now().isoformat()
    }
    assert report['report']['error'] == getLogger("test").formatException(Exception())


@pytest.mark.asyncio
async def test_dont_send_error_report(time, debug_worker: DebugWorker, config: Config, global_info: GlobalInfo, server: SimulationServer):
    config.override(Setting.SEND_ERROR_REPORTS, False)
    config.override(Setting.DRIVE_HOST_NAME, "localhost")
    global_info.failed(Exception())
    await debug_worker.doWork()
    with pytest.raises(AttributeError):
        json.loads(getLast().msg)


@pytest.mark.asyncio
async def test_only_send_duplicates(time, debug_worker: DebugWorker, config: Config, global_info: GlobalInfo, server):
    config.override(Setting.SEND_ERROR_REPORTS, True)
    config.override(Setting.DRIVE_HOST_NAME, "localhost")
    global_info.failed(Exception("boom1"))
    firstExceptionTime = time.now()
    await debug_worker.doWork()
    report = json.loads(getLast().msg)
    assert report['report']["error"] == getLogger("test").formatException(Exception("boom1"))
    assert report['report']["now"] == firstExceptionTime.isoformat()

    # Same exception shouldn't cause us to send the error report again
    time.advance(days=1)
    global_info.failed(Exception("boom1"))
    await debug_worker.doWork()
    report = json.loads(getLast().msg)
    assert report['report']["error"] == getLogger("test").formatException(Exception("boom1"))
    assert report['report']["now"] == firstExceptionTime.isoformat()

    # Btu a new one will send a new report
    global_info.failed(Exception("boom2"))
    await debug_worker.doWork()
    report = json.loads(getLast().msg)
    assert report['report']["error"] == getLogger("test").formatException(Exception("boom2"))
    assert report['report']["now"] == time.now().isoformat()


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
    report = json.loads(getLast().msg)
    assert report['report'] == {
        'duration': '1 day, 0:00:00'
    }
