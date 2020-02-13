from .snapshots import AbstractSnapshot
from ..logger import getLogger

logger = getLogger(__name__)


class DummySnapshotSource(AbstractSnapshot):
    def __init__(self, name, date, source, slug, retain=False):
        super().__init__(
            name=name,
            slug=slug,
            date=date,
            size=0,
            source=source,
            snapshotType="dummy",
            version="dummy_version",
            protected=True,
            retained=retain,
            uploadable=True,
            details={})
