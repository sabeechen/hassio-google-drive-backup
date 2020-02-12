from .validator import Validator


class StringValidator(Validator):
    def __init__(self, name):
        super().__init__(name)

    def validate(self, value):
        if value is None or (type(value) == str and len(value) == 0):
            return ""
        return str(value)
