from .validator import Validator
from ..logger import getLogger

logger = getLogger(__name__)


class ListValidator(Validator):
    def __init__(self, name, values):
        super().__init__(name)
        self.values = values

    def validate(self, value):
        if value not in self.values:
            self.raiseForValue(value)
        return value
