import asyncio
from datetime import timedelta
import os

import pytest
from aiohttp.client_exceptions import ClientResponseError

from backup.config import Config, Setting, CreateOptions, Version
from backup.const import SOURCE_HA
from backup.exceptions import (HomeAssistantDeleteError, BackupInProgress,
                               BackupPasswordKeyInvalid, UploadFailed, SupervisorConnectionError, SupervisorPermissionError, SupervisorTimeoutError)
from backup.util import GlobalInfo, DataCache, KEY_CREATED, KEY_LAST_SEEN, KEY_NAME
from backup.ha import HaSource, PendingBackup, EVENT_BACKUP_END, EVENT_BACKUP_START, HABackup, Password, AddonStopper
from backup.model import DummyBackup
from dev.simulationserver import SimulationServer
from .faketime import FakeTime
from .helpers import all_addons, all_folders, createBackupTar, getTestStream
from dev.simulated_supervisor import SimulatedSupervisor, URL_MATCH_SELF_OPTIONS, URL_MATCH_START_ADDON, URL_MATCH_STOP_ADDON, URL_MATCH_BACKUP_FULL, URL_MATCH_BACKUP_DELETE, URL_MATCH_MISC_INFO, URL_MATCH_BACKUP_DOWNLOAD, URL_MATCH_BACKUPS, URL_MATCH_SNAPSHOT
from dev.request_interceptor import RequestInterceptor
from backup.model import Model
from backup.time import Time
from yarl import URL


@pytest.mark.asyncio
async def test_sync_empty(ha) -> None:
    assert len(await ha.get()) == 0


@pytest.mark.asyncio
async def test_CRUD(ha: HaSource, time, interceptor: RequestInterceptor, data_cache: DataCache) -> None:
    backup: HABackup = await ha.create(CreateOptions(time.now(), "Test Name"))

    assert backup.name() == "Test Name"
    assert type(backup) is HABackup
    assert not backup.retained()
    assert backup.backupType() == "full"
    assert not backup.protected()
    assert backup.name() == "Test Name"
    assert backup.source() == SOURCE_HA
    assert not backup.ignore()
    assert backup.madeByTheAddon()
    assert "pending" not in data_cache.backups

    # read the item directly, its metadata should match
    from_ha = await ha.harequests.backup(backup.slug())
    assert from_ha.size() == backup.size()
    assert from_ha.slug() == backup.slug()
    assert from_ha.source() == SOURCE_HA

    backups = await ha.get()
    assert len(backups) == 1
    assert backup.slug() in backups

    full = DummyBackup(from_ha.name(), from_ha.date(),
                       from_ha.size(), from_ha.slug(), "dummy")
    full.addSource(backup)

    # download the item, its bytes should match up
    download = await ha.read(full)
    await download.setup()
    direct_download = await ha.harequests.download(backup.slug())
    await direct_download.setup()
    while True:
        from_file = await direct_download.read(1024 * 1024)
        from_download = await download.read(1024 * 1024)
        if len(from_file.getbuffer()) == 0:
            assert len(from_download.getbuffer()) == 0
            break
        assert from_file.getbuffer() == from_download.getbuffer()

    # update retention
    assert not backup.retained()
    await ha.retain(full, True)
    assert (await ha.get())[full.slug()].retained()
    await ha.retain(full, False)
    assert not (await ha.get())[full.slug()].retained()

    # Delete the item, make sure its gone
    await ha.delete(full)
    assert full.getSource(ha.name()) is None
    backups = await ha.get()
    assert len(backups) == 0


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_pending_backup_nowait(ha: HaSource, time: Time, supervisor: SimulatedSupervisor, interceptor: RequestInterceptor, config: Config, data_cache: DataCache):
    interceptor.setSleep(URL_MATCH_BACKUP_FULL, sleep=5)
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 0.1)
    backup_immediate: PendingBackup = await ha.create(CreateOptions(time.now(), "Test Name"))
    assert isinstance(backup_immediate, PendingBackup)
    backup_pending: HABackup = (await ha.get())['pending']

    assert isinstance(backup_immediate, PendingBackup)
    assert isinstance(backup_pending, PendingBackup)
    assert backup_immediate is backup_pending
    assert backup_immediate.name() == "Test Name"
    assert backup_immediate.slug() == "pending"
    assert not backup_immediate.uploadable()
    assert backup_immediate.backupType() == "Full"
    assert backup_immediate.source() == SOURCE_HA
    assert backup_immediate.date() == time.now()
    assert not backup_immediate.protected()
    assert not backup_immediate.ignore()
    assert backup_immediate.madeByTheAddon()
    assert data_cache.backup("pending") == {
        KEY_CREATED: time.now().isoformat(),
        KEY_LAST_SEEN: time.now().isoformat(),
        KEY_NAME: "Test Name"
    }

    # Might be a little flaky but...whatever
    await asyncio.wait({ha._pending_backup_task})

    backups = await ha.get()
    assert 'pending' not in backups
    assert len(backups) == 1
    backup = next(iter(backups.values()))
    assert isinstance(backup, HABackup)
    assert not backup.ignore()
    assert backup.madeByTheAddon()
    assert data_cache.backup(backup.slug())[KEY_LAST_SEEN] == time.now().isoformat()
    assert "pending" not in data_cache.backups

    return
    # ignroe events for now
    assert supervisor.getEvents() == [
        (EVENT_BACKUP_START, {
            'backup_name': backup_immediate.name(),
            'backup_time': str(backup_immediate.date())})]
    ha.backup_thread.join()
    assert supervisor.getEvents() == [
        (EVENT_BACKUP_START, {
            'backup_name': backup_immediate.name(),
            'backup_time': str(backup_immediate.date())}),
        (EVENT_BACKUP_END, {
            'completed': True,
            'backup_name': backup_immediate.name(),
            'backup_time': str(backup_immediate.date())})]


@pytest.mark.asyncio
async def test_pending_backup_already_in_progress(ha, time, config: Config, supervisor: SimulatedSupervisor):
    await ha.create(CreateOptions(time.now(), "Test Name"))
    assert len(await ha.get()) == 1

    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 100)
    await supervisor.toggleBlockBackup()
    with pytest.raises(BackupInProgress):
        await ha.create(CreateOptions(time.now(), "Test Name"))
    backups = list((await ha.get()).values())
    assert len(backups) == 2
    backup = backups[1]

    assert isinstance(backup, PendingBackup)
    assert backup.name() == "Pending Backup"
    assert backup.slug() == "pending"
    assert not backup.uploadable()
    assert backup.backupType() == "unknown"
    assert backup.source() == SOURCE_HA
    assert backup.date() == time.now()
    assert not backup.protected()

    with pytest.raises(BackupInProgress):
        await ha.create(CreateOptions(time.now(), "Test Name"))


@pytest.mark.asyncio
async def test_partial_backup(ha, time, server, config: Config):
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 100)
    for folder in all_folders:
        config.override(Setting.EXCLUDE_FOLDERS, folder)
        backup: HABackup = await ha.create(CreateOptions(time.now(), "Test Name"))

        assert backup.backupType() == "partial"
        for search in all_folders:
            if search == folder:
                assert search not in backup.details()['folders']
            else:
                assert search in backup.details()['folders']

    for addon in all_addons:
        config.override(Setting.EXCLUDE_ADDONS, addon['slug'])
        backup: HABackup = await ha.create(CreateOptions(time.now(), "Test Name"))
        assert backup.backupType() == "partial"
        list_of_addons = []
        for included in backup.details()['addons']:
            list_of_addons.append(included['slug'])
        for search in list_of_addons:
            if search == addon:
                assert search not in list_of_addons
            else:
                assert search in list_of_addons

    # excluding addon/folders that don't exist should actually make a full backup
    config.override(Setting.EXCLUDE_ADDONS, "none,of.these,are.addons")
    config.override(Setting.EXCLUDE_FOLDERS, "not,folders,either")
    backup: HABackup = await ha.create(CreateOptions(time.now(), "Test Name"))
    assert backup.backupType() == "full"


@pytest.mark.asyncio
async def test_backup_password(ha: HaSource, config: Config, time):
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 100)
    backup: HABackup = await ha.create(CreateOptions(time.now(), "Test Name"))
    assert not backup.protected()

    config.override(Setting.BACKUP_PASSWORD, 'test')
    backup = await ha.create(CreateOptions(time.now(), "Test Name"))
    assert backup.protected()

    config.override(Setting.BACKUP_PASSWORD, 'test')
    assert Password(ha.config).resolve() == 'test'

    config.override(Setting.BACKUP_PASSWORD, '!secret for_unit_tests')
    assert Password(ha.config).resolve() == 'password value'

    config.override(Setting.BACKUP_PASSWORD, '!secret bad_key')
    with pytest.raises(BackupPasswordKeyInvalid):
        Password(config).resolve()

    config.override(Setting.SECRETS_FILE_PATH, "/bad/file/path")
    config.override(Setting.BACKUP_PASSWORD, '!secret for_unit_tests')
    with pytest.raises(BackupPasswordKeyInvalid):
        Password(ha.config).resolve()


@pytest.mark.asyncio
async def test_backup_name(time: FakeTime, ha):
    time.setNow(time.local(1985, 12, 6, 15, 8, 9, 10))
    await assertName(ha, time.now(), "{type}", "Full")
    await assertName(ha, time.now(), "{year}", "1985")
    await assertName(ha, time.now(), "{year_short}", "85")
    await assertName(ha, time.now(), "{weekday}", "Friday")
    await assertName(ha, time.now(), "{weekday_short}", "Fri")
    await assertName(ha, time.now(), "{month}", "12")
    await assertName(ha, time.now(), "{month_long}", "December")
    await assertName(ha, time.now(), "{month_short}", "Dec")
    await assertName(ha, time.now(), "{ms}", "000010")
    await assertName(ha, time.now(), "{day}", "06")
    await assertName(ha, time.now(), "{hr24}", "15")
    await assertName(ha, time.now(), "{hr12}", "03")
    await assertName(ha, time.now(), "{min}", "08")
    await assertName(ha, time.now(), "{sec}", "09")
    await assertName(ha, time.now(), "{ampm}", "PM")
    await assertName(ha, time.now(), "{version_ha}", "ha version")
    await assertName(ha, time.now(), "{version_hassos}", "hassos version")
    await assertName(ha, time.now(), "{version_super}", "super version")
    await assertName(ha, time.now(), "{date}", "12/06/85")
    await assertName(ha, time.now(), "{time}", "15:08:09")
    await assertName(ha, time.now(), "{datetime}", "Fri Dec  6 15:08:09 1985")
    await assertName(ha, time.now(), "{isotime}", "1985-12-06T15:08:09.000010-05:00")


async def assertName(ha: HaSource, time, template: str, expected: str):
    backup: HABackup = await ha.create(CreateOptions(time, template))
    assert backup.name() == expected


@pytest.mark.asyncio
async def test_default_name(time: FakeTime, ha, server):
    backup = await ha.create(CreateOptions(time.now(), ""))
    assert backup.name() == "Full Backup 1985-12-06 00:00:00"


@pytest.mark.asyncio
async def test_pending_backup_timeout(time: FakeTime, ha: HaSource, config: Config, interceptor: RequestInterceptor):
    interceptor.setSleep(URL_MATCH_BACKUP_FULL, sleep=5)
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 1)
    config.override(Setting.FAILED_BACKUP_TIMEOUT_SECONDS, 1)
    config.override(Setting.PENDING_BACKUP_TIMEOUT_SECONDS, 1)

    backup_immediate: PendingBackup = await ha.create(CreateOptions(time.now(), "Test Name"))
    assert isinstance(backup_immediate, PendingBackup)
    assert backup_immediate.name() == "Test Name"
    assert not ha.check()
    assert ha.pending_backup is backup_immediate

    await asyncio.wait({ha._pending_backup_task})
    assert ha.pending_backup is backup_immediate
    assert ha.check()
    assert not ha.check()

    time.advance(minutes=1)
    assert ha.check()
    assert len(await ha.get()) == 0
    assert not ha.check()
    assert ha.pending_backup is None
    assert backup_immediate.isStale()


@pytest.mark.asyncio
async def test_pending_backup_timeout_external(time, config, ha: HaSource, supervisor: SimulatedSupervisor):
    # now configure a snapshto to start outside of the addon
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 100)
    await supervisor.toggleBlockBackup()
    with pytest.raises(BackupInProgress):
        await ha.create(CreateOptions(time.now(), "Ignored"))
    backup_immediate = (await ha.get())['pending']
    await supervisor.toggleBlockBackup()
    assert isinstance(backup_immediate, PendingBackup)
    assert backup_immediate.name() == "Pending Backup"
    assert ha.check()
    assert not ha.check()
    assert ha.pending_backup is backup_immediate

    # should clean up after a day, since we're still waiting on the backup thread.
    time.advanceDay()
    assert ha.check()
    assert len(await ha.get()) == 0


@pytest.mark.asyncio
async def test_pending_backup_replaces_original(time, ha: HaSource, config: Config, supervisor: SimulatedSupervisor):
    # now configure a snapshto to start outside of the addon
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 100)
    await supervisor.toggleBlockBackup()
    with pytest.raises(BackupInProgress):
        await ha.create(CreateOptions(time.now(), "Ignored"))
    backup_immediate = (await ha.get())['pending']
    await supervisor.toggleBlockBackup()
    assert isinstance(backup_immediate, PendingBackup)
    assert backup_immediate.name() == "Pending Backup"
    assert ha.check()
    assert ha.pending_backup is backup_immediate
    assert await ha.get() == {backup_immediate.slug(): backup_immediate}

    # create a new backup behind the scenes, the pending backup should get replaced with the new one
    slug = (await ha.harequests.createBackup({'name': "Suddenly Appears", "hardlock": True}))['slug']
    results = await ha.get()
    assert len(results) == 1
    assert slug in results
    assert results[slug].name() == "Suddenly Appears"
    assert not results[slug].retained()


def test_retryable_errors():
    # SOMEDAY: retryable errors should be retried in the future
    pass


@pytest.mark.asyncio
async def test_retained_on_finish(ha: HaSource, server, time, config: Config, supervisor: SimulatedSupervisor):
    async with supervisor._backup_inner_lock:
        retention = {ha.name(): True}
        config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 0.0001)
        pending = await ha.create(CreateOptions(time.now(), "Test Name", retention))
        results = await ha.get()
        assert pending.name() == "Test Name"
        assert results == {pending.slug(): pending}
        assert type(pending) == PendingBackup
        assert not ha._pending_backup_task.done()

    await asyncio.wait({ha._pending_backup_task})
    results = list((await ha.get()).values())
    assert len(results) == 1
    assert results[0].name() == "Test Name"
    assert type(results[0]) == HABackup
    assert results[0].retained()
    assert config.isRetained(results[0].slug())


@pytest.mark.asyncio
async def test_upload(time, ha, server, uploader):
    data = await uploader.upload(createBackupTar("slug", "Test Name", time.now(), 1024 * 1024))
    dummy = DummyBackup("Test Name", time.now(), "src", "slug", "dummy")
    backup: HABackup = await ha.save(dummy, data)
    assert backup.name() == "Test Name"
    assert backup.slug() == "slug"
    assert backup.size() == round(data.size() / 1024.0 / 1024.0, 2) * 1024 * 1024
    assert backup.retained()
    # ensure its still retained on a refresh
    assert list((await ha.get()).values())[0].retained()


@pytest.mark.asyncio
async def test_corrupt_upload(time, ha, server, uploader):
    # verify a corrupt backup throws the right exception
    bad_data = await uploader.upload(getTestStream(100))
    dummy = DummyBackup("Test Name", time.now(), "src", "slug2", "dummy")

    with pytest.raises(UploadFailed):
        await ha.save(dummy, bad_data)


@pytest.mark.asyncio
async def test_upload_wrong_slug(time, ha, server, uploader):
    # verify a backup with the wrong slug also throws
    bad_data = await uploader.upload(createBackupTar("wrongslug", "Test Name", time.now(), 1024 * 1024))
    dummy = DummyBackup("Test Name", time.now(), "src", "slug", "dummy")
    with pytest.raises(UploadFailed):
        await ha.save(dummy, bad_data)


@pytest.mark.asyncio
async def test_failed_backup(time, ha: HaSource, supervisor: SimulatedSupervisor, config: Config, interceptor: RequestInterceptor):
    # create a blocking backup
    interceptor.setError(URL_MATCH_BACKUP_FULL, 524)
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 0)
    await supervisor.toggleBlockBackup()
    backup_immediate = await ha.create(CreateOptions(time.now(), "Some Name"))
    assert isinstance(backup_immediate, PendingBackup)
    assert backup_immediate.name() == "Some Name"
    assert not ha.check()
    assert not backup_immediate.isFailed()
    await supervisor.toggleBlockBackup()

    # let the backup attempt to complete
    await asyncio.wait({ha._pending_backup_task})

    # verify it failed with the expected http error
    assert backup_immediate.isFailed()
    assert backup_immediate._exception.status == 524

    backups = list((await ha.get()).values())
    assert len(backups) == 1
    assert backups[0] is backup_immediate

    # verify we can create a new backup immediately
    interceptor.clear()
    await ha.create(CreateOptions(time.now(), "Some Name"))
    assert len(await ha.get()) == 1


@pytest.mark.asyncio
async def test_failed_backup_retry(ha: HaSource, time: FakeTime, config: Config, supervisor: SimulatedSupervisor, interceptor: RequestInterceptor):
    # create a blocking backup
    interceptor.setError(URL_MATCH_BACKUP_FULL, 524)
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 0)
    await supervisor.toggleBlockBackup()
    backup_immediate = await ha.create(CreateOptions(time.now(), "Some Name"))
    assert isinstance(backup_immediate, PendingBackup)
    assert backup_immediate.name() == "Some Name"
    assert not ha.check()
    assert not backup_immediate.isFailed()
    await supervisor.toggleBlockBackup()

    # let the backup attempt to complete
    await asyncio.wait({ha._pending_backup_task})

    # verify it failed with the expected http error
    assert backup_immediate.isFailed()
    assert backup_immediate._exception.status == 524

    assert ha.check()
    assert not ha.check()
    time.advance(seconds=config.get(Setting.FAILED_BACKUP_TIMEOUT_SECONDS))

    # should trigger a sync after the failed backup timeout
    assert ha.check()
    await ha.get()
    assert not ha.check()


@pytest.mark.asyncio
async def test_immediate_backup_failure(time: FakeTime, ha: HaSource, config: Config, interceptor: RequestInterceptor):
    interceptor.setError(URL_MATCH_BACKUP_FULL, 524)
    with pytest.raises(ClientResponseError) as thrown:
        await ha.create(CreateOptions(time.now(), "Some Name"))
    assert thrown.value.status == 524

    assert ha.pending_backup is not None
    backups = list((await ha.get()).values())
    assert len(backups) == 1
    assert backups[0].isFailed()

    # Failed backup should go away after it times out
    assert ha.check()
    assert not ha.check()
    time.advance(seconds=config.get(
        Setting.FAILED_BACKUP_TIMEOUT_SECONDS) + 1)
    assert ha.check()

    assert len(await ha.get()) == 0
    assert not ha.check()


@pytest.mark.asyncio
async def test_delete_error(time, ha: HaSource, interceptor: RequestInterceptor):
    backup = await ha.create(CreateOptions(time.now(), "Some Name"))
    full = DummyBackup(backup.name(), backup.date(),
                       backup.size(), backup.slug(), "dummy")
    full.addSource(backup)
    interceptor.setError(URL_MATCH_BACKUP_DELETE, 400)
    with pytest.raises(HomeAssistantDeleteError):
        await ha.delete(full)

    interceptor.clear()
    await ha.delete(full)


@pytest.mark.asyncio
async def test_hostname(time, ha: HaSource, server, global_info: GlobalInfo):
    await ha.init()
    assert global_info.url == "/hassio/ingress/self_slug"


@pytest.mark.asyncio
async def test_supervisor_error(time, ha: HaSource, server: SimulationServer, global_info: GlobalInfo):
    await server.stop()
    with pytest.raises(SupervisorConnectionError):
        await ha.init()


@pytest.mark.asyncio
async def test_supervisor_permission_error(time, ha: HaSource, interceptor: RequestInterceptor, global_info: GlobalInfo):
    interceptor.setError(URL_MATCH_MISC_INFO, 403)
    with pytest.raises(SupervisorPermissionError):
        await ha.init()

    interceptor.clear()
    interceptor.setError(URL_MATCH_MISC_INFO, 404)
    with pytest.raises(ClientResponseError):
        await ha.init()


@pytest.mark.asyncio
async def test_download_timeout(ha: HaSource, time, interceptor: RequestInterceptor, config: Config) -> None:
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 100)
    backup: HABackup = await ha.create(CreateOptions(time.now(), "Test Name"))
    from_ha = await ha.harequests.backup(backup.slug())
    full = DummyBackup(from_ha.name(), from_ha.date(),
                       from_ha.size(), from_ha.slug(), "dummy")
    full.addSource(backup)

    interceptor.setSleep(URL_MATCH_BACKUP_DOWNLOAD, sleep=100)
    config.override(Setting.DOWNLOAD_TIMEOUT_SECONDS, 1)
    direct_download = await ha.harequests.download(backup.slug())

    with pytest.raises(SupervisorTimeoutError):
        await direct_download.setup()
        await direct_download.read(1)


@pytest.mark.asyncio
async def test_start_and_stop_addon(ha: HaSource, time, interceptor: RequestInterceptor, config: Config, supervisor: SimulatedSupervisor, addon_stopper: AddonStopper) -> None:
    addon_stopper.allowRun()
    slug = "test_slug"
    supervisor.installAddon(slug, "Test decription")
    config.override(Setting.STOP_ADDONS, slug)
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 0.001)

    assert supervisor.addon(slug)["state"] == "started"
    async with supervisor._backup_inner_lock:
        await ha.create(CreateOptions(time.now(), "Test Name"))
        assert supervisor.addon(slug)["state"] == "stopped"
    await ha._pending_backup_task
    assert supervisor.addon(slug)["state"] == "started"


@pytest.mark.asyncio
async def test_start_and_stop_two_addons(ha: HaSource, time, interceptor: RequestInterceptor, config: Config, supervisor: SimulatedSupervisor, addon_stopper: AddonStopper) -> None:
    addon_stopper.allowRun()
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")

    slug2 = "test_slug_2"
    supervisor.installAddon(slug2, "Test decription")
    config.override(Setting.STOP_ADDONS, ",".join([slug1, slug2]))
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 0.001)

    assert supervisor.addon(slug1)["state"] == "started"
    assert supervisor.addon(slug2)["state"] == "started"
    async with supervisor._backup_inner_lock:
        await ha.create(CreateOptions(time.now(), "Test Name"))
        assert supervisor.addon(slug1)["state"] == "stopped"
        assert supervisor.addon(slug2)["state"] == "stopped"
    await ha._pending_backup_task
    assert supervisor.addon(slug1)["state"] == "started"
    assert supervisor.addon(slug2)["state"] == "started"


@pytest.mark.asyncio
async def test_stop_addon_failure(ha: HaSource, time, interceptor: RequestInterceptor, config: Config, supervisor: SimulatedSupervisor, addon_stopper: AddonStopper) -> None:
    addon_stopper.allowRun()
    slug = "test_slug"
    supervisor.installAddon(slug, "Test decription")
    config.override(Setting.STOP_ADDONS, slug)
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 0.001)
    interceptor.setError(URL_MATCH_STOP_ADDON, 400)

    assert supervisor.addon(slug)["state"] == "started"
    async with supervisor._backup_inner_lock:
        await ha.create(CreateOptions(time.now(), "Test Name"))
        assert supervisor.addon(slug)["state"] == "started"
    await ha._pending_backup_task
    assert supervisor.addon(slug)["state"] == "started"
    assert len(await ha.get()) == 1


@pytest.mark.asyncio
async def test_start_addon_failure(ha: HaSource, time, interceptor: RequestInterceptor, config: Config, supervisor: SimulatedSupervisor, addon_stopper: AddonStopper) -> None:
    addon_stopper.allowRun()
    slug = "test_slug"
    supervisor.installAddon(slug, "Test decription")
    config.override(Setting.STOP_ADDONS, slug)
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 0.001)
    interceptor.setError(URL_MATCH_START_ADDON, 400)

    assert supervisor.addon(slug)["state"] == "started"
    async with supervisor._backup_inner_lock:
        await ha.create(CreateOptions(time.now(), "Test Name"))
        assert supervisor.addon(slug)["state"] == "stopped"
    await ha._pending_backup_task
    assert supervisor.addon(slug)["state"] == "stopped"
    assert len(await ha.get()) == 1


@pytest.mark.asyncio
async def test_ingore_self_when_stopping(ha: HaSource, time, interceptor: RequestInterceptor, config: Config, supervisor: SimulatedSupervisor, addon_stopper: AddonStopper) -> None:
    addon_stopper.allowRun()
    slug = supervisor._addon_slug
    config.override(Setting.STOP_ADDONS, slug)
    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 0.001)
    interceptor.setError(URL_MATCH_START_ADDON, 400)

    assert supervisor.addon(slug)["state"] == "started"
    async with supervisor._backup_inner_lock:
        await ha.create(CreateOptions(time.now(), "Test Name"))
        assert supervisor.addon(slug)["state"] == "started"
    await ha._pending_backup_task
    assert supervisor.addon(slug)["state"] == "started"
    assert not interceptor.urlWasCalled(URL_MATCH_START_ADDON)
    assert not interceptor.urlWasCalled(URL_MATCH_STOP_ADDON)
    assert len(await ha.get()) == 1


@pytest.mark.asyncio
async def test_dont_purge_pending_backup(ha: HaSource, time, config: Config, supervisor: SimulatedSupervisor, model: Model, interceptor):
    config.override(Setting.MAX_BACKUPS_IN_HA, 4)
    await ha.create(CreateOptions(time.now(), "Test Name 1"))
    await ha.create(CreateOptions(time.now(), "Test Name 2"))
    await ha.create(CreateOptions(time.now(), "Test Name 3"))
    await ha.create(CreateOptions(time.now(), "Test Name 4"))
    await model.sync(time.now())

    config.override(Setting.NEW_BACKUP_TIMEOUT_SECONDS, 0.1)
    interceptor.setSleep(URL_MATCH_BACKUP_FULL, sleep=2)
    await ha.create(CreateOptions(time.now(), "Test Name"))
    backups = list((await ha.get()).values())
    assert len(backups) == 5
    backup = backups[4]
    assert isinstance(backup, PendingBackup)

    # no backup should get purged yet because the ending backup isn't considered for purging.
    await model.sync(time.now())
    backups = list((await ha.get()).values())
    assert len(backups) == 5

    # Wait for the backup to finish, then verify one gets purged.
    await ha._pending_backup_task
    await model.sync(time.now())
    backups = list((await ha.get()).values())
    assert len(backups) == 4


@pytest.mark.asyncio
async def test_matching_pending_backup(ha: HaSource, time: Time, config: Config, supervisor: SimulatedSupervisor, model: Model, interceptor, data_cache: DataCache):
    '''
    A pending backups with the same name and within a day of the backup time should be considered
    made by the addon
    '''
    data_cache.backup("pending")[KEY_NAME] = "Test Backup"
    data_cache.backup("pending")[KEY_CREATED] = time.now().isoformat()
    data_cache.backup("pending")[KEY_LAST_SEEN] = time.now().isoformat()

    await supervisor.createBackup({"name": "Test Backup"}, date=time.now() - timedelta(hours=12))

    backups = await ha.get()
    assert len(backups) == 1
    backup = next(iter(backups.values()))
    assert backup.madeByTheAddon()


@pytest.mark.asyncio
async def test_date_match_wrong_pending_backup(ha: HaSource, time: Time, config: Config, supervisor: SimulatedSupervisor, model: Model, interceptor, data_cache: DataCache):
    '''
    A pending backups with the same name but with the wrong date shoudl nto be considered made by the addon
    '''
    data_cache.backup("pending")[KEY_NAME] = "Test Backup"
    data_cache.backup("pending")[KEY_CREATED] = time.now().isoformat()
    data_cache.backup("pending")[KEY_LAST_SEEN] = time.now().isoformat()

    await supervisor.createBackup({"name": "Test Backup"}, date=time.now() - timedelta(hours=25))

    backups = await ha.get()
    assert len(backups) == 1
    backups = next(iter(backups.values()))
    assert not backups.madeByTheAddon()


@pytest.mark.asyncio
async def test_name_wrong_match_pending_backup(ha: HaSource, time: Time, config: Config, supervisor: SimulatedSupervisor, model: Model, interceptor, data_cache: DataCache):
    '''
    A pending backups with the wrong name shoudl not be considered made by the addon
    '''
    data_cache.backup("pending")[KEY_NAME] = "Test Backup"
    data_cache.backup("pending")[KEY_CREATED] = time.now().isoformat()
    data_cache.backup("pending")[KEY_LAST_SEEN] = time.now().isoformat()

    await supervisor.createBackup({"name": "Wrong Name"}, date=time.now() - timedelta(hours=12))

    backups = await ha.get()
    assert len(backups) == 1
    backup = next(iter(backups.values()))
    assert not backup.madeByTheAddon()


@pytest.mark.asyncio
async def test_bump_last_seen(ha: HaSource, time: Time, config: Config, supervisor: SimulatedSupervisor, model: Model, interceptor, data_cache: DataCache):
    backup = await ha.create(CreateOptions(time.now(), "Test Name"))
    time.advance(days=1)
    assert backup.slug() in await ha.get()
    assert data_cache.backup(backup.slug())[KEY_LAST_SEEN] == time.now().isoformat()

    time.advance(days=1)
    assert backup.slug() in await ha.get()
    assert data_cache.backup(backup.slug())[KEY_LAST_SEEN] == time.now().isoformat()


@pytest.mark.asyncio
async def test_backup_supervisor_path(ha: HaSource, supervisor: SimulatedSupervisor, interceptor: RequestInterceptor):
    supervisor._super_version = Version(2021, 8)
    await ha.get()
    assert interceptor.urlWasCalled(URL_MATCH_BACKUPS)
    assert not interceptor.urlWasCalled(URL_MATCH_SNAPSHOT)


@pytest.mark.asyncio
async def test_backup_supervisor_path(ha: HaSource, supervisor: SimulatedSupervisor, interceptor: RequestInterceptor):
    supervisor._super_version = Version(2021, 7)
    await ha.get()
    assert not interceptor.urlWasCalled(URL_MATCH_BACKUPS)
    assert interceptor.urlWasCalled(URL_MATCH_SNAPSHOT)


@pytest.mark.asyncio
async def test_supervisor_host(ha: HaSource, supervisor: SimulatedSupervisor, interceptor: RequestInterceptor, config: Config, server_url):
    assert ha.harequests.getSupervisorURL() == server_url

    config.override(Setting.SUPERVISOR_URL, "")
    assert ha.harequests.getSupervisorURL() == URL("http://hassio")

    os.environ['SUPERVISOR_TOKEN'] = "test"
    assert ha.harequests.getSupervisorURL() == URL("http://supervisor")


@pytest.mark.asyncio
async def test_upgrade_default_config(ha: HaSource, supervisor: SimulatedSupervisor, interceptor: RequestInterceptor, config: Config, server_url):
    """Verify that converting the original default config optiosn works as expected"""

    # overwrite the addon options with old values
    supervisor._options = {
        Setting.DEPRECTAED_MAX_BACKUPS_IN_HA.value: 4,
        Setting.DEPRECTAED_MAX_BACKUPS_IN_GOOGLE_DRIVE.value: 4,
        Setting.DEPRECATED_DAYS_BETWEEN_BACKUPS.value: 3,
        Setting.USE_SSL.value: False,
    }

    await ha.init()

    assert not config.mustSaveUpgradeChanges()
    assert interceptor.urlWasCalled(URL_MATCH_SELF_OPTIONS)

    # Verify the config was upgraded
    assert supervisor._options == {
        Setting.MAX_BACKUPS_IN_HA.value: 4,
        Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE.value: 4,
        Setting.DAYS_BETWEEN_BACKUPS.value: 3,
        Setting.CALL_BACKUP_SNAPSHOT.value: True,
    }


@pytest.mark.asyncio
async def test_upgrade_all_config(ha: HaSource, supervisor: SimulatedSupervisor, interceptor: RequestInterceptor, config: Config, server_url):
    """Verify that converting all upgradeable config optiosn works as expected"""

    # overwrite the addon options with old values
    supervisor._options = {
        Setting.DEPRECTAED_MAX_BACKUPS_IN_HA.value: 1,
        Setting.DEPRECTAED_MAX_BACKUPS_IN_GOOGLE_DRIVE.value: 2,
        Setting.DEPRECATED_DAYS_BETWEEN_BACKUPS.value: 5,
        Setting.DEPRECTAED_IGNORE_OTHER_BACKUPS.value: True,
        Setting.DEPRECTAED_IGNORE_UPGRADE_BACKUPS.value: True,
        Setting.DEPRECTAED_BACKUP_TIME_OF_DAY.value: "01:11",
        Setting.DEPRECTAED_DELETE_BEFORE_NEW_BACKUP.value: True,
        Setting.DEPRECTAED_BACKUP_NAME.value: "test",
        Setting.DEPRECTAED_SPECIFY_BACKUP_FOLDER.value: True,
        Setting.DEPRECTAED_NOTIFY_FOR_STALE_BACKUPS.value: False,
        Setting.DEPRECTAED_ENABLE_BACKUP_STALE_SENSOR.value: False,
        Setting.DEPRECTAED_ENABLE_BACKUP_STATE_SENSOR.value: False,
        Setting.DEPRECATED_BACKUP_PASSWORD.value: "test password",
    }

    await ha.init()
    assert not config.mustSaveUpgradeChanges()
    assert interceptor.urlWasCalled(URL_MATCH_SELF_OPTIONS)

    # Verify the config was upgraded
    assert supervisor._options == {
        Setting.MAX_BACKUPS_IN_HA.value: 1,
        Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE.value: 2,
        Setting.DAYS_BETWEEN_BACKUPS.value: 5,
        Setting.IGNORE_OTHER_BACKUPS.value: True,
        Setting.IGNORE_UPGRADE_BACKUPS.value: True,
        Setting.BACKUP_TIME_OF_DAY.value: "01:11",
        Setting.DELETE_BEFORE_NEW_BACKUP.value: True,
        Setting.BACKUP_NAME.value: "test",
        Setting.SPECIFY_BACKUP_FOLDER.value: True,
        Setting.NOTIFY_FOR_STALE_BACKUPS.value: False,
        Setting.ENABLE_BACKUP_STALE_SENSOR.value: False,
        Setting.ENABLE_BACKUP_STATE_SENSOR.value: False,
        Setting.BACKUP_PASSWORD.value: "test password",
        Setting.CALL_BACKUP_SNAPSHOT.value: True,
    }

    interceptor.clear()

    await ha.init()
    assert not interceptor.urlWasCalled(URL_MATCH_SELF_OPTIONS)


@pytest.mark.asyncio
async def test_upgrade_some_config(ha: HaSource, supervisor: SimulatedSupervisor, interceptor: RequestInterceptor, config: Config, server_url):
    """Verify that converting a mix of upgradeable and not upgradeable config works"""

    # overwrite the addon options with old values
    supervisor._options = {
        Setting.DEPRECTAED_MAX_BACKUPS_IN_HA.value: 4,
        Setting.DEPRECTAED_MAX_BACKUPS_IN_GOOGLE_DRIVE.value: 4,
        Setting.DEPRECATED_DAYS_BETWEEN_BACKUPS.value: 3,
        Setting.DEPRECTAED_BACKUP_TIME_OF_DAY.value: "01:11",
        Setting.EXCLUDE_ADDONS.value: "test",
        Setting.USE_SSL.value: False,
    }

    await ha.init()

    assert not config.mustSaveUpgradeChanges()
    assert interceptor.urlWasCalled(URL_MATCH_SELF_OPTIONS)

    # Verify the config was upgraded
    assert supervisor._options == {
        Setting.MAX_BACKUPS_IN_HA.value: 4,
        Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE.value: 4,
        Setting.DAYS_BETWEEN_BACKUPS.value: 3,
        Setting.EXCLUDE_ADDONS.value: "test",
        Setting.BACKUP_TIME_OF_DAY.value: "01:11",
        Setting.CALL_BACKUP_SNAPSHOT.value: True,
    }


@pytest.mark.asyncio
async def test_upgrade_no_config(ha: HaSource, supervisor: SimulatedSupervisor, interceptor: RequestInterceptor, config: Config, server_url):
    """Verifies that config not in need of an upgrade doesn't get upgraded"""

    # overwrite the addon options with old values
    supervisor._options = {
        Setting.MAX_BACKUPS_IN_HA.value: 4,
        Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE.value: 4,
        Setting.DAYS_BETWEEN_BACKUPS.value: 3,
        Setting.BACKUP_TIME_OF_DAY.value: "01:11",
        Setting.EXCLUDE_ADDONS.value: "test"
    }

    await ha.init()

    assert not config.mustSaveUpgradeChanges()
    assert not interceptor.urlWasCalled(URL_MATCH_SELF_OPTIONS)

    # Verify the config was upgraded
    assert supervisor._options == {
        Setting.MAX_BACKUPS_IN_HA.value: 4,
        Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE.value: 4,
        Setting.DAYS_BETWEEN_BACKUPS.value: 3,
        Setting.BACKUP_TIME_OF_DAY.value: "01:11",
        Setting.EXCLUDE_ADDONS.value: "test",
    }


@pytest.mark.asyncio
async def test_old_delete_path(ha: HaSource, supervisor: SimulatedSupervisor, interceptor: RequestInterceptor, time: FakeTime):
    supervisor._super_version = Version(2020, 8)
    await ha.get()
    backup: HABackup = await ha.create(CreateOptions(time.now(), "Test Name"))
    full = DummyBackup(backup.name(), backup.date(),
                       backup.size(), backup.slug(), "dummy")
    full.addSource(backup)
    await ha.delete(full)
    assert interceptor.urlWasCalled("/snapshots/{0}/remove".format(backup.slug()))
