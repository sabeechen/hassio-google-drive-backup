import pytest
from os.path import exists
from os import remove
from requests.exceptions import HTTPError
from ..hasource import HaSource, PendingSnapshot
from ..snapshots import HASnapshot, DummySnapshot
from .faketime import FakeTime
from ..exceptions import SnapshotInProgress, SnapshotPasswordKeyInvalid, UploadFailed, HomeAssistantDeleteError
from ..model import CreateOptions
from ..config import Config
from .helpers import createSnapshotTar, getTestStream, all_folders, all_addons
from .conftest import ServerInstance
from ..const import SOURCE_HA
from ..settings import Setting
from ..password import Password
from ..globalinfo import GlobalInfo
from ..harequests import EVENT_SNAPSHOT_START, EVENT_SNAPSHOT_END


def test_sync_empty(ha) -> None:
    assert len(ha.get()) == 0


def test_CRUD(ha, time, server: ServerInstance) -> None:
    server.getServer()._options.update({"new_snapshot_timeout_seconds": 100})
    snapshot: HASnapshot = ha.create(CreateOptions(time.now(), "Test Name"))

    assert snapshot.name() == "Test Name"
    assert type(snapshot) is HASnapshot
    assert not snapshot.retained()
    assert snapshot.snapshotType() == "full"
    assert not snapshot.protected()
    assert snapshot.name() == "Test Name"
    assert snapshot.source() == SOURCE_HA

    # read the item directly, its metadata should match
    from_ha = ha.harequests.snapshot(snapshot.slug())
    assert from_ha.size() == snapshot.size()
    assert from_ha.slug() == snapshot.slug()
    assert from_ha.source() == SOURCE_HA

    snapshots = ha.get()
    assert len(snapshots) == 1
    assert snapshot.slug() in snapshots

    full = DummySnapshot(from_ha.name(), from_ha.date(), from_ha.size(), from_ha.slug(), "dummy")
    full.addSource(snapshot)

    # download the item, its bytes should match up
    download = ha.read(full)
    direct_download = ha.harequests.download(snapshot.slug())
    while True:
        from_file = direct_download.read(1024 * 1024)
        from_download = download.read(1024 * 1024)
        if len(from_file) == 0:
            assert len(from_download) == 0
            break
        assert from_file == from_download

    # update retention
    assert not snapshot.retained()
    ha.retain(full, True)
    assert ha.get()[full.slug()].retained()
    ha.retain(full, False)
    assert not ha.get()[full.slug()].retained()

    # Delete the item, make sure its gone
    ha.delete(full)
    assert full.getSource(ha.name()) is None
    snapshots = ha.get()
    assert len(snapshots) == 0


def test_pending_snapshot_nowait(ha: HaSource, time, server):
    server.update({"snapshot_wait_time": 5})
    server.getServer()._options.update({"new_snapshot_timeout_seconds": 0})
    snapshot_immediate: PendingSnapshot = ha.create(CreateOptions(time.now(), "Test Name"))
    assert isinstance(snapshot_immediate, PendingSnapshot)
    snapshot_pending: HASnapshot = ha.get()['pending']

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
    ha.snapshot_thread.join(1)
    assert server.getServer().getEvents() == [
        (EVENT_SNAPSHOT_START, {
            'snapshot_name': snapshot_immediate.name(),
            'snapshot_time': str(snapshot_immediate.date())})]
    ha.snapshot_thread.join()
    assert server.getServer().getEvents() == [
        (EVENT_SNAPSHOT_START, {
            'snapshot_name': snapshot_immediate.name(),
            'snapshot_time': str(snapshot_immediate.date())}),
        (EVENT_SNAPSHOT_END, {
            'completed': True,
            'snapshot_name': snapshot_immediate.name(),
            'snapshot_time': str(snapshot_immediate.date())})]


def test_pending_snapshot_already_in_progress(ha, time, server: ServerInstance):
    server.getServer()._options.update({"new_snapshot_timeout_seconds": 100})
    with server.blockSnapshots():
        with pytest.raises(SnapshotInProgress):
            ha.create(CreateOptions(time.now(), "Test Name"))
        snapshots = list(ha.get().values())
        assert len(snapshots) == 1
        snapshot = snapshots[0]

    # Verify we logged events to start/end the snapshot
    assert server.getServer().getEvents() == [
        (EVENT_SNAPSHOT_START, {
            'snapshot_name': 'Test Name',
            'snapshot_time': str(snapshot.date())}),
        (EVENT_SNAPSHOT_END, {
            'completed': False,
            'snapshot_name': "Test Name",
            'snapshot_time': str(snapshot.date())})]

    assert isinstance(snapshot, PendingSnapshot)
    assert snapshot.name() == "Pending Snapshot"
    assert snapshot.slug() == "pending"
    assert not snapshot.uploadable()
    assert snapshot.snapshotType() == "Unknown"
    assert snapshot.source() == SOURCE_HA
    assert snapshot.date() == time.now()
    assert not snapshot.protected()

    with pytest.raises(SnapshotInProgress):
        ha.create(CreateOptions(time.now(), "Test Name"))

    # Shouldn't see another start/fail because the addon already knows 
    # there is a pending snapshot.
    assert len(server.getServer().getEvents()) == 2


def test_partial_snapshot(ha, time, server: ServerInstance, config: Config):
    server.getServer()._options.update({"new_snapshot_timeout_seconds": 100})
    for folder in all_folders:
        server.getServer()._options.update({'exclude_folders': folder})
        snapshot: HASnapshot = ha.create(CreateOptions(time.now(), "Test Name"))

        assert snapshot.snapshotType() == "partial"
        for search in all_folders:
            if search == folder:
                assert search not in snapshot.details()['folders']
            else:
                assert search in snapshot.details()['folders']

    for addon in all_addons:
        server.getServer()._options.update({'exclude_addons': addon['slug']})
        snapshot: HASnapshot = ha.create(CreateOptions(time.now(), "Test Name"))
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
    server.getServer()._options.update({'exclude_addons': "none,of.these,are.addons", 'exclude_folders': "not,folders,either"})
    snapshot: HASnapshot = ha.create(CreateOptions(time.now(), "Test Name"))
    assert snapshot.snapshotType() == "full"


def test_snapshot_password(ha: HaSource, config, time, server: ServerInstance):
    server.getServer()._options.update({"new_snapshot_timeout_seconds": 100})
    snapshot: HASnapshot = ha.create(CreateOptions(time.now(), "Test Name"))
    assert not snapshot.protected()

    server.getServer()._options.update({'snapshot_password': 'test'})
    snapshot = ha.create(CreateOptions(time.now(), "Test Name"))
    assert snapshot.protected()

    ha.config.override(Setting.SNAPSHOT_PASSWORD, 'test')
    assert Password(ha.config).resolve() == 'test'

    ha.config.override(Setting.SNAPSHOT_PASSWORD, '!secret for_unit_tests')
    assert Password(ha.config).resolve() == 'password value'

    ha.config.override(Setting.SNAPSHOT_PASSWORD, '!secret bad_key')
    try:
        Password(ha.config).resolve()
        assert False
    except SnapshotPasswordKeyInvalid:
        # expected
        pass

    ha.config.override(Setting.SECRETS_FILE_PATH, "/bad/file/path")
    ha.config.override(Setting.SNAPSHOT_PASSWORD, '!secret for_unit_tests')
    try:
        Password(ha.config).resolve()
        assert False
    except SnapshotPasswordKeyInvalid:
        # expected
        pass


def test_snapshot_name(time: FakeTime, ha):
    time.setNow(time.local(1985, 12, 6, 15, 8, 9, 10))
    assertName(ha, time.now(), "{type}", "Full")
    assertName(ha, time.now(), "{year}", "1985")
    assertName(ha, time.now(), "{year_short}", "85")
    assertName(ha, time.now(), "{weekday}", "Friday")
    assertName(ha, time.now(), "{weekday_short}", "Fri")
    assertName(ha, time.now(), "{month}", "12")
    assertName(ha, time.now(), "{month_long}", "December")
    assertName(ha, time.now(), "{month_short}", "Dec")
    assertName(ha, time.now(), "{ms}", "000010")
    assertName(ha, time.now(), "{day}", "06")
    assertName(ha, time.now(), "{hr24}", "15")
    assertName(ha, time.now(), "{hr12}", "03")
    assertName(ha, time.now(), "{min}", "08")
    assertName(ha, time.now(), "{sec}", "09")
    assertName(ha, time.now(), "{ampm}", "PM")
    assertName(ha, time.now(), "{version_ha}", "0.93.1")
    assertName(ha, time.now(), "{version_hassos}", "0.69.69")
    assertName(ha, time.now(), "{version_super}", "2.2.2")
    assertName(ha, time.now(), "{date}", "12/06/85")
    assertName(ha, time.now(), "{time}", "15:08:09")
    assertName(ha, time.now(), "{datetime}", "Fri Dec  6 15:08:09 1985")
    assertName(ha, time.now(), "{isotime}", "1985-12-06T15:08:09.000010-05:00")


def assertName(ha: HaSource, time, template: str, expected: str):
    snapshot: HASnapshot = ha.create(CreateOptions(time, template))
    assert snapshot.name() == expected


def test_default_name(time: FakeTime, ha, server):
    snapshot = ha.create(CreateOptions(time.now(), ""))
    assert snapshot.name() == "Full Snapshot 1985-12-06 00:00:00"


def test_pending_snapshot_timeout(time: FakeTime, ha, server: ServerInstance):
    server.update({"snapshot_wait_time": 5})
    server.getServer()._options.update({"new_snapshot_timeout_seconds": 0})
    server.getServer().getEvents()
    snapshot_immediate: PendingSnapshot = ha.create(CreateOptions(time.now(), "Test Name"))
    assert isinstance(snapshot_immediate, PendingSnapshot)
    assert snapshot_immediate.name() == "Test Name"
    assert not ha.check()
    assert ha.pending_snapshot is snapshot_immediate

    # shouldn't clean up after a day, since we're still waiting on the snapshot thread.
    time.advanceDay()
    assert not ha.check()
    assert ha.pending_snapshot is not None


def test_pending_snapshot_timeout_external(time, ha: HaSource, server: ServerInstance):
    # now configure a snapshto to start outside of the addon
    server.getServer()._options.update({"new_snapshot_timeout_seconds": 100})
    with server.blockSnapshots():
        with pytest.raises(SnapshotInProgress):
            ha.create(CreateOptions(time.now(), "Ignored"))
        snapshot_immediate = ha.get()['pending']
    assert isinstance(snapshot_immediate, PendingSnapshot)
    assert snapshot_immediate.name() == "Pending Snapshot"
    assert not ha.check()
    assert ha.pending_snapshot is snapshot_immediate

    # should clean up after a day, since we're still waiting on the snapshot thread.
    time.advanceDay()
    assert ha.check()
    assert ha.pending_snapshot is None
    assert not ha.check()


def test_pending_snapshot_replaces_original(time, ha: HaSource, server: ServerInstance):
    # now configure a snapshto to start outside of the addon
    server.getServer()._options.update({"new_snapshot_timeout_seconds": 100})
    with server.blockSnapshots():
        with pytest.raises(SnapshotInProgress):
            ha.create(CreateOptions(time.now(), "Ignored"))
        snapshot_immediate = ha.get()['pending']
    assert isinstance(snapshot_immediate, PendingSnapshot)
    assert snapshot_immediate.name() == "Pending Snapshot"
    assert not ha.check()
    assert ha.pending_snapshot is snapshot_immediate
    assert ha.get() == {snapshot_immediate.slug(): snapshot_immediate}

    # create a new snapshot behind the scenes, the pending snapshto should get replaced with the new one
    slug = ha.harequests.createSnapshot({'name': "Suddenly Appears", "hardlock": True})['slug']
    results = ha.get()
    assert len(results) == 1
    assert slug in results
    assert results[slug].name() == "Suddenly Appears"
    assert not results[slug].retained()


def test_retryable_errors():
    # SOMEDAY: retryable errors should be retried in the future
    pass


def test_retained_on_finish(ha: HaSource, server: ServerInstance, time):
    with server.blockSnapshots():
        server.update({'always_hard_lock': True})
        retention = {ha.name(): True}
        server.getServer()._options.update({"new_snapshot_timeout_seconds": 0})
        pending = ha.create(CreateOptions(time.now(), "Test Name", retention))
        results = ha.get()
        assert pending.name() == "Test Name"
        assert results == {pending.slug(): pending}
        assert type(pending) == PendingSnapshot
        assert ha.snapshot_thread.is_alive()
    ha.snapshot_thread.join()
    results = list(ha.get().values())
    assert len(results) == 1
    assert results[0].name() == "Test Name"
    assert type(results[0]) == HASnapshot
    assert results[0].retained()


def test_upload(time, ha):
    data = createSnapshotTar("slug", "Test Name", time.now(), 1024 * 1024)
    dummy = DummySnapshot("Test Name", time.now(), "src", "slug", "dummy")
    snapshot: HASnapshot = ha.save(dummy, data)
    assert snapshot.name() == "Test Name"
    assert snapshot.slug() == "slug"
    assert snapshot.size() == round(len(data.getbuffer()) / 1024.0 / 1024.0, 2) * 1024 * 1024
    assert snapshot.retained()
    # ensure its still retained on a refresh
    assert list(ha.get().values())[0].retained()


def test_corrupt_upload(time, ha):
    # verify a corrupt snapshot throws the right exception
    bad_data = getTestStream(100)
    dummy = DummySnapshot("Test Name", time.now(), "src", "slug2", "dummy")
    try:
        ha.save(dummy, bad_data)
        assert False
    except UploadFailed:
        # expected
        pass


def test_upload_wrong_slug(time, ha):
    # verify a snapshot with the wrong slug also throws
    data = createSnapshotTar("wrongslug", "Test Name", time.now(), 1024 * 1024)
    dummy = DummySnapshot("Test Name", time.now(), "src", "slug", "dummy")
    try:
        ha.save(dummy, data)
        assert False
    except UploadFailed:
        # expected
        pass


def test_failed_snapshot(time, ha: HaSource, server: ServerInstance):
    # create a blocking snapshot
    server.update({"hassio_snapshot_error": 524, 'always_hard_lock': True})
    server.getServer()._options.update({"new_snapshot_timeout_seconds": 0})
    with server.blockSnapshots():
        snapshot_immediate = ha.create(CreateOptions(time.now(), "Some Name"))
        assert isinstance(snapshot_immediate, PendingSnapshot)
        assert snapshot_immediate.name() == "Some Name"
        assert not ha.check()
        assert not snapshot_immediate.isFailed()

    # let the snapshot attempt to complete
    ha.snapshot_thread.join()

    # verify it failed with the expected http error
    assert snapshot_immediate.isFailed()
    assert snapshot_immediate._exception.response.status_code == 524

    snapshots = list(ha.get().values())
    assert len(snapshots) == 1
    assert snapshots[0] is snapshot_immediate

    # verify we can create a new snapshot immediately
    server.update({"hassio_snapshot_error": None})
    ha.create(CreateOptions(time.now(), "Some Name"))
    assert len(ha.get()) == 1


def test_failed_snapshot_retry(ha: HaSource, server: ServerInstance, time: FakeTime, config: Config):
    # create a blocking snapshot
    server.update({"hassio_snapshot_error": 524, 'always_hard_lock': True})
    server.getServer()._options.update({"new_snapshot_timeout_seconds": 0})
    with server.blockSnapshots():
        snapshot_immediate = ha.create(CreateOptions(time.now(), "Some Name"))
        assert isinstance(snapshot_immediate, PendingSnapshot)
        assert snapshot_immediate.name() == "Some Name"
        assert not ha.check()
        assert not snapshot_immediate.isFailed()

    # let the snapshot attempt to complete
    ha.snapshot_thread.join()

    # verify it failed with the expected http error
    assert snapshot_immediate.isFailed()
    assert snapshot_immediate._exception.response.status_code == 524

    assert not ha.check()
    time.advance(seconds=config.get(Setting.FAILED_SNAPSHOT_TIMEOUT_SECONDS))

    # should trigger a sync after the failed snapshot timeout
    assert ha.check()
    assert not ha.check()


def test_immediate_snapshot_failure(time, ha: HaSource, server: ServerInstance):
    server.update({"hassio_snapshot_error": 524})
    with pytest.raises(HTTPError) as thrown:
        ha.create(CreateOptions(time.now(), "Some Name"))
    assert thrown.value.response.status_code == 524

    # shouldn't have stored the failed snapshot
    assert ha.pending_snapshot is None
    assert len(ha.get()) == 0


def test_delete_error(time, ha: HaSource, server: ServerInstance):
    snapshot = ha.create(CreateOptions(time.now(), "Some Name"))
    full = DummySnapshot(snapshot.name(), snapshot.date(), snapshot.size(), snapshot.slug(), "dummy")
    full.addSource(snapshot)
    server.update({"hassio_error": 400})
    with pytest.raises(HomeAssistantDeleteError):
        ha.delete(full)

    server.update({"hassio_error": None})
    ha.delete(full)


def test_hostname(time, ha: HaSource, server: ServerInstance, global_info: GlobalInfo):
    ha.init()
    assert global_info.url == "/hassio/ingress/self_slug"


def test_ingress_upgrade(time, ha: HaSource, config: Config):
    # check the default before init
    assert exists(config.get(Setting.CREDENTIALS_FILE_PATH))
    assert not exists(config.get(Setting.INGRESS_TOKEN_FILE_PATH))
    assert not ha.runTemporaryServer()
    ha.init()

    # should run the server, since this is an upgrade
    assert ha.runTemporaryServer()
    assert not exists(config.get(Setting.INGRESS_TOKEN_FILE_PATH))

    ha.init()
    assert ha.runTemporaryServer()
    assert not exists(config.get(Setting.INGRESS_TOKEN_FILE_PATH))


def test_ingress_upgrade_new_install(time, ha: HaSource, config: Config):
    # check the default before init
    remove(config.get(Setting.CREDENTIALS_FILE_PATH))
    assert not exists(config.get(Setting.CREDENTIALS_FILE_PATH))
    assert not exists(config.get(Setting.INGRESS_TOKEN_FILE_PATH))
    assert not ha.runTemporaryServer()
    ha.init()

    # should run the server, since this is an upgrade
    assert not ha.runTemporaryServer()
    assert exists(config.get(Setting.INGRESS_TOKEN_FILE_PATH))

    ha.init()
    assert not ha.runTemporaryServer()
    assert exists(config.get(Setting.INGRESS_TOKEN_FILE_PATH))


def test_ingress_upgrade_file_exists(time, ha: HaSource, config: Config):
    with open(config.get(Setting.INGRESS_TOKEN_FILE_PATH), "x"):
        pass

    # check the default before init
    assert exists(config.get(Setting.CREDENTIALS_FILE_PATH))
    assert exists(config.get(Setting.INGRESS_TOKEN_FILE_PATH))
    assert not ha.runTemporaryServer()
    ha.init()

    # should run the server, since this is an upgrade
    assert not ha.runTemporaryServer()
    assert exists(config.get(Setting.INGRESS_TOKEN_FILE_PATH))
