from ..settings import Setting


# TODO: need a test to verify we ask for error reports when it isn't set


def test_defaults():
    # all settings should have a default
    for setting in Setting:
        assert setting.default() is not None, setting.value + " has no default"

    # all defaults shoudl have a validator
    for setting in Setting:
        assert setting.validator() is not None, setting.value + " has no validator"

    # all defaults values should be valid and validate to their own value
    for setting in Setting:
        assert setting.validator().validate(setting.default()) == setting.default()
