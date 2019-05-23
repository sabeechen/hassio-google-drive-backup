from pytest import raises
from ..exceptions import InvalidConfigurationValue
from ..config import Config
from ..settings import Setting
from ..resolver import Resolver
import socket


def test_validate_empty():
    config = Config()
    assert config.validate({}) == defaultAnd()


def test_validate_int():
    assert Config().validate({'max_snapshots_in_hassio': 5}) == defaultAnd({Setting.MAX_SNAPSHOTS_IN_HASSIO: 5})
    assert Config().validate({'max_snapshots_in_hassio': 5.0}) == defaultAnd({Setting.MAX_SNAPSHOTS_IN_HASSIO: 5})
    assert Config().validate({'max_snapshots_in_hassio': "5"}) == defaultAnd({Setting.MAX_SNAPSHOTS_IN_HASSIO: 5})

    with raises(InvalidConfigurationValue):
        Config().validate({'max_snapshots_in_hassio': -1})


def test_validate_float():
    setting = Setting.DAYS_BETWEEN_SNAPSHOTS
    assert Config().validate({setting: 5}) == defaultAnd({setting: 5})
    assert Config().validate({setting.key(): 5}) == defaultAnd({setting: 5})
    assert Config().validate({setting: 5.0}) == defaultAnd({setting: 5})
    assert Config().validate({setting: "5"}) == defaultAnd({setting: 5})

    with raises(InvalidConfigurationValue):
        Config().validate({'days_between_snapshots': -1})


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
    assert Config().validate({Setting.SNAPSHOT_NAME: True}) == defaultAnd({Setting.SNAPSHOT_NAME: "True"})
    assert Config().validate({Setting.SNAPSHOT_NAME: False}) == defaultAnd({Setting.SNAPSHOT_NAME: "False"})
    assert Config().validate({Setting.SNAPSHOT_NAME: "true"}) == defaultAnd({Setting.SNAPSHOT_NAME: "true"})
    assert Config().validate({Setting.SNAPSHOT_NAME: "false"}) == defaultAnd({Setting.SNAPSHOT_NAME: "false"})
    assert Config().validate({Setting.SNAPSHOT_NAME: "1"}) == defaultAnd({Setting.SNAPSHOT_NAME: "1"})
    assert Config().validate({Setting.SNAPSHOT_NAME: "0"}) == defaultAnd({Setting.SNAPSHOT_NAME: "0"})
    assert Config().validate({Setting.SNAPSHOT_NAME: "yes"}) == defaultAnd({Setting.SNAPSHOT_NAME: "yes"})
    assert Config().validate({Setting.SNAPSHOT_NAME: "no"}) == defaultAnd({Setting.SNAPSHOT_NAME: "no"})


def test_validate_url():
    assert Config().validate({Setting.HASSIO_URL: True}) == defaultAnd({Setting.HASSIO_URL: "True"})
    assert Config().validate({Setting.HASSIO_URL: False}) == defaultAnd({Setting.HASSIO_URL: "False"})
    assert Config().validate({Setting.HASSIO_URL: "true"}) == defaultAnd({Setting.HASSIO_URL: "true"})
    assert Config().validate({Setting.HASSIO_URL: "false"}) == defaultAnd({Setting.HASSIO_URL: "false"})
    assert Config().validate({Setting.HASSIO_URL: "1"}) == defaultAnd({Setting.HASSIO_URL: "1"})
    assert Config().validate({Setting.HASSIO_URL: "0"}) == defaultAnd({Setting.HASSIO_URL: "0"})
    assert Config().validate({Setting.HASSIO_URL: "yes"}) == defaultAnd({Setting.HASSIO_URL: "yes"})
    assert Config().validate({Setting.HASSIO_URL: "no"}) == defaultAnd({Setting.HASSIO_URL: "no"})


def test_validate_regex():
    assert Config().validate({Setting.DRIVE_IPV4: "192.168.1.1"}) == defaultAnd({Setting.DRIVE_IPV4: "192.168.1.1"})
    with raises(InvalidConfigurationValue):
        Config().validate({Setting.DRIVE_IPV4: -1})
    with raises(InvalidConfigurationValue):
        Config().validate({Setting.DRIVE_IPV4: "192.168.1"})


def test_remove_ssl():
    assert Config().validate({Setting.USE_SSL: True}) == defaultAnd({Setting.USE_SSL: True})
    assert Config().validate({Setting.USE_SSL: False}) == defaultAnd({Setting.USE_SSL: False})
    assert Config().validate({
        Setting.USE_SSL: False,
        Setting.CERTFILE: "removed",
        Setting.KEYFILE: 'removed'
    }) == defaultAnd({Setting.USE_SSL: False})
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
    assert Config().validate({Setting.SEND_ERROR_REPORTS: False}) == defaultAnd({Setting.SEND_ERROR_REPORTS: False})
    assert Config().validate({Setting.SEND_ERROR_REPORTS: True}) == defaultAnd({Setting.SEND_ERROR_REPORTS: True})
    assert Config().validate({Setting.SEND_ERROR_REPORTS: None}) == defaultAnd()


def test_unrecognized_values_filter():
    assert Config().validate({'blah': "bloo"}) == defaultAnd()


def test_removes_defaults():
    assert Config().validate({Setting.SNAPSHOT_TIME_OF_DAY: ""}) == defaultAnd()


def defaultAnd(config={}):
    ret = {
        Setting.DAYS_BETWEEN_SNAPSHOTS: 3,
        Setting.MAX_SNAPSHOTS_IN_HASSIO: 4,
        Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE: 4,
        Setting.USE_SSL: False
    }
    ret.update(config)
    return ret


def test_GenerationalConfig(mocker) -> None:
    assert Config().getGenerationalConfig() is None
    assert Config().override(Setting.GENERATIONAL_DAYS, 3).getGenerationalConfig() == getGenConfig({"days": 3})
    assert Config().override(Setting.GENERATIONAL_WEEKS, 3).getGenerationalConfig() == getGenConfig({"weeks": 3})
    assert Config().override(Setting.GENERATIONAL_MONTHS, 3).getGenerationalConfig() == getGenConfig({"months": 3})
    assert Config().override(Setting.GENERATIONAL_YEARS, 3).getGenerationalConfig() == getGenConfig({"years": 3})
    assert Config().override(Setting.GENERATIONAL_DAYS, 1).override(Setting.GENERATIONAL_DAY_OF_YEAR, 3).getGenerationalConfig() == getGenConfig({
        "day_of_year": 3
    })
    assert Config().override(Setting.GENERATIONAL_DAYS, 1).override(Setting.GENERATIONAL_DAY_OF_MONTH, 3).getGenerationalConfig() == getGenConfig({
        "day_of_month": 3
    })
    assert Config().override(Setting.GENERATIONAL_DAYS, 1).override(Setting.GENERATIONAL_DAY_OF_WEEK, "tue").getGenerationalConfig() == getGenConfig({"day_of_week": "tue"})

    assert Config().override(Setting.GENERATIONAL_DAY_OF_MONTH, 3).override(Setting.GENERATIONAL_DAY_OF_WEEK, "tue").override(Setting.GENERATIONAL_DAY_OF_YEAR, "4").getGenerationalConfig() is None


def test_resolver(time):
    host = "www.googleapis.com"
    with Resolver(time) as resolver:
        config = Config(resolver)
        assert config.resolver is not None
        assert len(socket.getaddrinfo(host, 443)) > 1

        # override shoudl just return the drive ipv4 value
        config.update({Setting.DRIVE_IPV4: "1.1.1.1"})
        assert socket.getaddrinfo(host, 443) == [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ("1.1.1.1", 443))]
        assert len(socket.getaddrinfo(host, 443)) == 1

        # default options should clear the override
        config.update({})
        assert len(socket.getaddrinfo(host, 443)) > 1

        # override should ignore alternate dns
        config.update({Setting.DRIVE_IPV4: "1.1.1.1", Setting.ALTERNATE_DNS_SERVERS: "8.8.8.8"})
        resolver.toggle()
        assert socket.getaddrinfo(host, 443) == [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ("1.1.1.1", 443))]
        assert len(socket.getaddrinfo(host, 443)) == 1

        # test using alternate dns
        assert resolver.cache[host] is None
        config.update({Setting.ALTERNATE_DNS_SERVERS: "8.8.8.8"})
        assert len(socket.getaddrinfo(host, 443)) > 1
        assert len(resolver.cache[host][0]) > 1
        assert len(resolver.cache[host][0]) == len(socket.getaddrinfo(host, 443))


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
