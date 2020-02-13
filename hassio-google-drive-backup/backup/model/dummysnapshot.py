from .snapshots import Snapshot
from .dummysnapshotsource import DummySnapshotSource
from ..logger import getLogger

logger = getLogger(__name__)


class DummySnapshot(Snapshot):
    def __init__(self, name, date, source, slug, size=0):
        super().__init__(None)
        self._size = size
        self.addSource(DummySnapshotSource(name, date, source, slug))

    def size(self):
        return self._size
