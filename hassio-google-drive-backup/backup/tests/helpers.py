from datetime import datetime
from io import BytesIO
from ..simulation import SimulatedSource
from threading import Thread, Event
import tarfile
import json

all_folders = [
    "share",
    "ssl",
    "addons/local",
    "homeassistant"
]
all_addons = [
    {
        "name": "Sexy Robots",
        "slug": "sexy_robots",
        "description": "The robots you already know, but sexier. See what they don't want you to see.",
        "version": "0.69",
        "size": 0.0
    },
    {
        "name": "Particle Accelerator",
        "slug": "particla_accel",
        "description": "What CAN'T you do with Home Assistant?",
        "version": "0.5",
        "size": 0.0
    },
    {
        "name": "Empty Addon",
        "slug": "addon_empty",
        "description": "Explore the meaning of the universe by contemplating whats missing.",
        "version": "0.-1",
        "size": 0.0
    }
]


def createSnapshotTar(slug: str, name: str, date: datetime, padSize: int, included_folders=None, included_addons=None, password=None) -> BytesIO:
    snapshot_type = "full"
    if included_folders:
        folders = included_folders.copy()
    else:
        folders = all_folders.copy()

    if included_addons:
        snapshot_type = "partial"
        addons = []
        for addon in all_addons:
            if addon['slug'] in included_addons:
                addons.append(addon)
    else:
        addons = all_addons.copy()

    snapshot_info = {
        "slug": slug,
        "name": name,
        "date": date.isoformat(),
        "type": snapshot_type,
        "protected": password is not None,
        "homeassistant": {
            "ssl": True,
            "watchdog": True,
            "port": 8123,
            "wait_boot": 600,
            "boot": True,
            "version": "0.92.2",
            "refresh_token": "fake_token"
        },
        "folders": folders,
        "addons": addons,
        "repositories": [
            "https://github.com/hassio-addons/repository"
        ]
    }
    stream = BytesIO()
    tar = tarfile.open(fileobj=stream, mode="w")
    add(tar, "snapshot.json", BytesIO(json.dumps(snapshot_info).encode()))
    add(tar, "padding.dat", getTestStream(padSize))
    tar.close()
    stream.seek(0)
    stream.size = lambda: len(stream.getbuffer())
    return stream


def add(tar, name, stream):
    info = tarfile.TarInfo(name)
    info.size = len(stream.getbuffer())
    stream.seek(0)
    tar.addfile(info, stream)


def parseSnapshotInfo(stream: BytesIO):
    with tarfile.open(fileobj=stream, mode="r") as tar:
        info = tar.getmember("snapshot.json")
        with tar.extractfile(info) as f:
            snapshot_data = json.load(f)
            snapshot_data['size'] = float(round(len(stream.getbuffer()) / 1024.0 / 1024.0, 2))
            snapshot_data['version'] = 'dev'
            return snapshot_data


def getTestStream(size: int):
    """
    Produces a stream of repeating prime sequences to avoid accidental repetition
    """
    arr = bytearray()
    while True:
        for prime in [4759, 4783, 4787, 4789, 4793, 4799, 4801, 4813, 4817, 4831, 4861, 4871, 4877, 4889, 4903, 4909, 4919, 4931, 4933, 4937]:
            for x in range(prime):
                if len(arr) < size:
                    arr.append(x % 255)
                else:
                    break
            if len(arr) >= size:
                break
        if len(arr) >= size:
            break
    return BytesIO(arr)


def compareStreams(left, right):
    while True:
        from_left = left.read(1024 * 1024)
        from_right = right.read(1024 * 1024)
        if len(from_left) == 0:
            assert len(from_right) == 0
            break
        if from_left != from_right:
            print("break!")
        assert from_left == from_right


class LockBlocker():
    def __init__(self):
        self._event = Event()
        self._thread = Thread(target=self._doBlock, name="Blocker Thread")
        self._thread.setDaemon(True)
        self._lock = None

    def block(self, lock):
        self._lock = lock
        return self

    def _doBlock(self):
        with self._lock:
            self._event.wait()

    def __enter__(self):
        if self._lock is None:
            raise Exception("Lock was not configured")
        self._thread.start()

    def __exit__(self, a, b, c):
        self._event.set()
        self._thread.join()
        self._event.clear()


class TestSource(SimulatedSource):
    def __init__(self, name):
        super().__init__(name)

    def reset(self):
        self.saved = []
        self.deleted = []
        self.created = []

    def assertThat(self, created=0, deleted=0, saved=0, current=0):
        assert len(self.saved) == saved
        assert len(self.deleted) == deleted
        assert len(self.created) == created
        assert len(self.current) == current
        return self

    def assertUnchanged(self):
        self.assertThat(current=len(self.current))
        return self
