from backup.config import Version


def test_default():
    assert Version.default() == Version.default()
    assert not Version.default() > Version.default()
    assert not Version.default() < Version.default()
    assert not Version.default() != Version.default()
    assert Version.default() >= Version.default()
    assert Version.default() <= Version.default()


def test_version():
    assert Version(1, 2, 3) == Version(1, 2, 3)
    assert Version(1, 2, 3) >= Version(1, 2, 3)
    assert Version(1, 2, 3) <= Version(1, 2, 3)
    assert Version(1, 2, 3) > Version(1, 2)
    assert Version(1) < Version(2)
    assert Version(2) > Version(1)
    assert Version(1) != Version(2)
    assert Version(1, 2) > Version(1)
    assert Version(1) < Version(1, 2)


def test_parse():
    assert Version.parse("1.0") == Version(1, 0)
    assert Version.parse("1.2.3") == Version(1, 2, 3)


def test_parse_staging():
    assert Version.parse("1.0.staging.1") == Version(1, 0, 1)
    assert Version.parse("1.0.staging.1").staging == True
    assert Version.parse("1.0.staging.1") > Version(1.0)
    assert Version.parse("1.2.3") == Version(1, 2, 3)
