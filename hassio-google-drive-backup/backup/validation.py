import re
from abc import ABC, abstractmethod

from .exceptions import InvalidConfigurationValue
from .helpers import strToBool


class Validator(ABC):
    def __init__(self, name):
        self.name = name

    @abstractmethod
    def validate(self, value):
        return True

    def raiseForValue(self, value):
        raise InvalidConfigurationValue(self.name, str(value))


class IntValidator(Validator):
    def __init__(self, name, minimum=None, maximum=None):
        super().__init__(name)
        self.min = minimum
        self.max = maximum

    def validate(self, value):
        if value is None or (type(value) == str and len(value) == 0):
            return None
        try:
            value = int(value)
        except ValueError:
            self.raiseForValue(value)

        if self.max is not None and value > self.max:
            self.raiseForValue(value)
        if self.min is not None and value < self.min:
            self.raiseForValue(value)
        return value


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


class StringValidator(Validator):
    def __init__(self, name):
        super().__init__(name)

    def validate(self, value):
        if value is None or (type(value) == str and len(value) == 0):
            return ""
        return str(value)


class RegexValidator(Validator):
    def __init__(self, name, regex):
        super().__init__(name)
        self.re = re.compile(regex)

    def validate(self, value):
        if value is None or (type(value) == str and len(value) == 0):
            return ""
        value = str(value)
        if not self.re.match(value):
            self.raiseForValue(value)
        return value


class BoolValidator(Validator):
    def __init__(self, name):
        super().__init__(name)

    def validate(self, value):
        if value is None or (type(value) == str and len(value) == 0):
            return None
        return strToBool(value)
