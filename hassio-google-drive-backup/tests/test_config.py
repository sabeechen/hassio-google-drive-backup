import os
from pytest import raises

from backup.model import GenConfig
from backup.config import Config, Setting
from backup.exceptions import InvalidConfigurationValue


def test_validate_empty():
    config = Config()
    assert config.validate({}) == defaultAnd()


def test_validate_int():
    assert Config().validate({'max_backups_in_ha': 5}) == defaultAnd(
        {Setting.MAX_BACKUPS_IN_HA: 5})
    assert Config().validate({'max_backups_in_ha': 5.0}) == defaultAnd(
        {Setting.MAX_BACKUPS_IN_HA: 5})
    assert Config().validate({'max_backups_in_ha': "5"}) == defaultAnd(
        {Setting.MAX_BACKUPS_IN_HA: 5})

    with raises(InvalidConfigurationValue):
        Config().validate({'max_backups_in_ha': -2})


def test_validate_float():
    setting = Setting.DAYS_BETWEEN_BACKUPS
    assert Config().validate({setting: 5}) == defaultAnd({setting: 5})
    assert Config().validate({setting.key(): 5}) == defaultAnd({setting: 5})
    assert Config().validate({setting: 5.0}) == defaultAnd({setting: 5})
    assert Config().validate({setting: "5"}) == defaultAnd({setting: 5})

    with raises(InvalidConfigurationValue):
        Config().validate({'days_between_backups': -1})


def test_validate_bool():
    setting = Setting.SEND_ERROR_REPORTS
    assert Config().validate({setting: True}) == defaultAnd({setting: True})
    assert Config().validate({setting: False}) == defaultAnd({setting: False})
    assert Config().validate({setting: "true"}) == defaultAnd({setting: True})
    assert Config().validate({setting: "false"}) == defaultAnd({setting: False})
    assert Config().validate({setting: "1"}) == defaultAnd({setting: True})
    assert Config().validate({setting: "0"}) == defaultAnd({setting: False})
    assert Config().validate({setting: "yes"}) == defaultAnd({setting: True})
    assert Config().validate({setting: "no"}) == defaultAnd({setting: False})
    assert Config().validate({setting: "on"}) == defaultAnd({setting: True})
    assert Config().validate({setting: "off"}) == defaultAnd({setting: False})


def test_validate_string():
    assert Config().validate({Setting.BACKUP_NAME: True}) == defaultAnd({Setting.BACKUP_NAME: "True"})
    assert Config().validate({Setting.BACKUP_NAME: False}) == defaultAnd({Setting.BACKUP_NAME: "False"})
    assert Config().validate({Setting.BACKUP_NAME: "true"}) == defaultAnd({Setting.BACKUP_NAME: "true"})
    assert Config().validate({Setting.BACKUP_NAME: "false"}) == defaultAnd({Setting.BACKUP_NAME: "false"})
    assert Config().validate({Setting.BACKUP_NAME: "1"}) == defaultAnd({Setting.BACKUP_NAME: "1"})
    assert Config().validate({Setting.BACKUP_NAME: "0"}) == defaultAnd({Setting.BACKUP_NAME: "0"})
    assert Config().validate({Setting.BACKUP_NAME: "yes"}) == defaultAnd({Setting.BACKUP_NAME: "yes"})
    assert Config().validate({Setting.BACKUP_NAME: "no"}) == defaultAnd({Setting.BACKUP_NAME: "no"})


def test_validate_url():
    assert Config().validate({Setting.SUPERVISOR_URL: True}) == defaultAnd(
        {Setting.SUPERVISOR_URL: "True"})
    assert Config().validate({Setting.SUPERVISOR_URL: False}) == defaultAnd(
        {Setting.SUPERVISOR_URL: "False"})
    assert Config().validate({Setting.SUPERVISOR_URL: "true"}) == defaultAnd(
        {Setting.SUPERVISOR_URL: "true"})
    assert Config().validate({Setting.SUPERVISOR_URL: "false"}) == defaultAnd(
        {Setting.SUPERVISOR_URL: "false"})
    assert Config().validate({Setting.SUPERVISOR_URL: "1"}) == defaultAnd(
        {Setting.SUPERVISOR_URL: "1"})
    assert Config().validate({Setting.SUPERVISOR_URL: "0"}) == defaultAnd(
        {Setting.SUPERVISOR_URL: "0"})
    assert Config().validate({Setting.SUPERVISOR_URL: "yes"}) == defaultAnd(
        {Setting.SUPERVISOR_URL: "yes"})
    assert Config().validate({Setting.SUPERVISOR_URL: "no"}) == defaultAnd(
        {Setting.SUPERVISOR_URL: "no"})


def test_validate_regex():
    assert Config().validate({Setting.DRIVE_IPV4: "192.168.1.1"}) == defaultAnd(
        {Setting.DRIVE_IPV4: "192.168.1.1"})
    with raises(InvalidConfigurationValue):
        Config().validate({Setting.DRIVE_IPV4: -1})
    with raises(InvalidConfigurationValue):
        Config().validate({Setting.DRIVE_IPV4: "192.168.1"})


def test_remove_ssl():
    assert Config().validate({Setting.USE_SSL: True}) == defaultAnd({Setting.USE_SSL: True})
    assert Config().validate({Setting.USE_SSL: False}) == defaultAnd()
    assert Config().validate({
        Setting.USE_SSL: False,
        Setting.CERTFILE: "removed",
        Setting.KEYFILE: 'removed'
    }) == defaultAnd()
    assert Config().validate({
        Setting.USE_SSL: True,
        Setting.CERTFILE: "kept",
        Setting.KEYFILE: 'kept'
    }) == defaultAnd({
        Setting.USE_SSL: True,
        Setting.CERTFILE: "kept",
        Setting.KEYFILE: 'kept'
    })


def test_send_error_reports():
    assert Config().validate({Setting.SEND_ERROR_REPORTS: False}) == defaultAnd(
        {Setting.SEND_ERROR_REPORTS: False})
    assert Config().validate({Setting.SEND_ERROR_REPORTS: True}) == defaultAnd(
        {Setting.SEND_ERROR_REPORTS: True})
    assert Config().validate(
        {Setting.SEND_ERROR_REPORTS: None}) == defaultAnd()


def test_unrecognized_values_filter():
    assert Config().validate({'blah': "bloo"}) == defaultAnd()


def test_removes_defaults():
    assert Config().validate(
        {Setting.BACKUP_TIME_OF_DAY: ""}) == defaultAnd()


def defaultAnd(config={}):
    ret = {
        Setting.DAYS_BETWEEN_BACKUPS: 3,
        Setting.MAX_BACKUPS_IN_HA: 4,
        Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE: 4
    }
    ret.update(config)
    return (ret, False)


def test_GenerationalConfig() -> None:
    assert Config().getGenerationalConfig() is None

    assert Config().override(Setting.GENERATIONAL_DAYS, 5).getGenerationalConfig() == GenConfig(days=5)
    assert Config().override(Setting.GENERATIONAL_WEEKS, 3).getGenerationalConfig() == GenConfig(days=1, weeks=3)
    assert Config().override(Setting.GENERATIONAL_MONTHS, 3).getGenerationalConfig() == GenConfig(days=1, months=3)
    assert Config().override(Setting.GENERATIONAL_YEARS, 3).getGenerationalConfig() == GenConfig(days=1, years=3)
    assert Config().override(Setting.GENERATIONAL_DELETE_EARLY, True).override(
        Setting.GENERATIONAL_DAYS, 2).getGenerationalConfig() == GenConfig(days=2, aggressive=True)
    assert Config().override(Setting.GENERATIONAL_DAYS, 1).override(
        Setting.GENERATIONAL_DAY_OF_YEAR, 3).getGenerationalConfig() == GenConfig(days=1, day_of_year=3)
    assert Config().override(Setting.GENERATIONAL_DAYS, 1).override(
        Setting.GENERATIONAL_DAY_OF_MONTH, 3).getGenerationalConfig() == GenConfig(days=1, day_of_month=3)
    assert Config().override(Setting.GENERATIONAL_DAYS, 1).override(
        Setting.GENERATIONAL_DAY_OF_WEEK, "tue").getGenerationalConfig() == GenConfig(days=1, day_of_week="tue")

    assert Config().override(Setting.GENERATIONAL_DAY_OF_MONTH, 3).override(Setting.GENERATIONAL_DAY_OF_WEEK, "tue").override(Setting.GENERATIONAL_DAY_OF_YEAR, "4").getGenerationalConfig() is None


def test_from_environment():
    assert Config.fromEnvironment().get(Setting.PORT) != 1000

    os.environ["PORT"] = str(1000)
    assert Config.fromEnvironment().get(Setting.PORT) == 1000

    del os.environ["PORT"]
    assert Config.fromEnvironment().get(Setting.PORT) != 1000

    os.environ["port"] = str(1000)
    assert Config.fromEnvironment().get(Setting.PORT) == 1000


def test_config_upgrade():
    # Test specifying one value
    config = Config()
    config.update({Setting.DEPRECTAED_BACKUP_TIME_OF_DAY: "00:01"})
    assert (config.getAllConfig(), False) == defaultAnd({
        Setting.BACKUP_TIME_OF_DAY: "00:01",
        Setting.CALL_BACKUP_SNAPSHOT: True
    })
    assert config.mustSaveUpgradeChanges()

    # Test specifying multiple values
    config = Config()
    config.update({
        Setting.DEPRECTAED_MAX_BACKUPS_IN_GOOGLE_DRIVE: 21,
        Setting.DEPRECTAED_MAX_BACKUPS_IN_HA: 20,
        Setting.DEPRECATED_BACKUP_PASSWORD: "boop"
    })
    assert config.getAllConfig() == defaultAnd({
        Setting.MAX_BACKUPS_IN_HA: 20,
        Setting.MAX_BACKUPS_IN_GOOGLE_DRIVE: 21,
        Setting.BACKUP_PASSWORD: "boop",
        Setting.CALL_BACKUP_SNAPSHOT: True
    })[0]
    assert config.mustSaveUpgradeChanges()

    # test specifying value that don't get upgraded
    config = Config()
    config.update({Setting.EXCLUDE_ADDONS: "test"})
    assert config.getAllConfig() == defaultAnd({
        Setting.EXCLUDE_ADDONS: "test"
    })[0]
    assert not config.mustSaveUpgradeChanges()

    # Test specifying both
    config = Config()
    config.update({
        Setting.DEPRECTAED_BACKUP_TIME_OF_DAY: "00:01",
        Setting.EXCLUDE_ADDONS: "test"
    })
    assert config.getAllConfig() == defaultAnd({
        Setting.BACKUP_TIME_OF_DAY: "00:01",
        Setting.EXCLUDE_ADDONS: "test",
        Setting.CALL_BACKUP_SNAPSHOT: True
    })[0]
    assert config.mustSaveUpgradeChanges()


def test_overwrite_on_upgrade():
    config = Config()
    config.update({
        Setting.DEPRECTAED_MAX_BACKUPS_IN_HA: 5,
        Setting.MAX_BACKUPS_IN_HA: 6
    })
    assert (config.getAllConfig(), False) == defaultAnd({
        Setting.MAX_BACKUPS_IN_HA: 6,
        Setting.CALL_BACKUP_SNAPSHOT: True
    })
    assert config.mustSaveUpgradeChanges()

    config = Config()
    config.update({
        Setting.MAX_BACKUPS_IN_HA: 6,
        Setting.DEPRECTAED_MAX_BACKUPS_IN_HA: 5
    })
    assert (config.getAllConfig(), False) == defaultAnd({
        Setting.MAX_BACKUPS_IN_HA: 6,
        Setting.CALL_BACKUP_SNAPSHOT: True
    })
    assert config.mustSaveUpgradeChanges()

    config = Config()
    config.update({
        Setting.MAX_BACKUPS_IN_HA: 6,
        Setting.DEPRECTAED_MAX_BACKUPS_IN_HA: 4
    })
    assert (config.getAllConfig(), False) == defaultAnd({
        Setting.MAX_BACKUPS_IN_HA: 6,
        Setting.CALL_BACKUP_SNAPSHOT: True
    })
    assert config.mustSaveUpgradeChanges()


def test_overwrite_on_upgrade_default_value():
    # Test specifying one value
    config = Config()
    config.update({
        Setting.DEPRECTAED_MAX_BACKUPS_IN_HA: Setting.MAX_BACKUPS_IN_HA.default() + 1,
        Setting.MAX_BACKUPS_IN_HA: Setting.MAX_BACKUPS_IN_HA.default()
    })
    assert (config.getAllConfig(), False) == defaultAnd({
        Setting.MAX_BACKUPS_IN_HA: Setting.MAX_BACKUPS_IN_HA.default() + 1,
        Setting.CALL_BACKUP_SNAPSHOT: True
    })
    assert config.mustSaveUpgradeChanges()

    config = Config()
    config.update({
        Setting.MAX_BACKUPS_IN_HA: Setting.MAX_BACKUPS_IN_HA.default(),
        Setting.DEPRECTAED_MAX_BACKUPS_IN_HA: Setting.MAX_BACKUPS_IN_HA.default() + 1
    })
    assert (config.getAllConfig(), False) == defaultAnd({
        Setting.MAX_BACKUPS_IN_HA: Setting.MAX_BACKUPS_IN_HA.default() + 1,
        Setting.CALL_BACKUP_SNAPSHOT: True
    })
    assert config.mustSaveUpgradeChanges()


def test_empty_colors():
    # Test specifying one value
    config = Config()
    config.update({Setting.BACKGROUND_COLOR: "", Setting.ACCENT_COLOR: ""})
    assert config.get(Setting.BACKGROUND_COLOR) == Setting.BACKGROUND_COLOR.default()
    assert config.get(Setting.ACCENT_COLOR) == Setting.ACCENT_COLOR.default()


def getGenConfig(update):
    base = {
        "days": 1,
        "weeks": 0,
        "months": 0,
        "years": 0,
        "day_of_week": "mon",
        "day_of_year": 1,
        "day_of_month": 1
    }
    base.update(update)
    return base
