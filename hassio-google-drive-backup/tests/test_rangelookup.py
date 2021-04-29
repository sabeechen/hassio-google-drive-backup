from backup.util import RangeLookup


def test_lookup():
    data = [1, 3, 5]
    lookup = RangeLookup(data, lambda x: x)
    assert list(lookup.matches(-1, 0)) == []
    assert list(lookup.matches(6, 7)) == []
    assert list(lookup.matches(2, 2)) == []
    assert list(lookup.matches(4, 4)) == []
    assert list(lookup.matches(6, 6)) == []

    assert list(lookup.matches(0, 6)) == [1, 3, 5]
    assert list(lookup.matches(1, 5)) == [1, 3, 5]

    assert list(lookup.matches(1, 3)) == [1, 3]
    assert list(lookup.matches(0, 4)) == [1, 3]
    assert list(lookup.matches(3, 5)) == [3, 5]
    assert list(lookup.matches(2, 6)) == [3, 5]

    assert list(lookup.matches(0, 2)) == [1]
    assert list(lookup.matches(1, 1)) == [1]
    assert list(lookup.matches(3, 3)) == [3]
    assert list(lookup.matches(2, 4)) == [3]
    assert list(lookup.matches(5, 5)) == [5]
    assert list(lookup.matches(4, 5)) == [5]
