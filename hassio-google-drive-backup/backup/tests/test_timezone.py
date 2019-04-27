from ..helpers import parseDateTime


def test_parse(mocker) -> None:
    time = parseDateTime("1985-12-06 01:01:01.0001")
    assert str(time) == "1985-12-06 01:01:01.000100+00:00"

    time = parseDateTime("1985-12-06 01:01:01.0001+01:00")
    assert str(time) == "1985-12-06 01:01:01.000100+00:00"
