import asyncio

import pytest
from aiohttp.client_exceptions import ClientResponseError

from backup.config import Config, Setting, CreateOptions
from backup.const import SOURCE_HA
from backup.exceptions import (HomeAssistantDeleteError, SnapshotInProgress,
                               SnapshotPasswordKeyInvalid, UploadFailed, SupervisorConnectionError, SupervisorPermissionError, SupervisorTimeoutError)
from backup.util import GlobalInfo
from backup.ha import HaSource, PendingSnapshot, EVENT_SNAPSHOT_END, EVENT_SNAPSHOT_START, HASnapshot, Password, AddonStopper
from backup.model import DummySnapshot
from dev.simulationserver import SimulationServer
from .faketime import FakeTime
from .helpers import all_addons, all_folders, createSnapshotTar, getTestStream
from dev.simulated_supervisor import SimulatedSupervisor, URL_MATCH_START_ADDON, URL_MATCH_STOP_ADDON, URL_MATCH_SNAPSHOT_FULL, URL_MATCH_SNAPSHOT_DELETE, URL_MATCH_MISC_INFO, URL_MATCH_SNAPSHOT_DOWNLOAD
from dev.request_interceptor import RequestInterceptor
from backup.model import Model

@pytest.mark.asyncio
async def test_sync_empty(ha) -> None:
    assert len(await ha.get()) == 0


@pytest.mark.asyncio
async def test_CRUD(ha: HaSource, time, interceptor: RequestInterceptor) -> None:
    snapshot: HASnapshot = await ha.create(CreateOptions(time.now(), "Test Name"))

    assert snapshot.name() == "Test Name"
    assert type(snapshot) is HASnapshot
    assert not snapshot.retained()
    assert snapshot.snapshotType() == "full"
    assert not snapshot.protected()
    assert snapshot.name() == "Test Name"
    assert snapshot.source() == SOURCE_HA

    # read the item directly, its metadata should match
    from_ha = await ha.harequests.snapshot(snapshot.slug())
    assert from_ha.size() == snapshot.size()
    assert from_ha.slug() == snapshot.slug()
    assert from_ha.source() == SOURCE_HA

    snapshots = await ha.get()
    assert len(snapshots) == 1
    assert snapshot.slug() in snapshots

    full = DummySnapshot(from_ha.name(), from_ha.date(),
                         from_ha.size(), from_ha.slug(), "dummy")
    full.addSource(snapshot)

    # download the item, its bytes should match up
    download = await ha.read(full)
    await download.setup()
    direct_download = await ha.harequests.download(snapshot.slug())
    await direct_download.setup()
    while True:
        from_file = await direct_download.read(1024 * 1024)
        from_download = await download.read(1024 * 1024)
        if len(from_file.getbuffer()) == 0:
            assert len(from_download.getbuffer()) == 0
            break
        assert from_file.getbuffer() == from_download.getbuffer()

    # update retention
    assert not snapshot.retained()
    await ha.retain(full, True)
    assert (await ha.get())[full.slug()].retained()
    await ha.retain(full, False)
    assert not (await ha.get())[full.slug()].retained()

    # Delete the item, make sure its gone
    await ha.delete(full)
    assert full.getSource(ha.name()) is None
    snapshots = await ha.get()
    assert len(snapshots) == 0


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_pending_snapshot_nowait(ha: HaSource, time, supervisor: SimulatedSupervisor, interceptor: RequestInterceptor, config: Config):
    interceptor.setSleep(URL_MATCH_SNAPSHOT_FULL, sleep=5)
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 0.1)
    snapshot_immediate: PendingSnapshot = await ha.create(CreateOptions(time.now(), "Test Name"))
    assert isinstance(snapshot_immediate, PendingSnapshot)
    snapshot_pending: HASnapshot = (await ha.get())['pending']

    assert isinstance(snapshot_immediate, PendingSnapshot)
    assert isinstance(snapshot_pending, PendingSnapshot)
    assert snapshot_immediate is snapshot_pending
    assert snapshot_immediate.name() == "Test Name"
    assert snapshot_immediate.slug() == "pending"
    assert not snapshot_immediate.uploadable()
    assert snapshot_immediate.snapshotType() == "Full"
    assert snapshot_immediate.source() == SOURCE_HA
    assert snapshot_immediate.date() == time.now()
    assert not snapshot_immediate.protected()

    # Might be a little flaky but...whatever
    await asyncio.wait({ha._pending_snapshot_task})

    snapshots = await ha.get()
    assert 'pending' not in snapshots
    assert isinstance(next(iter(snapshots.values())), HASnapshot)

    return
    # ignroe events for now
    assert supervisor.getEvents() == [
        (EVENT_SNAPSHOT_START, {
            'snapshot_name': snapshot_immediate.name(),
            'snapshot_time': str(snapshot_immediate.date())})]
    ha.snapshot_thread.join()
    assert supervisor.getEvents() == [
        (EVENT_SNAPSHOT_START, {
            'snapshot_name': snapshot_immediate.name(),
            'snapshot_time': str(snapshot_immediate.date())}),
        (EVENT_SNAPSHOT_END, {
            'completed': True,
            'snapshot_name': snapshot_immediate.name(),
            'snapshot_time': str(snapshot_immediate.date())})]


@pytest.mark.asyncio
async def test_pending_snapshot_already_in_progress(ha, time, config: Config, supervisor: SimulatedSupervisor):
    await ha.create(CreateOptions(time.now(), "Test Name"))
    assert len(await ha.get()) == 1

    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 100)
    await supervisor.toggleBlockSnapshot()
    with pytest.raises(SnapshotInProgress):
        await ha.create(CreateOptions(time.now(), "Test Name"))
    snapshots = list((await ha.get()).values())
    assert len(snapshots) == 2
    snapshot = snapshots[1]

    assert isinstance(snapshot, PendingSnapshot)
    assert snapshot.name() == "Pending Snapshot"
    assert snapshot.slug() == "pending"
    assert not snapshot.uploadable()
    assert snapshot.snapshotType() == "unknown"
    assert snapshot.source() == SOURCE_HA
    assert snapshot.date() == time.now()
    assert not snapshot.protected()

    with pytest.raises(SnapshotInProgress):
        await ha.create(CreateOptions(time.now(), "Test Name"))


@pytest.mark.asyncio
async def test_partial_snapshot(ha, time, server, config: Config):
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 100)
    for folder in all_folders:
        config.override(Setting.EXCLUDE_FOLDERS, folder)
        snapshot: HASnapshot = await ha.create(CreateOptions(time.now(), "Test Name"))

        assert snapshot.snapshotType() == "partial"
        for search in all_folders:
            if search == folder:
                assert search not in snapshot.details()['folders']
            else:
                assert search in snapshot.details()['folders']

    for addon in all_addons:
        config.override(Setting.EXCLUDE_ADDONS, addon['slug'])
        snapshot: HASnapshot = await ha.create(CreateOptions(time.now(), "Test Name"))
        assert snapshot.snapshotType() == "partial"
        list_of_addons = []
        for included in snapshot.details()['addons']:
            list_of_addons.append(included['slug'])
        for search in list_of_addons:
            if search == addon:
                assert search not in list_of_addons
            else:
                assert search in list_of_addons

    # excluding addon/folders that don't exist should actually make a full snapshot
    config.override(Setting.EXCLUDE_ADDONS, "none,of.these,are.addons")
    config.override(Setting.EXCLUDE_FOLDERS, "not,folders,either")
    snapshot: HASnapshot = await ha.create(CreateOptions(time.now(), "Test Name"))
    assert snapshot.snapshotType() == "full"


@pytest.mark.asyncio
async def test_snapshot_password(ha: HaSource, config: Config, time):
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 100)
    snapshot: HASnapshot = await ha.create(CreateOptions(time.now(), "Test Name"))
    assert not snapshot.protected()

    config.override(Setting.SNAPSHOT_PASSWORD, 'test')
    snapshot = await ha.create(CreateOptions(time.now(), "Test Name"))
    assert snapshot.protected()

    config.override(Setting.SNAPSHOT_PASSWORD, 'test')
    assert Password(ha.config).resolve() == 'test'

    config.override(Setting.SNAPSHOT_PASSWORD, '!secret for_unit_tests')
    assert Password(ha.config).resolve() == 'password value'

    config.override(Setting.SNAPSHOT_PASSWORD, '!secret bad_key')
    with pytest.raises(SnapshotPasswordKeyInvalid):
        Password(config).resolve()

    config.override(Setting.SECRETS_FILE_PATH, "/bad/file/path")
    config.override(Setting.SNAPSHOT_PASSWORD, '!secret for_unit_tests')
    with pytest.raises(SnapshotPasswordKeyInvalid):
        Password(ha.config).resolve()


@pytest.mark.asyncio
async def test_snapshot_name(time: FakeTime, ha):
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
    snapshot: HASnapshot = await ha.create(CreateOptions(time, template))
    assert snapshot.name() == expected


@pytest.mark.asyncio
async def test_default_name(time: FakeTime, ha, server):
    snapshot = await ha.create(CreateOptions(time.now(), ""))
    assert snapshot.name() == "Full Snapshot 1985-12-06 00:00:00"


@pytest.mark.asyncio
async def test_pending_snapshot_timeout(time: FakeTime, ha: HaSource, config: Config, interceptor: RequestInterceptor):
    interceptor.setSleep(URL_MATCH_SNAPSHOT_FULL, sleep=5)
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 1)
    config.override(Setting.FAILED_SNAPSHOT_TIMEOUT_SECONDS, 1)
    config.override(Setting.PENDING_SNAPSHOT_TIMEOUT_SECONDS, 1)

    snapshot_immediate: PendingSnapshot = await ha.create(CreateOptions(time.now(), "Test Name"))
    assert isinstance(snapshot_immediate, PendingSnapshot)
    assert snapshot_immediate.name() == "Test Name"
    assert not ha.check()
    assert ha.pending_snapshot is snapshot_immediate

    await asyncio.wait({ha._pending_snapshot_task})
    assert ha.pending_snapshot is snapshot_immediate
    assert ha.check()
    assert not ha.check()

    time.advance(minutes=1)
    assert ha.check()
    assert len(await ha.get()) == 0
    assert not ha.check()
    assert ha.pending_snapshot is None
    assert snapshot_immediate.isStale()


@pytest.mark.asyncio
async def test_pending_snapshot_timeout_external(time, config, ha: HaSource, supervisor: SimulatedSupervisor):
    # now configure a snapshto to start outside of the addon
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 100)
    await supervisor.toggleBlockSnapshot()
    with pytest.raises(SnapshotInProgress):
        await ha.create(CreateOptions(time.now(), "Ignored"))
    snapshot_immediate = (await ha.get())['pending']
    await supervisor.toggleBlockSnapshot()
    assert isinstance(snapshot_immediate, PendingSnapshot)
    assert snapshot_immediate.name() == "Pending Snapshot"
    assert ha.check()
    assert not ha.check()
    assert ha.pending_snapshot is snapshot_immediate

    # should clean up after a day, since we're still waiting on the snapshot thread.
    time.advanceDay()
    assert ha.check()
    assert len(await ha.get()) == 0


@pytest.mark.asyncio
async def test_pending_snapshot_replaces_original(time, ha: HaSource, config: Config, supervisor: SimulatedSupervisor):
    # now configure a snapshto to start outside of the addon
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 100)
    await supervisor.toggleBlockSnapshot()
    with pytest.raises(SnapshotInProgress):
        await ha.create(CreateOptions(time.now(), "Ignored"))
    snapshot_immediate = (await ha.get())['pending']
    await supervisor.toggleBlockSnapshot()
    assert isinstance(snapshot_immediate, PendingSnapshot)
    assert snapshot_immediate.name() == "Pending Snapshot"
    assert ha.check()
    assert ha.pending_snapshot is snapshot_immediate
    assert await ha.get() == {snapshot_immediate.slug(): snapshot_immediate}

    # create a new snapshot behind the scenes, the pending snapshot should get replaced with the new one
    slug = (await ha.harequests.createSnapshot({'name': "Suddenly Appears", "hardlock": True}))['slug']
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
    async with supervisor._snapshot_inner_lock:
        retention = {ha.name(): True}
        config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 0.0001)
        pending = await ha.create(CreateOptions(time.now(), "Test Name", retention))
        results = await ha.get()
        assert pending.name() == "Test Name"
        assert results == {pending.slug(): pending}
        assert type(pending) == PendingSnapshot
        assert not ha._pending_snapshot_task.done()

    await asyncio.wait({ha._pending_snapshot_task})
    results = list((await ha.get()).values())
    assert len(results) == 1
    assert results[0].name() == "Test Name"
    assert type(results[0]) == HASnapshot
    assert results[0].retained()
    assert config.isRetained(results[0].slug())


@pytest.mark.asyncio
async def test_upload(time, ha, server, uploader):
    data = await uploader.upload(createSnapshotTar("slug", "Test Name", time.now(), 1024 * 1024))
    dummy = DummySnapshot("Test Name", time.now(), "src", "slug", "dummy")
    snapshot: HASnapshot = await ha.save(dummy, data)
    assert snapshot.name() == "Test Name"
    assert snapshot.slug() == "slug"
    assert snapshot.size() == round(data.size() / 1024.0 / 1024.0, 2) * 1024 * 1024
    assert snapshot.retained()
    # ensure its still retained on a refresh
    assert list((await ha.get()).values())[0].retained()


@pytest.mark.asyncio
async def test_corrupt_upload(time, ha, server, uploader):
    # verify a corrupt snapshot throws the right exception
    bad_data = await uploader.upload(getTestStream(100))
    dummy = DummySnapshot("Test Name", time.now(), "src", "slug2", "dummy")

    with pytest.raises(UploadFailed):
        await ha.save(dummy, bad_data)


@pytest.mark.asyncio
async def test_upload_wrong_slug(time, ha, server, uploader):
    # verify a snapshot with the wrong slug also throws
    bad_data = await uploader.upload(createSnapshotTar("wrongslug", "Test Name", time.now(), 1024 * 1024))
    dummy = DummySnapshot("Test Name", time.now(), "src", "slug", "dummy")
    with pytest.raises(UploadFailed):
        await ha.save(dummy, bad_data)


@pytest.mark.asyncio
async def test_failed_snapshot(time, ha: HaSource, supervisor: SimulatedSupervisor, config: Config, interceptor: RequestInterceptor):
    # create a blocking snapshot
    interceptor.setError(URL_MATCH_SNAPSHOT_FULL, 524)
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 0)
    await supervisor.toggleBlockSnapshot()
    snapshot_immediate = await ha.create(CreateOptions(time.now(), "Some Name"))
    assert isinstance(snapshot_immediate, PendingSnapshot)
    assert snapshot_immediate.name() == "Some Name"
    assert not ha.check()
    assert not snapshot_immediate.isFailed()
    await supervisor.toggleBlockSnapshot()

    # let the snapshot attempt to complete
    await asyncio.wait({ha._pending_snapshot_task})

    # verify it failed with the expected http error
    assert snapshot_immediate.isFailed()
    assert snapshot_immediate._exception.status == 524

    snapshots = list((await ha.get()).values())
    assert len(snapshots) == 1
    assert snapshots[0] is snapshot_immediate

    # verify we can create a new snapshot immediately
    interceptor.clear()
    await ha.create(CreateOptions(time.now(), "Some Name"))
    assert len(await ha.get()) == 1


@pytest.mark.asyncio
async def test_failed_snapshot_retry(ha: HaSource, time: FakeTime, config: Config, supervisor: SimulatedSupervisor, interceptor: RequestInterceptor):
    # create a blocking snapshot
    interceptor.setError(URL_MATCH_SNAPSHOT_FULL, 524)
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 0)
    await supervisor.toggleBlockSnapshot()
    snapshot_immediate = await ha.create(CreateOptions(time.now(), "Some Name"))
    assert isinstance(snapshot_immediate, PendingSnapshot)
    assert snapshot_immediate.name() == "Some Name"
    assert not ha.check()
    assert not snapshot_immediate.isFailed()
    await supervisor.toggleBlockSnapshot()

    # let the snapshot attempt to complete
    await asyncio.wait({ha._pending_snapshot_task})

    # verify it failed with the expected http error
    assert snapshot_immediate.isFailed()
    assert snapshot_immediate._exception.status == 524

    assert ha.check()
    assert not ha.check()
    time.advance(seconds=config.get(Setting.FAILED_SNAPSHOT_TIMEOUT_SECONDS))

    # should trigger a sync after the failed snapshot timeout
    assert ha.check()
    await ha.get()
    assert not ha.check()


@pytest.mark.asyncio
async def test_immediate_snapshot_failure(time: FakeTime, ha: HaSource, config: Config, interceptor: RequestInterceptor):
    interceptor.setError(URL_MATCH_SNAPSHOT_FULL, 524)
    with pytest.raises(ClientResponseError) as thrown:
        await ha.create(CreateOptions(time.now(), "Some Name"))
    assert thrown.value.status == 524

    assert ha.pending_snapshot is not None
    snapshots = list((await ha.get()).values())
    assert len(snapshots) == 1
    assert snapshots[0].isFailed()

    # Failed snapshot should go away after it times out
    assert ha.check()
    assert not ha.check()
    time.advance(seconds=config.get(
        Setting.FAILED_SNAPSHOT_TIMEOUT_SECONDS) + 1)
    assert ha.check()

    assert len(await ha.get()) == 0
    assert not ha.check()


@pytest.mark.asyncio
async def test_delete_error(time, ha: HaSource, interceptor: RequestInterceptor):
    snapshot = await ha.create(CreateOptions(time.now(), "Some Name"))
    full = DummySnapshot(snapshot.name(), snapshot.date(),
                         snapshot.size(), snapshot.slug(), "dummy")
    full.addSource(snapshot)
    interceptor.setError(URL_MATCH_SNAPSHOT_DELETE, 400)
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
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 100)
    snapshot: HASnapshot = await ha.create(CreateOptions(time.now(), "Test Name"))
    from_ha = await ha.harequests.snapshot(snapshot.slug())
    full = DummySnapshot(from_ha.name(), from_ha.date(),
                         from_ha.size(), from_ha.slug(), "dummy")
    full.addSource(snapshot)

    interceptor.setSleep(URL_MATCH_SNAPSHOT_DOWNLOAD, sleep=100)
    config.override(Setting.DOWNLOAD_TIMEOUT_SECONDS, 1)
    direct_download = await ha.harequests.download(snapshot.slug())

    with pytest.raises(SupervisorTimeoutError):
        await direct_download.setup()
        await direct_download.read(1)


@pytest.mark.asyncio
async def test_start_and_stop_addon(ha: HaSource, time, interceptor: RequestInterceptor, config: Config, supervisor: SimulatedSupervisor, addon_stopper: AddonStopper) -> None:
    addon_stopper.allowRun()
    slug = "test_slug"
    supervisor.installAddon(slug, "Test decription")
    config.override(Setting.STOP_ADDONS, slug)
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 0.001)

    assert supervisor.addon(slug)["state"] == "started"
    async with supervisor._snapshot_inner_lock:
        await ha.create(CreateOptions(time.now(), "Test Name"))
        assert supervisor.addon(slug)["state"] == "stopped"
    await ha._pending_snapshot_task
    assert supervisor.addon(slug)["state"] == "started"


@pytest.mark.asyncio
async def test_start_and_stop_two_addons(ha: HaSource, time, interceptor: RequestInterceptor, config: Config, supervisor: SimulatedSupervisor, addon_stopper: AddonStopper) -> None:
    addon_stopper.allowRun()
    slug1 = "test_slug_1"
    supervisor.installAddon(slug1, "Test decription")

    slug2 = "test_slug_2"
    supervisor.installAddon(slug2, "Test decription")
    config.override(Setting.STOP_ADDONS, ",".join([slug1, slug2]))
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 0.001)

    assert supervisor.addon(slug1)["state"] == "started"
    assert supervisor.addon(slug2)["state"] == "started"
    async with supervisor._snapshot_inner_lock:
        await ha.create(CreateOptions(time.now(), "Test Name"))
        assert supervisor.addon(slug1)["state"] == "stopped"
        assert supervisor.addon(slug2)["state"] == "stopped"
    await ha._pending_snapshot_task
    assert supervisor.addon(slug1)["state"] == "started"
    assert supervisor.addon(slug2)["state"] == "started"


@pytest.mark.asyncio
async def test_stop_addon_failure(ha: HaSource, time, interceptor: RequestInterceptor, config: Config, supervisor: SimulatedSupervisor, addon_stopper: AddonStopper) -> None:
    addon_stopper.allowRun()
    slug = "test_slug"
    supervisor.installAddon(slug, "Test decription")
    config.override(Setting.STOP_ADDONS, slug)
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 0.001)
    interceptor.setError(URL_MATCH_STOP_ADDON, 400)

    assert supervisor.addon(slug)["state"] == "started"
    async with supervisor._snapshot_inner_lock:
        await ha.create(CreateOptions(time.now(), "Test Name"))
        assert supervisor.addon(slug)["state"] == "started"
    await ha._pending_snapshot_task
    assert supervisor.addon(slug)["state"] == "started"
    assert len(await ha.get()) == 1


@pytest.mark.asyncio
async def test_start_addon_failure(ha: HaSource, time, interceptor: RequestInterceptor, config: Config, supervisor: SimulatedSupervisor, addon_stopper: AddonStopper) -> None:
    addon_stopper.allowRun()
    slug = "test_slug"
    supervisor.installAddon(slug, "Test decription")
    config.override(Setting.STOP_ADDONS, slug)
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 0.001)
    interceptor.setError(URL_MATCH_START_ADDON, 400)

    assert supervisor.addon(slug)["state"] == "started"
    async with supervisor._snapshot_inner_lock:
        await ha.create(CreateOptions(time.now(), "Test Name"))
        assert supervisor.addon(slug)["state"] == "stopped"
    await ha._pending_snapshot_task
    assert supervisor.addon(slug)["state"] == "stopped"
    assert len(await ha.get()) == 1


@pytest.mark.asyncio
async def test_ingore_self_when_stopping(ha: HaSource, time, interceptor: RequestInterceptor, config: Config, supervisor: SimulatedSupervisor, addon_stopper: AddonStopper) -> None:
    addon_stopper.allowRun()
    slug = supervisor._addon_slug
    config.override(Setting.STOP_ADDONS, slug)
    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 0.001)
    interceptor.setError(URL_MATCH_START_ADDON, 400)

    assert supervisor.addon(slug)["state"] == "started"
    async with supervisor._snapshot_inner_lock:
        await ha.create(CreateOptions(time.now(), "Test Name"))
        assert supervisor.addon(slug)["state"] == "started"
    await ha._pending_snapshot_task
    assert supervisor.addon(slug)["state"] == "started"
    assert not interceptor.urlWasCalled(URL_MATCH_START_ADDON)
    assert not interceptor.urlWasCalled(URL_MATCH_STOP_ADDON)
    assert len(await ha.get()) == 1


@pytest.mark.asyncio
async def test_dont_purge_pending_snapshot(ha: HaSource, time, config: Config, supervisor: SimulatedSupervisor, model: Model, interceptor):
    config.override(Setting.MAX_SNAPSHOTS_IN_HASSIO, 4)
    await ha.create(CreateOptions(time.now(), "Test Name 1"))
    await ha.create(CreateOptions(time.now(), "Test Name 2"))
    await ha.create(CreateOptions(time.now(), "Test Name 3"))
    await ha.create(CreateOptions(time.now(), "Test Name 4"))
    await model.sync(time.now())

    config.override(Setting.NEW_SNAPSHOT_TIMEOUT_SECONDS, 0.1)
    interceptor.setSleep(URL_MATCH_SNAPSHOT_FULL, sleep=2)
    await ha.create(CreateOptions(time.now(), "Test Name"))
    snapshots = list((await ha.get()).values())
    assert len(snapshots) == 5
    snapshot = snapshots[4]
    assert isinstance(snapshot, PendingSnapshot)

    # no snapshot should get purged yet because the ending snapshot isn't considered for purging.
    await model.sync(time.now())
    snapshots = list((await ha.get()).values())
    assert len(snapshots) == 5

    # Wait for the snapshot to finish, then verify one gets purged.
    await ha._pending_snapshot_task
    await model.sync(time.now())
    snapshots = list((await ha.get()).values())
    assert len(snapshots) == 4
