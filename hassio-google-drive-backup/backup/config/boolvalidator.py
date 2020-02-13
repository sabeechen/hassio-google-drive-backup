from .validator import Validator
from ..logger import getLogger

logger = getLogger(__name__)


class BoolValidator(Validator):
    def __init__(self, name):
        super().__init__(name)

    def validate(self, value):
        if value is None or (type(value) == str and len(value) == 0):
            return None
        return BoolValidator.strToBool(value)

    @classmethod
    def strToBool(cls, value) -> bool:
        return str(value).lower() in ['true', 't', 'on', 'yes', 'y', '1', 'hai', 'si', 'omgyesplease']
