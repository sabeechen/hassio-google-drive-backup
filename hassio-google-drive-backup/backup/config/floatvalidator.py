from .validator import Validator
from ..logger import getLogger

logger = getLogger(__name__)


class FloatValidator(Validator):
    def __init__(self, name, minimum=None, maximum=None):
        super().__init__(name)
        self.min = minimum
        self.max = maximum

    def validate(self, value):
        if value is None or (type(value) == str and len(value) == 0):
            return None
        try:
            value = float(value)
        except ValueError:
            self.raiseForValue(value)

        if self.max is not None and value > self.max:
            self.raiseForValue(value)
        if self.min is not None and value < self.min:
            self.raiseForValue(value)
        return value
