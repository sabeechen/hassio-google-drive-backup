from datetime import datetime
from typing import Dict
from ..logger import getLogger

logger = getLogger(__name__)


class CreateOptions(object):
    def __init__(self, when: datetime, name_template: str, retain_sources: Dict[str, bool] = {}, note: str = None):
        self.when: datetime = when
        self.name_template: str = name_template
        self.retain_sources: Dict[str, bool] = retain_sources
        self.note = note
