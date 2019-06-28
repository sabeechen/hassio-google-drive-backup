from .logbase import LogBase
from .model import SnapshotSource, Model, CreateOptions
from .snapshots import Snapshot, DummySnapshotSource
from typing import Dict
from io import IOBase
from datetime import datetime
from .const import SOURCE_GOOGLE_DRIVE, SOURCE_HA
from .settings import Setting
from .time import Time, FakeTime
from .globalinfo import GlobalInfo
from .snapshotname import SnapshotName


class SimulatedSource(SnapshotSource[DummySnapshotSource]):
    def __init__(self, name):
        self._name = name
        self.current: Dict[str, DummySnapshotSource] = {}
        self.saved = []
        self.deleted = []
        self.created = []
        self._enabled = True
        self._upload = True
        self.index = 0
        self.max = 0
        self.snapshot_name = SnapshotName()
        self.host_info = {}
        self.snapshot_type = "Full"

    def setEnabled(self, value):
        self._enabled = value
        return self

    def setUpload(self, value):
        self._upload = value
        return self

    def upload(self):
        return self._upload

    def setMax(self, count):
        self.max = count
        return self

    def maxCount(self) -> None:
        return self.max

    def insert(self, name, date, slug=None, retain=False):
        if slug is None:
            slug = name
        new_snapshot = DummySnapshotSource(
            name,
            date,
            self._name,
            slug)
        self.current[new_snapshot.slug()] = new_snapshot
        return new_snapshot

    def name(self) -> str:
        return self._name

    def enabled(self) -> bool:
        return self._enabled

    def nameSetup(self, type, host_info):
        self.snapshot_type = type
        self.host_info = host_info

    def create(self, options: CreateOptions) -> DummySnapshotSource:
        assert self.enabled
        new_snapshot = DummySnapshotSource(
            # TODO: time shoudl be local
            self.snapshot_name.resolve(self.snapshot_type, options.name_template, options.when, self.host_info),
            options.when,
            self._name,
            "{0}slug{1}".format(self._name, self.index))
        self.index += 1
        self.current[new_snapshot.slug()] = new_snapshot
        self.created.append(new_snapshot)
        return new_snapshot

    def get(self) -> Dict[str, DummySnapshotSource]:
        assert self.enabled
        return self.current

    def delete(self, snapshot: Snapshot):
        assert self.enabled
        assert snapshot.getSource(self._name) is not None
        assert snapshot.getSource(self._name).source() is self._name
        assert snapshot.slug() in self.current
        slug = snapshot.slug()
        self.deleted.append(snapshot.getSource(self._name))
        snapshot.removeSource(self._name)
        del self.current[slug]

    def save(self, snapshot: Snapshot, bytes: IOBase = None) -> DummySnapshotSource:
        assert self.enabled
        assert snapshot.slug() not in self.current
        new_snapshot = DummySnapshotSource(snapshot.name(), snapshot.date(), self._name, snapshot.slug())
        snapshot.addSource(new_snapshot)
        self.current[new_snapshot.slug()] = new_snapshot
        self.saved.append(new_snapshot)
        return new_snapshot

    def read(self, snapshot: DummySnapshotSource) -> IOBase:
        assert self.enabled
        return None

    def retain(self, snapshot: DummySnapshotSource, retain: bool) -> None:
        assert self.enabled
        snapshot.getSource(self.name()).setRetained(retain)


class Simulation(LogBase):
    def __init(self, config, time: Time):
        self.config = config
        self.real_time = time

    def simulate(self, snapshots, now: datetime, until: datetime):
        source = SimulatedSource(SOURCE_HA)
        source.setEnabled(True)
        source.setMax(self.config.get(Setting.MAX_SNAPSHOTS_IN_HASSIO))

        dest = SimulatedSource(SOURCE_GOOGLE_DRIVE)
        dest.setEnabled(True)
        dest.setMax(self.config.get(Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE))
        sources = [source, dest]
        for snapshot in snapshots:
            for source in sources:
                exists = snapshot.getSource(source.name())
                if exists:
                    source.insert(exists.name(), exists.date(), exists.slug(), exists.retained())
        fake_time = FakeTime(now)
        model = Model(self.config, fake_time, source, dest, GlobalInfo(fake_time))
        while fake_time.now() <= until:
            model.sync()
            next = model.nextSnapshot(fake_time.now())
            if not next or next <= fake_time.now():
                break
            else:
                fake_time.setNow(next)
