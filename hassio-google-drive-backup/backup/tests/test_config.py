from pytest import raises
from ..exceptions import InvalidConfigurationValue
from ..config import Config, DEFAULTS
from os.path import abspath, join
import json


def test_validate_empty():
    config = Config()
    assert config.validate({}) == defaultAnd()


def test_validate_int():
    assert Config().validate({'max_snapshots_in_hassio': 5}) == defaultAnd({'max_snapshots_in_hassio': 5})
    assert Config().validate({'max_snapshots_in_hassio': 5.0}) == defaultAnd({'max_snapshots_in_hassio': 5})
    assert Config().validate({'max_snapshots_in_hassio': "5"}) == defaultAnd({'max_snapshots_in_hassio': 5})

    with raises(InvalidConfigurationValue):
        Config().validate({'max_snapshots_in_hassio': -1})


def test_validate_float():
    assert Config().validate({'days_between_snapshots': 5}) == defaultAnd({'days_between_snapshots': 5})
    assert Config().validate({'days_between_snapshots': 5.0}) == defaultAnd({'days_between_snapshots': 5})
    assert Config().validate({'days_between_snapshots': "5"}) == defaultAnd({'days_between_snapshots': 5})

    with raises(InvalidConfigurationValue):
        Config().validate({'days_between_snapshots': -1})


def test_validate_bool():
    assert Config().validate({'send_error_reports': True}) == defaultAnd({'send_error_reports': True})
    assert Config().validate({'send_error_reports': False}) == defaultAnd({'send_error_reports': False})
    assert Config().validate({'send_error_reports': "true"}) == defaultAnd({'send_error_reports': True})
    assert Config().validate({'send_error_reports': "false"}) == defaultAnd({'send_error_reports': False})
    assert Config().validate({'send_error_reports': "1"}) == defaultAnd({'send_error_reports': True})
    assert Config().validate({'send_error_reports': "0"}) == defaultAnd({'send_error_reports': False})
    assert Config().validate({'send_error_reports': "yes"}) == defaultAnd({'send_error_reports': True})
    assert Config().validate({'send_error_reports': "no"}) == defaultAnd({'send_error_reports': False})
    assert Config().validate({'send_error_reports': "on"}) == defaultAnd({'send_error_reports': True})
    assert Config().validate({'send_error_reports': "off"}) == defaultAnd({'send_error_reports': False})


def test_validate_string():
    assert Config().validate({'snapshot_name': True}) == defaultAnd({'snapshot_name': "True"})
    assert Config().validate({'snapshot_name': False}) == defaultAnd({'snapshot_name': "False"})
    assert Config().validate({'snapshot_name': "true"}) == defaultAnd({'snapshot_name': "true"})
    assert Config().validate({'snapshot_name': "false"}) == defaultAnd({'snapshot_name': "false"})
    assert Config().validate({'snapshot_name': "1"}) == defaultAnd({'snapshot_name': "1"})
    assert Config().validate({'snapshot_name': "0"}) == defaultAnd({'snapshot_name': "0"})
    assert Config().validate({'snapshot_name': "yes"}) == defaultAnd({'snapshot_name': "yes"})
    assert Config().validate({'snapshot_name': "no"}) == defaultAnd({'snapshot_name': "no"})


def test_validate_url():
    assert Config().validate({'hassio_base_url': True}) == defaultAnd({'hassio_base_url': "True"})
    assert Config().validate({'hassio_base_url': False}) == defaultAnd({'hassio_base_url': "False"})
    assert Config().validate({'hassio_base_url': "true"}) == defaultAnd({'hassio_base_url': "true"})
    assert Config().validate({'hassio_base_url': "false"}) == defaultAnd({'hassio_base_url': "false"})
    assert Config().validate({'hassio_base_url': "1"}) == defaultAnd({'hassio_base_url': "1"})
    assert Config().validate({'hassio_base_url': "0"}) == defaultAnd({'hassio_base_url': "0"})
    assert Config().validate({'hassio_base_url': "yes"}) == defaultAnd({'hassio_base_url': "yes"})
    assert Config().validate({'hassio_base_url': "no"}) == defaultAnd({'hassio_base_url': "no"})


def test_validate_regex():
    assert Config().validate({'drive_ipv4': "192.168.1.1"}) == defaultAnd({'drive_ipv4': "192.168.1.1"})
    with raises(InvalidConfigurationValue):
        Config().validate({'drive_ipv4': -1})
    with raises(InvalidConfigurationValue):
        Config().validate({'drive_ipv4': "192.168.1"})


def test_remove_ssl():
    assert Config().validate({'use_ssl': True}) == defaultAnd({'use_ssl': True})
    assert Config().validate({'use_ssl': False}) == defaultAnd({'use_ssl': False})
    assert Config().validate({
        'use_ssl': False,
        'certfile': "removed",
        'keyfile': 'removed'
    }) == defaultAnd({'use_ssl': False})
    assert Config().validate({
        'use_ssl': True,
        'certfile': "kept",
        'keyfile': 'kept'
    }) == defaultAnd({
        'use_ssl': True,
        'certfile': "kept",
        'keyfile': 'kept'
    })


def test_send_error_reports():
    assert Config().validate({'send_error_reports': False}) == defaultAnd()
    assert Config().validate({'send_error_reports': True}) == defaultAnd({'send_error_reports': True})
    assert Config().validate({'send_error_reports': None}) == defaultAnd({'send_error_reports': False})


def test_unrecognized_values_filter():
    assert Config().validate({'blah': "bloo"}) == defaultAnd()


def test_removes_defaults():
    assert Config().validate({'snapshot_time_of_day': ""}) == defaultAnd()


def test_all_defaults_valid():
    path = abspath(join(__file__, "..", "..", "..", "config.json"))
    with open(path) as f:
        addon_config = json.load(f)
    config = Config()
    for key in DEFAULTS:
        if key in addon_config['schema']:
            # The key should have a default value
            assert key in DEFAULTS

            # The default should be valid
            assert config._validateConfig(key, addon_config['schema'][key], DEFAULTS[key]) == DEFAULTS[key]
    # validate that all of the defaults are present and valid
    pass


def defaultAnd(config={}):
    ret = {
        'days_between_snapshots': 3,
        'max_snapshots_in_hassio': 4,
        'max_snapshots_in_google_drive': 4,
        'use_ssl': False,
        'send_error_reports': False
    }
    ret.update(config)
    return ret


# INGRESS: Rewrite this test
"""
def test_expose_extra_server(mocker) -> None:
    assertConfigValue(
        method=Config.exposeExtraServer,
        default=False,
        param_name="expose_extra_server",
        html_name="expose_extra_server",
        override=True,
        default_removes=True)

    assert Config({"expose_extra_server": True}).exposeExtraServer() is True
    assert Config({"expose_extra_server": True}).useIngress() is False
    assert Config({"expose_extra_server": True}).warnIngress() is False

    config: Config = Config()

    # Test strange version
    config.setIngressInfo({'homeassistant': 'badversion'}, force_enable=True)
    assert config.useIngress() is False
    assert config.warnIngress() is True

    # Test empty version
    config.setIngressInfo({'homeassistant': ''}, force_enable=True)
    assert config.useIngress() is False
    assert config.warnIngress() is True

    # Test null version
    config.setIngressInfo({}, force_enable=True)
    assert config.useIngress() is False
    assert config.warnIngress() is True

    # Test weird minimum version
    config.setIngressInfo({'homeassistant': '0.91.3.otherinfo'}, force_enable=True)
    assert config.useIngress() is True
    assert config.warnIngress() is False

    # Test older
    config.setIngressInfo({'homeassistant': '0.91.2'}, force_enable=True)
    assert config.useIngress() is False
    assert config.warnIngress() is True

    # Test older
    config.setIngressInfo({'homeassistant': '0.90.3'}, force_enable=True)
    assert config.useIngress() is False
    assert config.warnIngress() is True

    # Test minimum version
    config.setIngressInfo({'homeassistant': '0.91.3'}, force_enable=True)
    assert config.useIngress() is True
    assert config.warnIngress() is False

    # Test newer version
    config.setIngressInfo({'homeassistant': '0.91.4'}, force_enable=True)
    assert config.useIngress() is True
    assert config.warnIngress() is False

    # Test newer version
    config.setIngressInfo({'homeassistant': '0.92.3'}, force_enable=True)
    assert config.useIngress() is True
    assert config.warnIngress() is False

    # Test newer version
    config.setIngressInfo({'homeassistant': '1.91.3'}, force_enable=True)
    assert config.useIngress() is True
    assert config.warnIngress() is False
"""


def test_GenerationalConfig(mocker) -> None:
    assert Config().getGenerationalConfig() is None
    assert Config({"generational_days": 3}).getGenerationalConfig() == getGenConfig({"days": 3})
    assert Config({"generational_weeks": 3}).getGenerationalConfig() == getGenConfig({"weeks": 3})
    assert Config({"generational_months": 3}).getGenerationalConfig() == getGenConfig({"months": 3})
    assert Config({"generational_years": 3}).getGenerationalConfig() == getGenConfig({"years": 3})
    assert Config({
        "generational_days": 1,
        "generational_day_of_year": 3
    }).getGenerationalConfig() == getGenConfig(
        {
            "day_of_year": 3
        })
    assert Config({
        "generational_days": 1,
        "generational_day_of_month": 3
    }).getGenerationalConfig() == getGenConfig(
        {
            "day_of_month": 3
        })
    assert Config({
        "generational_days": 1,
        "generational_day_of_week": "tue"
    }).getGenerationalConfig() == getGenConfig(
        {
            "day_of_week": "tue"
        })

    assert Config({
        "generational_day_of_month": 3,
        "generational_day_of_week": "tue",
        "generational_day_of_year": "4"
    }).getGenerationalConfig() is None


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
