from .byteformatter import ByteFormatter
from .validator import Validator


class BytesizeAsStringValidator(Validator):
    def __init__(self, name, minimum=None, maximum=None):
        super().__init__(name)
        self.min = minimum
        self.max = maximum

    def validate(self, value):
        if type(value) is str:
            value = value.strip()
        if value is None or (type(value) == str and len(value) == 0):
            return None
        try:
            if type(value) == str:
                value = ByteFormatter().parse(value)
            value = float(value)
        except ValueError:
            self.raiseForValue(value)

        if self.max is not None and value > self.max:
            self.raiseForValue(value)
        if self.min is not None and value < self.min:
            self.raiseForValue(value)
        return value

    def formatForUi(self, value):
        return ByteFormatter().format(value)
