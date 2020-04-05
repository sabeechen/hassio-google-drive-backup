from abc import ABC, abstractmethod

from ..exceptions import InvalidConfigurationValue
from ..logger import getLogger

logger = getLogger(__name__)


class Validator(ABC):
    def __init__(self, name):
        self.name = name

    @abstractmethod
    def validate(self, value):
        return True

    def raiseForValue(self, value):
        raise InvalidConfigurationValue(self.name, str(value))

    def formatForUi(self, value):
        return value
