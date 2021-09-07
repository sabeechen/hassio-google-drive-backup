import pytest

from dev.simulationserver import SimulationServer, RequestInterceptor
from backup.time import Time
from backup.config import Config, Setting
from backup.drive import DriveRequests
from backup.exceptions import CredRefreshMyError, GoogleCredentialsExpired, CredRefreshGoogleError
from backup.tracing_session import TracingSession
from yarl import URL


@pytest.mark.asyncio
async def test_correct_host(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, server_url, interceptor: RequestInterceptor):
    # Verify the correct endpoitns get called for a successful request
    session.record = True
    await drive_requests.exchanger.refresh(drive_requests.creds)
    assert interceptor.urlWasCalled("/drive/refresh")
    session._records[0]['url'] == server_url.with_path("/drive/refresh")


@pytest.mark.asyncio
async def test_some_bad_hosts(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, server_url, interceptor: RequestInterceptor):
    session.record = True
    config.override(Setting.EXCHANGER_TIMEOUT_SECONDS, 1)
    config.override(Setting.TOKEN_SERVER_HOSTS, "https://this.goes.nowhere.info," + str(server_url))

    await drive_requests.exchanger.refresh(drive_requests.creds)
    assert interceptor.urlWasCalled("/drive/refresh")

    # Verify both hosts were checked
    session._records[0]['url'] == URL("https://this.goes.nowhere.info").with_path("/drive/refresh")
    session._records[1]['url'] == server_url.with_path("/drive/refresh")


@pytest.mark.asyncio
async def test_all_bad_hosts(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, interceptor: RequestInterceptor):
    session.record = True
    config.override(Setting.EXCHANGER_TIMEOUT_SECONDS, 1)
    config.override(Setting.TOKEN_SERVER_HOSTS, "https://this.goes.nowhere.info,http://also.a.bad.host")

    with pytest.raises(CredRefreshMyError) as e:
        await drive_requests.exchanger.refresh(drive_requests.creds)

    # Error should be about the last host name
    assert e.value.reason == "Couldn't communicate with also.a.bad.host"

    # Verify both hosts were checked
    session._records[0]['url'] == URL("https://this.goes.nowhere.info").with_path("/drive/refresh")
    session._records[1]['url'] == URL("http://also.a.bad.host").with_path("/drive/refresh")


@pytest.mark.asyncio
async def test_exchange_timeout(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, interceptor: RequestInterceptor, server_url: URL):
    session.record = True
    interceptor.setSleep("/drive/refresh", sleep=10)

    config.override(Setting.EXCHANGER_TIMEOUT_SECONDS, 0.1)

    with pytest.raises(CredRefreshMyError) as e:
        await drive_requests.exchanger.refresh(drive_requests.creds)

    # Error should be about the last host name
    assert e.value.reason == "Timed out communicating with localhost"

    # Verify both hosts were checked
    session._records[0]['url'] == server_url.with_path("/drive/refresh")


@pytest.mark.asyncio
async def test_exchange_invalid_creds(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, interceptor: RequestInterceptor, server_url: URL):
    session.record = True
    drive_requests.creds._refresh_token = "fail"
    with pytest.raises(GoogleCredentialsExpired):
        await drive_requests.exchanger.refresh(drive_requests.creds)

    # Verify both hosts were checked
    session._records[0]['url'] == server_url.with_path("/drive/refresh")


@pytest.mark.asyncio
async def test_fail_503_with_error(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, interceptor: RequestInterceptor, server_url: URL):
    session.record = True
    interceptor.setError("^/drive/refresh$", 503, response={'error': 'test_value'})
    with pytest.raises(CredRefreshGoogleError) as e:
        await drive_requests.exchanger.refresh(drive_requests.creds)
    assert e.value.message() == "Couldn't refresh your credentials with Google because: 'test_value'"

    # Verify both hosts were checked
    session._records[0]['url'] == server_url.with_path("/drive/refresh")


@pytest.mark.asyncio
async def test_fail_503_invalid_grant(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, interceptor: RequestInterceptor, server_url: URL):
    session.record = True
    interceptor.setError("^/drive/refresh$", 503, response={'error': 'invalid_grant'})
    with pytest.raises(GoogleCredentialsExpired):
        await drive_requests.exchanger.refresh(drive_requests.creds)

    # Verify both hosts were checked
    session._records[0]['url'] == server_url.with_path("/drive/refresh")


@pytest.mark.asyncio
async def test_fail_503_with_invalid_json(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, interceptor: RequestInterceptor, server_url: URL):
    session.record = True
    interceptor.setError("^/drive/refresh$", 503, response={'ignored': 'nothing'})
    with pytest.raises(CredRefreshMyError) as e:
        await drive_requests.exchanger.refresh(drive_requests.creds)
    assert e.value.message() == "Couldn't refresh Google Drive credentials because: HTTP 503 from localhost"

    # Verify both hosts were checked
    session._records[0]['url'] == server_url.with_path("/drive/refresh")


@pytest.mark.asyncio
async def test_fail_503_with_no_data(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, interceptor: RequestInterceptor, server_url: URL):
    session.record = True
    interceptor.setError("^/drive/refresh$", 503)
    with pytest.raises(CredRefreshMyError) as e:
        await drive_requests.exchanger.refresh(drive_requests.creds)
    assert e.value.message() == "Couldn't refresh Google Drive credentials because: HTTP 503 from localhost"

    # Verify both hosts were checked
    session._records[0]['url'] == server_url.with_path("/drive/refresh")


@pytest.mark.asyncio
async def test_fail_401(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, interceptor: RequestInterceptor, server_url: URL):
    session.record = True
    interceptor.setError("^/drive/refresh$", 401)
    with pytest.raises(GoogleCredentialsExpired):
        await drive_requests.exchanger.refresh(drive_requests.creds)

    # Verify both hosts were checked
    session._records[0]['url'] == server_url.with_path("/drive/refresh")


@pytest.mark.asyncio
async def test_fail_401_no_fall_through(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, interceptor: RequestInterceptor, server_url: URL):
    session.record = True
    config.override(Setting.TOKEN_SERVER_HOSTS, str(server_url) + "," + str(server_url))
    interceptor.setError("^/drive/refresh$", 401)
    with pytest.raises(GoogleCredentialsExpired):
        await drive_requests.exchanger.refresh(drive_requests.creds)

    # Verify both hosts were checked
    session._records[0]['url'] == server_url.with_path("/drive/refresh")
    assert len(session._records) == 1


@pytest.mark.asyncio
async def test_invalid_grant_no_fall_through(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, interceptor: RequestInterceptor, server_url: URL):
    session.record = True
    config.override(Setting.TOKEN_SERVER_HOSTS, str(server_url) + "," + str(server_url))
    interceptor.setError("^/drive/refresh$", 503, response={'error': 'invalid_grant'})
    with pytest.raises(GoogleCredentialsExpired):
        await drive_requests.exchanger.refresh(drive_requests.creds)

    # Verify both hosts were checked
    session._records[0]['url'] == server_url.with_path("/drive/refresh")
    assert len(session._records) == 1


@pytest.mark.asyncio
async def test_timeout_fall_through(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, interceptor: RequestInterceptor, server_url: URL):
    session.record = True
    config.override(Setting.EXCHANGER_TIMEOUT_SECONDS, 0.1)
    config.override(Setting.TOKEN_SERVER_HOSTS, str(server_url) + "," + str(server_url))
    interceptor.setSleep("^/drive/refresh$", sleep=10, wait_for=1)
    await drive_requests.exchanger.refresh(drive_requests.creds)

    # Verify both hosts were checked
    session._records[0]['url'] == server_url.with_path("/drive/refresh")
    session._records[1]['url'] == server_url.with_path("/drive/refresh")


@pytest.mark.asyncio
async def test_anything_else_through(time: Time, session: TracingSession, config: Config, server: SimulationServer, drive_requests: DriveRequests, interceptor: RequestInterceptor, server_url: URL):
    session.record = True
    config.override(Setting.TOKEN_SERVER_HOSTS, str(server_url) + "," + str(server_url))
    interceptor.setError("^/drive/refresh$", status=500, fail_for=1)
    await drive_requests.exchanger.refresh(drive_requests.creds)

    # Verify both hosts were checked
    session._records[0]['url'] == server_url.with_path("/drive/refresh")
    session._records[1]['url'] == server_url.with_path("/drive/refresh")
