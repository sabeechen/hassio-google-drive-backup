from pytest import raises
from ..coordinator import Coordinator
from ..globalinfo import GlobalInfo
from .faketime import FakeTime
from ..exceptions import PleaseWait, NoSnapshot, LogicError
from ..model import CreateOptions
from .helpers import TestSource
from ..snapshots import Snapshot
from ..config import Config
from ..settings import Setting
from datetime import timedelta


def test_enabled(coord: Coordinator, dest):
    dest.setEnabled(True)
    assert coord.enabled()
    dest.setEnabled(False)
    assert not coord.enabled()


def test_sync(coord: Coordinator, global_info: GlobalInfo, time: FakeTime):
    coord.sync()
    assert global_info._syncs == 1
    assert global_info._successes == 1
    assert global_info._last_sync_start == time.now()
    assert len(coord.snapshots()) == 1


def test_blocking(coord: Coordinator, blocker):
    with blocker.block(coord._lock):
        with raises(PleaseWait):
            coord.delete(None, None)
        with raises(PleaseWait):
            coord.sync()
        with raises(PleaseWait):
            coord.uploadSnapshot(None)
        with raises(PleaseWait):
            coord.startSnapshot(None)


def test_new_snapshot(coord: Coordinator, time: FakeTime, source, dest):
    coord.startSnapshot(CreateOptions(time.now(), "Test Name"))
    snapshots = coord.snapshots()
    assert len(snapshots) == 1
    assert snapshots[0].name() == "Test Name"
    assert snapshots[0].getSource(source.name()) is not None
    assert snapshots[0].getSource(dest.name()) is None


def test_sync_error(coord: Coordinator, global_info: GlobalInfo, time: FakeTime, model):
    error = Exception("BOOM")
    old_sync = model.sync
    model.sync = lambda s: doRaise(error)
    coord.sync()
    assert global_info._last_error is error
    assert global_info._last_failure_time == time.now()
    assert global_info._successes == 0
    model.sync = old_sync
    coord.sync()
    assert global_info._last_error is None
    assert global_info._successes == 1
    assert global_info._last_success == time.now()


def doRaise(error):
    raise error


def test_delete(coord: Coordinator, snapshot, source, dest):
    assert snapshot.getSource(source.name()) is not None
    assert snapshot.getSource(dest.name()) is not None
    coord.delete([source.name()], snapshot.slug())
    assert len(coord.snapshots()) == 1
    assert snapshot.getSource(source.name()) is None
    assert snapshot.getSource(dest.name()) is not None
    coord.delete([dest.name()], snapshot.slug())
    assert snapshot.getSource(source.name()) is None
    assert snapshot.getSource(dest.name()) is None
    assert snapshot.isDeleted()
    assert len(coord.snapshots()) == 0

    coord.sync()
    assert len(coord.snapshots()) == 1
    coord.delete([source.name(), dest.name()], coord.snapshots()[0].slug())
    assert len(coord.snapshots()) == 0


def test_delete_errors(coord: Coordinator, source, dest, snapshot):
    with raises(NoSnapshot):
        coord.delete([source.name()], "badslug")
    bad_source = TestSource("bad")
    with raises(NoSnapshot):
        coord.delete([bad_source.name()], snapshot.slug())


def test_retain(coord: Coordinator, source, dest, snapshot):
    assert not snapshot.getSource(source.name()).retained()
    assert not snapshot.getSource(dest.name()).retained()
    coord.retain({
        source.name(): True,
        dest.name(): True
    }, snapshot.slug())
    assert snapshot.getSource(source.name()).retained()
    assert snapshot.getSource(dest.name()).retained()


def test_retain_errors(coord: Coordinator, source, dest, snapshot):
    with raises(NoSnapshot):
        coord.retain({source.name(): True}, "badslug")
    bad_source = TestSource("bad")
    with raises(NoSnapshot):
        coord.delete({bad_source.name(): True}, snapshot.slug())


def test_freshness(coord: Coordinator, source: TestSource, dest: TestSource, snapshot: Snapshot, time: FakeTime):
    assert snapshot.getPurges() == {
        source.name(): False,
        dest.name(): False
    }

    source.setMax(1)
    dest.setMax(1)
    coord.sync()
    assert snapshot.getPurges() == {
        source.name(): True,
        dest.name(): True
    }

    dest.setMax(0)
    coord.sync()
    assert snapshot.getPurges() == {
        source.name(): True,
        dest.name(): False
    }

    source.setMax(0)
    coord.sync()
    assert snapshot.getPurges() == {
        source.name(): False,
        dest.name(): False
    }

    source.setMax(2)
    dest.setMax(2)
    time.advance(days=7)
    coord.sync()
    assert len(coord.snapshots()) == 2
    assert snapshot.getPurges() == {
        source.name(): True,
        dest.name(): True
    }
    assert coord.snapshots()[1].getPurges() == {
        source.name(): False,
        dest.name(): False
    }

    # should refresh on delete
    source.setMax(1)
    dest.setMax(1)
    coord.delete([source.name()], snapshot.slug())
    assert coord.snapshots()[0].getPurges() == {
        dest.name(): True
    }
    assert coord.snapshots()[1].getPurges() == {
        source.name(): True,
        dest.name(): False
    }

    # should update on retain
    coord.retain({dest.name(): True}, snapshot.slug())
    assert coord.snapshots()[0].getPurges() == {
        dest.name(): False
    }
    assert coord.snapshots()[1].getPurges() == {
        source.name(): True,
        dest.name(): True
    }

    # should update on upload
    coord.uploadSnapshot(coord.snapshots()[0].slug())
    assert coord.snapshots()[0].getPurges() == {
        dest.name(): False,
        source.name(): True
    }
    assert coord.snapshots()[1].getPurges() == {
        source.name(): False,
        dest.name(): True
    }


def test_upload(coord: Coordinator, source: TestSource, dest: TestSource, snapshot):
    coord.delete([source.name()], snapshot.slug())
    assert snapshot.getSource(source.name()) is None
    coord.uploadSnapshot(snapshot.slug())
    assert snapshot.getSource(source.name()) is not None

    with raises(LogicError):
        coord.uploadSnapshot(snapshot.slug())

    with raises(NoSnapshot):
        coord.uploadSnapshot("bad slug")

    coord.delete([dest.name()], snapshot.slug())
    with raises(NoSnapshot):
        coord.uploadSnapshot(snapshot.slug())


def test_download(coord: Coordinator, source, dest, snapshot):
    coord.download(snapshot.slug())
    coord.delete([source.name()], snapshot.slug())
    coord.download(snapshot.slug())

    with raises(NoSnapshot):
        coord.download("bad slug")


def test_backoff(coord: Coordinator, model, source: TestSource, dest: TestSource, snapshot, time: FakeTime, simple_config: Config):
    assert coord.check()
    simple_config.override(Setting.DAYS_BETWEEN_SNAPSHOTS, 1)
    simple_config.override(Setting.MAX_SYNC_INTERVAL_SECONDS, 60 * 60 * 6)

    assert coord.nextSyncAttempt() == time.now() + timedelta(hours=6)
    assert not coord.check()
    error = Exception("BOOM")
    old_sync = model.sync
    model.sync = lambda s: doRaise(error)
    coord.sync()

    # first backoff should be 0 seconds
    assert coord.nextSyncAttempt() == time.now()
    assert coord.check()

    # backoff maxes out at 1 hr = 3600 seconds
    for seconds in [10, 20, 40, 80, 160, 320, 640, 1280, 2560, 3600, 3600, 3600]:
        coord.sync()
        assert coord.nextSyncAttempt() == time.now() + timedelta(seconds=seconds)
        assert not coord.check()
        assert not coord.check()
        assert not coord.check()

    # a good sync resets it back to 6 hours from now
    model.sync = old_sync
    coord.sync()
    assert coord.nextSyncAttempt() == time.now() + timedelta(hours=6)
    assert not coord.check()

    # if the next snapshot is less that 6 hours from the last one, that that shoudl be when we sync
    simple_config.override(Setting.DAYS_BETWEEN_SNAPSHOTS, 1.0 / 24.0)
    assert coord.nextSyncAttempt() == time.now() + timedelta(hours=1)
    assert not coord.check()

    time.advance(hours=2)
    assert coord.nextSyncAttempt() == time.now() - timedelta(hours=1)
    assert coord.check()


def test_dest_disabled():
    # TODO: add a test for the next snapshot time when drive is disabled.
    pass


def test_save_creds(coord: Coordinator, source, dest):
    pass
