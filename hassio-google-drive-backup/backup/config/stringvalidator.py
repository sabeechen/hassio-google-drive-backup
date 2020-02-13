from .validator import Validator
from ..logger import getLogger

logger = getLogger(__name__)


class StringValidator(Validator):
    def __init__(self, name):
        super().__init__(name)

    def validate(self, value):
        if value is None or (type(value) == str and len(value) == 0):
            return ""
        return str(value)
