from backup.config import BytesizeAsStringValidator
from backup.exceptions import InvalidConfigurationValue
import pytest


def test_minimum():
    parser = BytesizeAsStringValidator("test", minimum=10)
    assert parser.validate("11 bytes") == 11
    assert parser.validate(11) == 11
    with pytest.raises(InvalidConfigurationValue):
        parser.validate("9 bytes")


def test_maximum():
    parser = BytesizeAsStringValidator("test", maximum=10)
    assert parser.validate("9 bytes") == 9
    assert parser.validate(9) == 9
    with pytest.raises(InvalidConfigurationValue):
        parser.validate("11 bytes")
    assert parser.formatForUi(9) == "9 B"


def test_ui_format():
    parser = BytesizeAsStringValidator("test")
    assert parser.formatForUi(25) == "25 B"
    assert parser.formatForUi(25 * 1024) == "25 KB"
    assert parser.formatForUi(25 * 1024 * 1024) == "25 MB"
    assert parser.formatForUi(25 * 1024 * 1024 * 1024) == "25 GB"
    assert parser.formatForUi(25 * 1024 * 1024 * 1024 * 1024) == "25 TB"
    assert parser.formatForUi(25 * 1024 * 1024 * 1024 * 1024 * 1024) == "25 PB"
    assert parser.formatForUi(25 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024) == "25 EB"
    assert parser.formatForUi(25 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024) == "25 ZB"
    assert parser.formatForUi(25 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024) == "25 YB"
    assert parser.formatForUi(2000 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024) == "2000 YB"

    assert parser.formatForUi(2.5 * 1024 * 1024) == "2.5 MB"
    assert parser.formatForUi(2.534525 * 1024 * 1024) == "2.534525 MB"
    assert parser.formatForUi(98743.1234 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024) == "98743.1234 YB"


def test_parsing():
    parser = BytesizeAsStringValidator("test")
    assert parser.validate("1 B") == 1
    assert parser.validate("1 b") == 1
    assert parser.validate("1 bytes") == 1
    assert parser.validate("1 byte") == 1
    assert parser.validate("") is None
    assert parser.validate("   ") is None
    assert parser.validate("  5.   bytes   ") == 5
    assert parser.validate("10b") == 10

    assert parser.validate("1 KB") == 1024
    assert parser.validate("1 k") == 1024
    assert parser.validate("1 kb") == 1024
    assert parser.validate("1 kilobytes") == 1024
    assert parser.validate("1 kibibytes") == 1024
    assert parser.validate("1 kibi") == 1024
    assert parser.validate("2.5 KB") == 1024 * 2.5
    assert parser.validate("10k") == 10 * 1024

    assert parser.validate("1 MB") == 1024 * 1024
    assert parser.validate("1 m") == 1024 * 1024
    assert parser.validate("1 mb") == 1024 * 1024
    assert parser.validate("1 megs") == 1024 * 1024
    assert parser.validate("1 mega") == 1024 * 1024
    assert parser.validate("1 megabytes") == 1024 * 1024
    assert parser.validate("1 mebibytes") == 1024 * 1024
    assert parser.validate("10m") == 10 * 1024 * 1024

    assert parser.validate("1 GB") == 1024 * 1024 * 1024
    assert parser.validate("1 g") == 1024 * 1024 * 1024
    assert parser.validate("1 gb") == 1024 * 1024 * 1024
    assert parser.validate("1 gigs") == 1024 * 1024 * 1024
    assert parser.validate("1 gig") == 1024 * 1024 * 1024
    assert parser.validate("1 giga") == 1024 * 1024 * 1024
    assert parser.validate("1 gigabytes") == 1024 * 1024 * 1024
    assert parser.validate("1 gibibytes") == 1024 * 1024 * 1024
    assert parser.validate("10G") == 10 * 1024 * 1024 * 1024

    assert parser.validate("1 TB") == 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 t") == 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 tb") == 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 tera") == 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 tebi") == 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 terabytes") == 1024 * 1024 * 1024 * 1024
    assert parser.validate("10T") == 10 * 1024 * 1024 * 1024 * 1024

    assert parser.validate("1 PB") == 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 p") == 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 pb") == 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 peta") == 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 pebi") == 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 petabytes") == 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("10P") == 10 * 1024 * 1024 * 1024 * 1024 * 1024

    assert parser.validate("1 EB") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 e") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 eb") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 exa") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 exbi") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 exabytes") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("10E") == 10 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024

    assert parser.validate("1 ZB") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 z") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 zb") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 zetta") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 zebi") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 zettabytes") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("10Z") == 10 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024

    assert parser.validate("1 YB") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 y") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 yb") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 yotta") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 yobi") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("1 yottabytes") == 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
    assert parser.validate("10Y") == 10 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
