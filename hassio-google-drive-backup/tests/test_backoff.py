from pytest import fixture, raises

from backup.util import Backoff


@fixture
def error():
    return Exception()


def test_defaults(error):
    backoff = Backoff()
    assert backoff.backoff(error) == 2
    assert backoff.backoff(error) == 4
    assert backoff.backoff(error) == 8
    assert backoff.backoff(error) == 16
    assert backoff.backoff(error) == 32
    assert backoff.backoff(error) == 64
    assert backoff.backoff(error) == 128
    assert backoff.backoff(error) == 256
    assert backoff.backoff(error) == 512
    assert backoff.backoff(error) == 1024
    assert backoff.backoff(error) == 2048

    for x in range(10000):
        assert backoff.backoff(error) == 3600


def test_max(error):
    backoff = Backoff(max=500)
    assert backoff.backoff(error) == 2
    assert backoff.backoff(error) == 4
    assert backoff.backoff(error) == 8
    assert backoff.backoff(error) == 16
    assert backoff.backoff(error) == 32
    assert backoff.backoff(error) == 64
    assert backoff.backoff(error) == 128
    assert backoff.backoff(error) == 256

    for x in range(10000):
        assert backoff.backoff(error) == 500


def test_initial(error):
    backoff = Backoff(initial=0)
    assert backoff.backoff(error) == 0
    assert backoff.backoff(error) == 2
    assert backoff.backoff(error) == 4
    assert backoff.backoff(error) == 8
    assert backoff.backoff(error) == 16
    assert backoff.backoff(error) == 32
    assert backoff.backoff(error) == 64
    assert backoff.backoff(error) == 128
    assert backoff.backoff(error) == 256
    assert backoff.backoff(error) == 512
    assert backoff.backoff(error) == 1024
    assert backoff.backoff(error) == 2048

    for x in range(10000):
        assert backoff.backoff(error) == 3600


def test_attempts(error):
    backoff = Backoff(attempts=5)
    assert backoff.backoff(error) == 2
    assert backoff.backoff(error) == 4
    assert backoff.backoff(error) == 8
    assert backoff.backoff(error) == 16
    assert backoff.backoff(error) == 32

    for x in range(5):
        with raises(type(error)):
            backoff.backoff(error)


def test_start(error):
    backoff = Backoff(base=10)
    assert backoff.backoff(error) == 10
    assert backoff.backoff(error) == 20
    assert backoff.backoff(error) == 40
    assert backoff.backoff(error) == 80


def test_realistic(error):
    backoff = Backoff(base=5, initial=0, exp=1.5, attempts=5)
    assert backoff.backoff(error) == 0
    assert backoff.backoff(error) == 5
    assert backoff.backoff(error) == 5 * 1.5
    assert backoff.backoff(error) == 5 * (1.5**2)
    assert backoff.backoff(error) == 5 * (1.5**3)
    for x in range(5):
        with raises(type(error)):
            backoff.backoff(error)


def test_maxOut(error):
    backoff = Backoff(base=10, max=100)
    assert backoff.backoff(error) == 10
    assert backoff.backoff(error) == 20
    backoff.maxOut()
    assert backoff.backoff(error) == 100
    assert backoff.backoff(error) == 100
    backoff.reset()
    assert backoff.backoff(error) == 10
