from abc import ABC, abstractmethod

from ..exceptions import InvalidConfigurationValue


class Validator(ABC):
    def __init__(self, name):
        self.name = name

    @abstractmethod
    def validate(self, value):
        return True

    def raiseForValue(self, value):
        raise InvalidConfigurationValue(self.name, str(value))
