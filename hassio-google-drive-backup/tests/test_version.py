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
    assert Version.parse("1.0.staging.1").staging
    assert Version.parse("1.0.staging.1") > Version(1.0)
    assert Version.parse("1.2.3") == Version(1, 2, 3)


def test_junk_strings():
    assert Version.parse("1-.2.3.1") == Version(1, 2, 3, 1)
    assert Version.parse("ignore-1.2.3.1") == Version(1, 2, 3, 1)
    assert Version.parse("1.2.ignore.this.text.3.and...andhere.too.1") == Version(1, 2, 3, 1)


def test_broken_versions():
    assert Version.parse("") == Version.default()
    assert Version.parse(".") == Version.default()
    assert Version.parse("empty") == Version.default()
    assert Version.parse("no.version.here") == Version.default()
