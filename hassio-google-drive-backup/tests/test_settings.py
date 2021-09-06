from backup.config import Setting, addon_config, _CONFIG


def test_defaults():
    # all settings should have a default
    for setting in Setting:
        if setting is not Setting.DEBUGGER_PORT:
            assert setting.default() is not None, setting.value + " has no default"

    # all defaults shoudl have a validator
    for setting in Setting:
        assert setting.validator() is not None, setting.value + " has no validator"

    # all defaults values should be valid and validate to their own value
    for setting in Setting:
        assert setting.validator().validate(setting.default()) == setting.default()

    # All settings in the default config should have the exact same parse expression
    for setting in Setting:
        if setting.value in addon_config["schema"]:
            if setting != Setting.GENERATIONAL_DAY_OF_WEEK:
                assert _CONFIG[setting] == addon_config["schema"][setting.value], setting.value
