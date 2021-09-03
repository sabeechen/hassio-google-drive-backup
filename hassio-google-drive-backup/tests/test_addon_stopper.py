import json
import pytest
import os

from stat import S_IREAD
from backup.config import Config, Setting
from backup.ha import AddonStopper
from backup.exceptions import SupervisorFileSystemError
from .faketime import FakeTime
from dev.simulated_supervisor import SimulatedSupervisor, URL_MATCH_START_ADDON, URL_MATCH_STOP_ADDON, URL_MATCH_ADDON_INFO
from dev.request_interceptor import RequestInterceptor
from .helpers import skipForRoot


def getSaved(config: Config):
    with open(config.get(Setting.STOP_ADDON_STATE_PATH)) as f:
        data = json.load(f)
        return set(data["start"]), set(data["watchdog"])


def save(config: Config, to_start, to_watchdog_enable):
    with open(config.get(Setting.STOP_ADDON_STATE_PATH), "w") as f:
        json.dump({"start": list(to_start), "watchdog": list(to_watchdog_enable)}, f)


@pytest.mark.asyncio
async def test_no_stop_config(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config) -> None:
    slug = "test_slug_1"
    supervisor.installAddon(slug, "Test decription")
    addon_stopper.allowRun()
    addon_stopper.isBackingUp(False)
    assert supervisor.addon(slug)["state"] == "started"
    await addon_stopper.stopAddons("ignore")
    assert supervisor.addon(slug)["state"] == "started"
    await addon_stopper.check()
    await addon_stopper.startAddons()
    assert supervisor.addon(slug)["state"] == "started"


@pytest.mark.asyncio
async def test_load_addons_on_boot(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config) -> None:
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    slug2 = "test_slug_2"
    supervisor.installAddon(slug2, "Test decription")
    slug3 = "test_slug_3"
    supervisor.installAddon(slug3, "Test decription")

    config.override(Setting.STOP_ADDONS, slug1)

    save(config, {slug3}, {slug2})

    await addon_stopper.start(False)
    assert addon_stopper.must_start == {slug3}
    assert addon_stopper.must_enable_watchdog == {slug2}

    addon_stopper.allowRun()
    assert addon_stopper.must_start == {slug1, slug3}
    assert addon_stopper.must_enable_watchdog == {slug2}


@pytest.mark.asyncio
async def test_do_nothing_while_backing_up(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config, interceptor: RequestInterceptor) -> None:
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    slug2 = "test_slug_2"
    supervisor.installAddon(slug2, "Test decription")
    config.override(Setting.STOP_ADDONS, ",".join([slug1, slug2]))

    await addon_stopper.start(False)
    addon_stopper.allowRun()
    addon_stopper.isBackingUp(True)
    assert addon_stopper.must_start == {slug1, slug2}

    await addon_stopper.check()

    assert not interceptor.urlWasCalled(URL_MATCH_START_ADDON)
    assert not interceptor.urlWasCalled(URL_MATCH_STOP_ADDON)


@pytest.mark.asyncio
async def test_start_and_stop(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config) -> None:
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    config.override(Setting.STOP_ADDONS, ",".join([slug1]))
    addon_stopper.allowRun()
    addon_stopper.must_start = set()
    assert supervisor.addon(slug1)["state"] == "started"

    await addon_stopper.stopAddons("ignore")

    assert supervisor.addon(slug1)["state"] == "stopped"
    await addon_stopper.check()
    assert supervisor.addon(slug1)["state"] == "stopped"
    await addon_stopper.startAddons()
    assert supervisor.addon(slug1)["state"] == "started"
    assert getSaved(config) == (set(), set())


@pytest.mark.asyncio
async def test_stop_failure(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config, interceptor: RequestInterceptor) -> None:
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    config.override(Setting.STOP_ADDONS, slug1)
    addon_stopper.allowRun()
    addon_stopper.must_start = set()
    assert supervisor.addon(slug1)["state"] == "started"
    interceptor.setError(URL_MATCH_STOP_ADDON, 400)

    await addon_stopper.stopAddons("ignore")
    assert interceptor.urlWasCalled(URL_MATCH_STOP_ADDON)
    assert getSaved(config) == (set(), set())
    assert supervisor.addon(slug1)["state"] == "started"
    await addon_stopper.check()
    await addon_stopper.startAddons()
    assert supervisor.addon(slug1)["state"] == "started"
    assert getSaved(config) == (set(), set())


@pytest.mark.asyncio
async def test_start_failure(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config, interceptor: RequestInterceptor, time: FakeTime) -> None:
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    config.override(Setting.STOP_ADDONS, ",".join([slug1]))
    addon_stopper.allowRun()
    addon_stopper.must_start = set()
    assert supervisor.addon(slug1)["state"] == "started"

    await addon_stopper.stopAddons("ignore")

    assert supervisor.addon(slug1)["state"] == "stopped"
    await addon_stopper.check()
    assert getSaved(config) == ({slug1}, set())
    assert supervisor.addon(slug1)["state"] == "stopped"
    interceptor.setError(URL_MATCH_START_ADDON, 400)
    await addon_stopper.startAddons()
    assert getSaved(config) == (set(), set())
    assert interceptor.urlWasCalled(URL_MATCH_START_ADDON)
    assert supervisor.addon(slug1)["state"] == "stopped"


@pytest.mark.asyncio
async def test_delayed_start(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config, interceptor: RequestInterceptor, time: FakeTime) -> None:
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    config.override(Setting.STOP_ADDONS, ",".join([slug1]))
    addon_stopper.allowRun()
    addon_stopper.must_start = set()
    assert supervisor.addon(slug1)["state"] == "started"
    await addon_stopper.stopAddons("ignore")
    assert supervisor.addon(slug1)["state"] == "stopped"
    assert getSaved(config) == ({slug1}, set())

    # start the addon again, which simluates the supervisor's tendency to report an addon as started right after stopping it.
    supervisor.addon(slug1)["state"] = "started"
    await addon_stopper.check()
    await addon_stopper.startAddons()
    assert getSaved(config) == ({slug1}, set())

    time.advance(seconds=30)
    await addon_stopper.check()
    assert getSaved(config) == ({slug1}, set())

    time.advance(seconds=30)
    await addon_stopper.check()
    assert getSaved(config) == ({slug1}, set())

    time.advance(seconds=30)
    supervisor.addon(slug1)["state"] = "stopped"
    await addon_stopper.check()
    assert supervisor.addon(slug1)["state"] == "started"
    assert getSaved(config) == (set(), set())


@pytest.mark.asyncio
async def test_delayed_start_give_up(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config, interceptor: RequestInterceptor, time: FakeTime) -> None:
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    config.override(Setting.STOP_ADDONS, ",".join([slug1]))
    addon_stopper.allowRun()
    addon_stopper.must_start = set()
    assert supervisor.addon(slug1)["state"] == "started"
    await addon_stopper.stopAddons("ignore")
    assert supervisor.addon(slug1)["state"] == "stopped"
    assert getSaved(config) == ({slug1}, set())

    # start the addon again, which simluates the supervisor's tendency to report an addon as started right after stopping it.
    supervisor.addon(slug1)["state"] = "started"
    await addon_stopper.check()
    await addon_stopper.startAddons()
    assert getSaved(config) == ({slug1}, set())

    time.advance(seconds=30)
    await addon_stopper.check()
    assert getSaved(config) == ({slug1}, set())

    time.advance(seconds=30)
    await addon_stopper.check()
    assert getSaved(config) == ({slug1}, set())

    # Should clear saved state after this, since it stops checking after 2 minutes.
    time.advance(seconds=100)
    await addon_stopper.check()
    assert getSaved(config) == (set(), set())


@pytest.mark.asyncio
async def test_disable_watchdog(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config) -> None:
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    config.override(Setting.STOP_ADDONS, ",".join([slug1]))
    supervisor.addon(slug1)["watchdog"] = True

    addon_stopper.allowRun()
    addon_stopper.must_start = set()
    assert supervisor.addon(slug1)["state"] == "started"

    await addon_stopper.stopAddons("ignore")

    assert supervisor.addon(slug1)["state"] == "stopped"
    assert supervisor.addon(slug1)["watchdog"] is False
    await addon_stopper.check()
    assert supervisor.addon(slug1)["state"] == "stopped"
    assert supervisor.addon(slug1)["watchdog"] is False
    await addon_stopper.startAddons()
    assert supervisor.addon(slug1)["state"] == "started"
    assert supervisor.addon(slug1)["watchdog"] is True
    assert getSaved(config) == (set(), set())


@pytest.mark.asyncio
async def test_enable_watchdog_on_reboot(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config, time: FakeTime) -> None:
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    config.override(Setting.STOP_ADDONS, ",".join([slug1]))
    supervisor.addon(slug1)["watchdog"] = False
    save(config, set(), {slug1})

    await addon_stopper.start(False)
    addon_stopper.allowRun()
    assert addon_stopper.must_enable_watchdog == {slug1}

    time.advance(minutes=5)
    await addon_stopper.check()
    assert supervisor.addon(slug1)["watchdog"] is True
    assert getSaved(config) == (set(), set())


@pytest.mark.asyncio
async def test_enable_watchdog_waits_for_start(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config) -> None:
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    config.override(Setting.STOP_ADDONS, ",".join([slug1]))
    supervisor.addon(slug1)["watchdog"] = False
    save(config, {slug1}, {slug1})

    await addon_stopper.start(False)
    addon_stopper.allowRun()
    assert addon_stopper.must_enable_watchdog == {slug1}

    await addon_stopper.check()
    assert getSaved(config) == ({slug1}, {slug1})

    supervisor.addon(slug1)["state"] = "stopped"
    await addon_stopper.check()
    assert supervisor.addon(slug1)["state"] == "started"
    assert supervisor.addon(slug1)["watchdog"] is True
    assert getSaved(config) == (set(), set())


@pytest.mark.asyncio
async def test_get_info_failure_on_stop(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config, interceptor: RequestInterceptor) -> None:
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    config.override(Setting.STOP_ADDONS, slug1)
    addon_stopper.allowRun()
    addon_stopper.must_start = set()
    assert supervisor.addon(slug1)["state"] == "started"
    interceptor.setError(URL_MATCH_ADDON_INFO, 400)

    await addon_stopper.stopAddons("ignore")
    assert interceptor.urlWasCalled(URL_MATCH_ADDON_INFO)
    assert getSaved(config) == (set(), set())
    assert supervisor.addon(slug1)["state"] == "started"
    await addon_stopper.check()
    await addon_stopper.startAddons()
    assert supervisor.addon(slug1)["state"] == "started"
    assert getSaved(config) == (set(), set())


@pytest.mark.asyncio
async def test_get_info_failure_on_start(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config, interceptor: RequestInterceptor) -> None:
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    config.override(Setting.STOP_ADDONS, ",".join([slug1]))
    addon_stopper.allowRun()
    addon_stopper.must_start = set()
    assert supervisor.addon(slug1)["state"] == "started"

    await addon_stopper.stopAddons("ignore")

    assert supervisor.addon(slug1)["state"] == "stopped"
    await addon_stopper.check()
    assert getSaved(config) == ({slug1}, set())
    assert supervisor.addon(slug1)["state"] == "stopped"
    interceptor.setError(URL_MATCH_ADDON_INFO, 400)
    await addon_stopper.startAddons()
    assert getSaved(config) == (set(), set())
    assert interceptor.urlWasCalled(URL_MATCH_ADDON_INFO)
    assert supervisor.addon(slug1)["state"] == "stopped"


@pytest.mark.asyncio
async def test_read_only_fs(supervisor: SimulatedSupervisor, addon_stopper: AddonStopper, config: Config, interceptor: RequestInterceptor) -> None:
    # This test can't be run as the root user, since no file is read-only to root.
    skipForRoot()

    # Stop an addon
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")
    config.override(Setting.STOP_ADDONS, ",".join([slug1]))
    addon_stopper.allowRun()
    addon_stopper.must_start = set()
    assert supervisor.addon(slug1)["state"] == "started"
    await addon_stopper.stopAddons("ignore")
    assert supervisor.addon(slug1)["state"] == "stopped"
    await addon_stopper.check()
    assert getSaved(config) == ({slug1}, set())

    # make the state file unmodifiable
    os.chmod(config.get(Setting.STOP_ADDON_STATE_PATH), S_IREAD)

    # verify we raise a known error when trying to save.
    with pytest.raises(SupervisorFileSystemError):
        await addon_stopper.startAddons()
