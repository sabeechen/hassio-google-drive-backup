from typing import Any, Dict

from ..const import SOURCE_HA
from ..exceptions import ensureKey
from ..time import Time
from .snapshots import AbstractSnapshot

HA_KEY_TEXT = "Hass.io's snapshot metadata"


class HASnapshot(AbstractSnapshot):
    """
    Represents a Hass.io snapshot stored locally in Home Assistant
    """

    def __init__(self, data: Dict[str, Any], retained=False):
        super().__init__(
            name=ensureKey('name', data, HA_KEY_TEXT),
            slug=ensureKey('slug', data, HA_KEY_TEXT),
            date=Time.parse(ensureKey('date', data, HA_KEY_TEXT)),
            size=float(ensureKey("size", data, HA_KEY_TEXT)) * 1024 * 1024,
            source=SOURCE_HA,
            snapshotType=ensureKey('type', data, HA_KEY_TEXT),
            version=ensureKey('homeassistant', data, HA_KEY_TEXT),
            protected=ensureKey('protected', data, HA_KEY_TEXT),
            retained=retained,
            uploadable=True,
            details=data)

    def __str__(self) -> str:
        return "<HA: {0} Name: {1} {2}>".format(self.slug(), self.name(), self.date().isoformat())

    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def __repr__(self) -> str:
        return self.__str__()
