from datetime import timedelta
from .durationparser import DurationParser
from .validator import Validator


class DurationAsSecondsValidator(Validator):
    def __init__(self, name, minimum=None, maximum=None):
        super().__init__(name)
        self.min = minimum
        self.max = maximum

    def validate(self, value):
        if value is None or (type(value) == str and len(value) == 0):
            return None
        try:
            if type(value) == str:
                value = DurationParser().parse(value).total_seconds()
            value = int(value)
        except ValueError:
            self.raiseForValue(value)

        if self.max is not None and value > self.max:
            self.raiseForValue(value)
        if self.min is not None and value < self.min:
            self.raiseForValue(value)
        return value

    def formatForUi(self, value):
        return DurationParser().format(timedelta(seconds=value))
