from datetime import timedelta
from .durationparser import DurationParser
from .validator import Validator


class DurationAsStringValidator(Validator):
    def __init__(self, name, minimum=None, maximum=None, base_seconds=1, default_as_empty=None):
        super().__init__(name)
        self.min = minimum
        self.max = maximum
        self.base_seconds = base_seconds
        self.default_as_empty = default_as_empty

    def validate(self, value):
        if value is None or (type(value) == str and len(value) == 0):
            return None
        try:
            if type(value) == str:
                if self.default_as_empty is not None and value == "":
                    value = self.default_as_empty
                else:
                    value = DurationParser().parse(value).total_seconds() / self.base_seconds
            value = float(value)
        except ValueError:
            self.raiseForValue(value)

        if self.max is not None and value > self.max:
            self.raiseForValue(value)
        if self.min is not None and value < self.min:
            self.raiseForValue(value)
        return value

    def formatForUi(self, value):
        if self.default_as_empty is not None and value == self.default_as_empty:
            return ""
        else:
            return DurationParser().format(timedelta(seconds=value * self.base_seconds))
