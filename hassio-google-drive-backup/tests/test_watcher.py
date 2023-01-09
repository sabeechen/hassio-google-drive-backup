from backup.watcher import Watcher
from backup.config import Config, Setting, CreateOptions
from backup.ha import HaSource
from os.path import join
from .faketime import FakeTime
from asyncio import sleep
import pytest
import os

TEST_FILE_NAME = "test.tar"


@pytest.mark.asyncio
async def test_watcher_trigger_on_backup(server, watcher: Watcher, config: Config, time: FakeTime, ha: HaSource):
    await watcher.start()
    assert not await watcher.check()
    watcher.noticed_change_signal.clear()
    await simulateBackup(config, TEST_FILE_NAME, ha, time)
    await watcher.noticed_change_signal.wait()
    time.advance(minutes=11)
    assert await watcher.check()


@pytest.mark.asyncio
async def test_disable_watching(server, watcher: Watcher, config: Config, time: FakeTime, ha: HaSource):
    config.override(Setting.WATCH_BACKUP_DIRECTORY, False)
    await watcher.start()
    assert not await watcher.check()
    await simulateBackup(config, TEST_FILE_NAME, ha, time)
    await sleep(1)
    time.advance(minutes=11)
    assert not await watcher.check()


@pytest.mark.asyncio
async def test_watcher_doesnt_trigger_on_no_backup(server, watcher: Watcher, config: Config, time: FakeTime, ha: HaSource):
    await watcher.start()
    assert not await watcher.check()
    file = join(config.get(Setting.BACKUP_DIRECTORY_PATH), TEST_FILE_NAME)
    watcher.noticed_change_signal.clear()
    with open(file, "w"):
        pass
    await watcher.noticed_change_signal.wait()
    time.advance(minutes=11)
    assert not await watcher.check()


@pytest.mark.asyncio
async def test_watcher_below_wait_threshold(server, watcher: Watcher, config: Config, time: FakeTime, ha: HaSource):
    await watcher.start()
    assert not await watcher.check()
    for x in range(10):
        watcher.noticed_change_signal.clear()
        await simulateBackup(config, f"{TEST_FILE_NAME}.{x}", ha, time)
        await watcher.noticed_change_signal.wait()
        time.advance(seconds=9)
        assert not await watcher.check()
    time.advance(minutes=11)
    assert await watcher.check()


@pytest.mark.asyncio
async def test_watcher_triggers_for_deletes(server, watcher: Watcher, config: Config, time: FakeTime, ha: HaSource):
    await simulateBackup(config, TEST_FILE_NAME, ha, time)

    await watcher.start()
    assert not await watcher.check()
    watcher.noticed_change_signal.clear()
    os.remove(join(config.get(Setting.BACKUP_DIRECTORY_PATH), TEST_FILE_NAME))
    await watcher.noticed_change_signal.wait()

    time.advance(seconds=30)
    assert await watcher.check()


@pytest.mark.asyncio
async def test_moves_out_trigger(server, watcher: Watcher, config: Config, time: FakeTime, ha: HaSource):
    await simulateBackup(config, TEST_FILE_NAME, ha, time)
    await watcher.start()
    watcher.noticed_change_signal.clear()
    os.mkdir(join(config.get(Setting.BACKUP_DIRECTORY_PATH), "subdir"))
    os.rename(join(config.get(Setting.BACKUP_DIRECTORY_PATH), TEST_FILE_NAME), join(config.get(Setting.BACKUP_DIRECTORY_PATH), "subdir", TEST_FILE_NAME))
    await watcher.noticed_change_signal.wait()
    time.advance(minutes=11)
    assert await watcher.check()

# Check if move ins are really necessary
# @pytest.mark.asyncio
# async def test_moves_in_trigger(server, watcher: Watcher, config: Config, time: FakeTime, ha: HaSource):
#     os.mkdir(join(config.get(Setting.BACKUP_DIRECTORY_PATH), "subdir"))
#     await simulateBackup(config, "subdir/" + TEST_FILE_NAME, ha, time)
#     await watcher.start()
#     watcher.noticed_change_signal.clear()
#     os.rename(join(config.get(Setting.BACKUP_DIRECTORY_PATH), "subdir", TEST_FILE_NAME), join(config.get(Setting.BACKUP_DIRECTORY_PATH), TEST_FILE_NAME))
#     await watcher.noticed_change_signal.wait()
#     time.advance(minutes=11)
#     assert await watcher.check()


@pytest.mark.asyncio
async def test_subdirs_dont_trigger(server, watcher: Watcher, config: Config, time: FakeTime, ha: HaSource):
    await simulateBackup(config, TEST_FILE_NAME, ha, time)
    await watcher.start()
    watcher.noticed_change_signal.clear()
    os.mkdir(join(config.get(Setting.BACKUP_DIRECTORY_PATH), "subdir"))
    with open(join(config.get(Setting.BACKUP_DIRECTORY_PATH), "subdir", "ignored.txt"), "w"):
        pass
    assert not await watcher.check()
    time.advance(minutes=11)
    assert not await watcher.check()


async def simulateBackup(config, file_name, ha, time):
    file = join(config.get(Setting.BACKUP_DIRECTORY_PATH), file_name)
    with open(file, "w"):
        pass
    await ha.create(CreateOptions(time.now(), file_name))

# Verify that subdirectories get ignored
