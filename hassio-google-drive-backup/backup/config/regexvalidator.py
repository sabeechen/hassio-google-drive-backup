from .validator import Validator
import re
from ..logger import getLogger

logger = getLogger(__name__)


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
