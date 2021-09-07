import pytest
import os
import json
from injector import Injector
from datetime import timedelta
from backup.config import Config, Setting, VERSION, Version
from backup.util import DataCache, UpgradeFlags, KEY_CREATED, KEY_LAST_SEEN, CACHE_EXPIRATION_DAYS
from backup.time import Time


@pytest.mark.asyncio
async def test_read_and_write(config: Config, time: Time) -> None:
    cache = DataCache(config, time)
    assert len(cache.backups) == 0

    cache.backup("test")[KEY_CREATED] = time.now().isoformat()
    assert not cache._dirty
    cache.makeDirty()
    assert cache._dirty
    cache.saveIfDirty()
    assert not cache._dirty

    cache = DataCache(config, time)
    assert cache.backup("test")[KEY_CREATED] == time.now().isoformat()
    assert not cache._dirty


@pytest.mark.asyncio
async def test_backup_expiration(config: Config, time: Time) -> None:
    cache = DataCache(config, time)
    assert len(cache.backups) == 0

    cache.backup("new")[KEY_LAST_SEEN] = time.now().isoformat()
    cache.backup("old")[KEY_LAST_SEEN] = (
        time.now() - timedelta(days=CACHE_EXPIRATION_DAYS + 1)) .isoformat()
    cache.makeDirty()
    cache.saveIfDirty()

    assert len(cache.backups) == 1
    assert "new" in cache.backups
    assert "old" not in cache.backups


@pytest.mark.asyncio
async def test_version_upgrades(time: Time, injector: Injector, config: Config) -> None:
    # Simluate upgrading from an un-tracked version
    assert not os.path.exists(config.get(Setting.DATA_CACHE_FILE_PATH))
    cache = injector.get(DataCache)
    upgrade_time = time.now()
    assert cache.previousVersion == Version.default()
    assert cache.currentVersion == Version.parse(VERSION)

    assert os.path.exists(config.get(Setting.DATA_CACHE_FILE_PATH))
    with open(config.get(Setting.DATA_CACHE_FILE_PATH)) as f:
        data = json.load(f)
        assert data["upgrades"] == [{
            "prev_version": str(Version.default()),
            "new_version": VERSION,
            "date": upgrade_time.isoformat()
        }]

    # Reload the data cache, verify there is no upgrade.
    time.advance(days=1)
    cache = DataCache(config, time)
    assert cache.previousVersion == Version.parse(VERSION)
    assert cache.currentVersion == Version.parse(VERSION)
    assert os.path.exists(config.get(Setting.DATA_CACHE_FILE_PATH))

    with open(config.get(Setting.DATA_CACHE_FILE_PATH)) as f:
        data = json.load(f)
        assert data["upgrades"] == [{
            "prev_version": str(Version.default()),
            "new_version": VERSION,
            "date": upgrade_time.isoformat()
        }]

    # simulate upgrading to a new version, verify an upgrade gets identified.
    upgrade_version = Version.parse("200")

    class UpgradeCache(DataCache):
        def __init__(self):
            super().__init__(config, time)

        @property
        def currentVersion(self):
            return upgrade_version

    cache = UpgradeCache()
    assert cache.previousVersion == Version.parse(VERSION)
    assert cache.currentVersion == upgrade_version
    assert os.path.exists(config.get(Setting.DATA_CACHE_FILE_PATH))

    with open(config.get(Setting.DATA_CACHE_FILE_PATH)) as f:
        data = json.load(f)
        assert data["upgrades"] == [
            {
                "prev_version": str(Version.default()),
                "new_version": VERSION,
                "date": upgrade_time.isoformat()
            },
            {
                "prev_version": VERSION,
                "new_version": str(upgrade_version),
                "date": time.now().isoformat()
            }
        ]

    next_upgrade_time = time.now()
    time.advance(days=1)
    # Verify version upgrade time queries work as expected
    assert cache.getUpgradeTime(Version.parse(VERSION)) == upgrade_time
    assert cache.getUpgradeTime(Version.default()) == upgrade_time
    assert cache.getUpgradeTime(upgrade_version) == next_upgrade_time

    # degenerate case, should never happen but a sensible value needs to be returned
    assert cache.getUpgradeTime(Version.parse("201")) == time.now()


@pytest.mark.asyncio
async def test_flag(config: Config, time: Time):
    cache = DataCache(config, time)
    assert not cache.checkFlag(UpgradeFlags.TESTING_FLAG)
    assert not cache.dirty

    cache.addFlag(UpgradeFlags.TESTING_FLAG)
    assert cache.dirty
    assert cache.checkFlag(UpgradeFlags.TESTING_FLAG)
    cache.saveIfDirty()

    cache = DataCache(config, time)
    assert cache.checkFlag(UpgradeFlags.TESTING_FLAG)
