import pytest

from backup.drive import AuthCodeQuery
from backup.exceptions import LogicError, GoogleCredGenerateError, ProtocolError
from dev.request_interceptor import RequestInterceptor
from dev.simulated_google import URL_MATCH_TOKEN, SimulatedGoogle, URL_MATCH_DEVICE_CODE
from aiohttp.web_response import json_response
from backup.config import Config, Setting


@pytest.mark.asyncio
async def test_invalid_sequence(device_code: AuthCodeQuery, interceptor: RequestInterceptor) -> None:
    with pytest.raises(LogicError):
        await device_code.waitForPermission()


@pytest.mark.asyncio
async def test_success(device_code: AuthCodeQuery, interceptor: RequestInterceptor, google: SimulatedGoogle, server) -> None:
    await device_code.requestCredentials(google._custom_drive_client_id, google._custom_drive_client_secret)

    google._device_code_accepted = True
    assert await device_code.waitForPermission() is not None


@pytest.mark.asyncio
async def test_google_failure_on_request(device_code: AuthCodeQuery, interceptor: RequestInterceptor, google: SimulatedGoogle, server) -> None:
    interceptor.setError(URL_MATCH_DEVICE_CODE, 458)
    with pytest.raises(GoogleCredGenerateError) as error:
        await device_code.requestCredentials(google._custom_drive_client_id, google._custom_drive_client_secret)
    assert error.value.message() == "Google responded with error status HTTP 458.  Please verify your credentials are set up correctly."


@pytest.mark.asyncio
async def test_failure_on_http_unknown(device_code: AuthCodeQuery, interceptor: RequestInterceptor, google: SimulatedGoogle, server) -> None:
    await device_code.requestCredentials(google._custom_drive_client_id, google._custom_drive_client_secret)

    interceptor.setError(URL_MATCH_TOKEN, 500)

    with pytest.raises(GoogleCredGenerateError) as error:
        await device_code.waitForPermission()
    assert error.value.message() == "Failed unexpectedly while trying to reach Google.  See the add-on logs for details."


@pytest.mark.asyncio
async def test_success_after_wait(device_code: AuthCodeQuery, interceptor: RequestInterceptor, google: SimulatedGoogle, server) -> None:
    await device_code.requestCredentials(google._custom_drive_client_id, google._custom_drive_client_secret)

    match = interceptor.setError(URL_MATCH_TOKEN)
    match.addResponse(json_response(data={'error': "slow_down"}, status=403))

    google._device_code_accepted = True
    await device_code.waitForPermission()

    assert match.callCount() == 2


@pytest.mark.asyncio
async def test_success_after_428(device_code: AuthCodeQuery, interceptor: RequestInterceptor, google: SimulatedGoogle, server) -> None:
    await device_code.requestCredentials(google._custom_drive_client_id, google._custom_drive_client_secret)

    match = interceptor.setError(URL_MATCH_TOKEN)
    match.addResponse(json_response(data={}, status=428))
    match.addResponse(json_response(data={}, status=428))
    match.addResponse(json_response(data={}, status=428))
    match.addResponse(json_response(data={}, status=428))
    match.addResponse(json_response(data={}, status=428))

    google._device_code_accepted = True
    await device_code.waitForPermission()

    assert match.callCount() == 6


@pytest.mark.asyncio
async def test_permission_failure(device_code: AuthCodeQuery, interceptor: RequestInterceptor, google: SimulatedGoogle, server) -> None:
    await device_code.requestCredentials(google._custom_drive_client_id, google._custom_drive_client_secret)

    match = interceptor.setError(URL_MATCH_TOKEN)
    match.addResponse(json_response(data={}, status=403))

    google._device_code_accepted = False
    with pytest.raises(GoogleCredGenerateError) as error:
        await device_code.waitForPermission()
    assert error.value.message() == "Google refused the request to connect your account, either because you rejected it or they were set up incorrectly."


@pytest.mark.asyncio
async def test_json_parse_failure(device_code: AuthCodeQuery, interceptor: RequestInterceptor, google: SimulatedGoogle, server) -> None:
    await device_code.requestCredentials(google._custom_drive_client_id, google._custom_drive_client_secret)

    interceptor.setError(URL_MATCH_TOKEN, 200)

    with pytest.raises(ProtocolError):
        await device_code.waitForPermission()


@pytest.mark.asyncio
async def test_repeated_failure(device_code: AuthCodeQuery, interceptor: RequestInterceptor, google: SimulatedGoogle, server, config: Config) -> None:
    await device_code.requestCredentials(google._custom_drive_client_id, google._custom_drive_client_secret)

    config.override(Setting.DRIVE_TOKEN_URL, "http://go.nowhere")
    with pytest.raises(GoogleCredGenerateError) as error:
        await device_code.waitForPermission()
    error.value.message() == "Failed unexpectedly too many times while attempting to reach Google.  See the logs for details."
