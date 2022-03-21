from backup.config import DurationAsStringValidator
from backup.exceptions import InvalidConfigurationValue
from datetime import timedelta
import pytest


def test_minimum():
    parser = DurationAsStringValidator("test", minimum=10)
    assert parser.validate("11 seconds") == 11
    assert parser.validate(11) == 11
    with pytest.raises(InvalidConfigurationValue):
        parser.validate("9 seconds")


def test_maximum():
    parser = DurationAsStringValidator("test", maximum=10)
    assert parser.validate("9 seconds") == 9
    assert parser.validate(9) == 9
    with pytest.raises(InvalidConfigurationValue):
        parser.validate("11 seconds")
    assert parser.formatForUi(9) == "9 seconds"


def test_base():
    parser = DurationAsStringValidator("test", base_seconds=60)
    assert parser.validate("60 seconds") == 1
    assert parser.validate(60) == 60
    assert parser.formatForUi(1) == "1 minutes"
