from ..config import Config
import tempfile
import json
import os


def test_BasicConfig(mocker) -> None:
    
    assertConfigValue(
        method=Config.maxSnapshotsInHassio,
        default=4,
        param_name="max_snapshots_in_hassio",
        html_name="max_snapshots_in_hassio",
        override=5)

    assertConfigValue(
        method=Config.maxSnapshotsInGoogleDrive,
        default=4,
        param_name="max_snapshots_in_google_drive",
        html_name="max_snapshots_in_google_drive",
        override=5)

    assertConfigValue(
        method=Config.daysBetweenSnapshots,
        default=3,
        param_name="days_between_snapshots",
        html_name="days_between_snapshots",
        override=5)

    assertConfigValue(
        method=Config.verbose,
        default=False,
        param_name="verbose",
        html_name="verbose",
        override=True,
        default_removes=True)

    assertConfigValue(
        method=Config.useSsl,
        default=False,
        param_name="use_ssl",
        html_name="use_ssl",
        override=True,
        default_removes=False)

    assertConfigValue(
        method=Config.requireLogin,
        default=False,
        param_name="require_login",
        html_name="require_login",
        override=True,
        default_removes=True)

    assertConfigValue(
        method=Config.certFile,
        default="/ssl/fullchain.pem",
        param_name="certfile",
        html_name="certfile",
        override="changed",
        default_removes=False,
        remove_if_not={"use_ssl": True})

    assertConfigValue(
        method=Config.keyFile,
        default="/ssl/privkey.pem",
        param_name="keyfile",
        html_name="keyfile",
        override="changed",
        default_removes=False,
        remove_if_not={"use_ssl": True})

    assertConfigValue(
        method=Config.snapshotTimeOfDay,
        default=None,
        default_json="",
        param_name="snapshot_time_of_day",
        html_name="snapshot_time_of_day",
        override="changed",
        default_removes=True)

    assertConfigValue(
        method=Config.snapshotPassword,
        default="",
        param_name="snapshot_password",
        html_name="snapshot_password",
        override="secret")

    assertConfigValue(
        method=Config.notifyForStaleSnapshots,
        default=True,
        param_name="notify_for_stale_snapshots",
        html_name="notify_for_stale_snapshots",
        override=False,
        default_removes=True)

    assertConfigValue(
        method=Config.enableSnapshotStaleSensor,
        default=True,
        param_name="enable_snapshot_stale_sensor",
        html_name="enable_snapshot_stale_sensor",
        override=False,
        default_removes=True)

    assertConfigValue(
        method=Config.enableSnapshotStateSensor,
        default=True,
        param_name="enable_snapshot_state_sensor",
        html_name="enable_snapshot_state_sensor",
        override=False,
        default_removes=True)


def test_GenerationalConfig(mocker) -> None:
    def getDays(s):
        if s.getGenerationalConfig():
            return s.getGenerationalConfig()['days']
        else:
            return 0
    assertConfigValue(
        method=getDays,
        default=0,
        param_name="generational_days",
        html_name="generational_days",
        override=5,
        remove_if_not={'generational_enabled': 'on'})

    def getweeks(s):
        if s.getGenerationalConfig():
            return s.getGenerationalConfig()['weeks']
        else:
            return 0
    assertConfigValue(
        method=getweeks,
        default=0,
        param_name="generational_weeks",
        html_name="generational_weeks",
        override=5,
        remove_if_not={'generational_enabled': 'on'})

    def getmonths(s):
        if s.getGenerationalConfig():
            return s.getGenerationalConfig()['months']
        else:
            return 0
    assertConfigValue(
        method=getmonths,
        default=0,
        param_name="generational_months",
        html_name="generational_months",
        override=5,
        remove_if_not={'generational_enabled': 'on'})

    def getyears(s):
        if s.getGenerationalConfig():
            return s.getGenerationalConfig()['years']
        else:
            return 0
    assertConfigValue(
        method=getyears,
        default=0,
        param_name="generational_years",
        html_name="generational_years",
        override=5,
        remove_if_not={'generational_enabled': 'on'})

    def getdow(s):
        if s.getGenerationalConfig():
            return s.getGenerationalConfig()['day_of_week']
        elif 'generational_day_of_week' in s.config:
            return s.config['generational_day_of_week']
        else:
            return 'mon'
    assertConfigValue(
        method=getdow,
        default="mon",
        param_name="generational_day_of_week",
        html_name="generational_day_of_week",
        override="tue",
        default_removes=True)

    def getdom(s):
        if s.getGenerationalConfig():
            return s.getGenerationalConfig()['day_of_month']
        elif 'generational_day_of_month' in s.config:
            return s.config['generational_day_of_month']
        else:
            return 1
    assertConfigValue(
        method=getdom,
        default=1,
        param_name="generational_day_of_month",
        html_name="generational_day_of_month",
        override=2,
        default_removes=True)

    def getdoy(s):
        if s.getGenerationalConfig():
            return s.getGenerationalConfig()['day_of_year']
        elif 'generational_day_of_year' in s.config:
            return s.config['generational_day_of_year']
        else:
            return 1
    assertConfigValue(
        method=getdoy,
        default=1,
        param_name="generational_day_of_year",
        html_name="generational_day_of_year",
        override=2,
        default_removes=True)


def test_sendErrorReports():
    assertConfigValue(
        method=Config.sendErrorReports,
        default=None,
        set_default=False,
        param_name="send_error_reports",
        html_name="send_error_reports",
        override=True)

    assertConfigValue(
        method=Config.sendErrorReports,
        default=None,
        set_default=False,
        param_name="send_error_reports",
        html_name="send_error_reports",
        override=False)


def assertConfigValue(method=None, param_name=None, default=None, default_json=None, set_default=None, override=None, html_name=None, default_removes=False, remove_if_not={}):
    if default_json is None:
        default_json = default

    if set_default is None:
        set_default = default

    assert default is not override

    # verify default
    config: Config = Config([])
    assert method(config) == default

    # verify override
    config = Config([], {param_name: override})
    assert method(config) == override

    # verify file override
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(str.encode(json.dumps({param_name: override})))
        tmp.seek(0)
        config = Config([tmp.name])
        assert method(config) == override

    if html_name:
        # Verify html query param rewrite
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(str.encode(json.dumps(remove_if_not)))
            tmp.seek(0)
            config = Config([tmp.name])
            assert method(config) == default
            tmp.seek(0)
            args = remove_if_not.copy()
            args[param_name] = override
            args = asHtmlParams(args)

            def handle(c):
                tmp.seek(0)
                tmp.write(str.encode(json.dumps(c, indent=4)))
                tmp.seek(0)

            config.update(handle, **args)
            assert method(config) == override
            tmp.seek(0)
            assert method(Config([tmp.name])) == override

        with tempfile.NamedTemporaryFile() as tmp:
            source = remove_if_not.copy()
            source.update({param_name: default_json})
            tmp.write(str.encode(json.dumps(source)))
            tmp.seek(0)
            config = Config([tmp.name])
            assert method(config) == default
            tmp.seek(0)
            args = asHtmlParams(source)
            config.update(handle, **args)
            assert method(config) == set_default
            tmp.seek(0)
            assert method(Config([tmp.name])) == set_default
            tmp.seek(0)
            saved = json.load(tmp)
            if default_removes:
                assert param_name not in saved
            else:
                assert param_name in saved

        if len(remove_if_not) > 0:
            with tempfile.NamedTemporaryFile() as tmp:
                source = {}
                source.update({param_name: default})
                tmp.write(str.encode(json.dumps(source)))
                tmp.seek(0)
                config = Config([tmp.name])
                tmp.seek(0)
                args = {param_name: override}
                config.update(handle, **asHtmlParams(source))
                assert method(config) == default
                tmp.seek(0)
                saved = json.load(tmp)
                assert param_name not in saved

    with open(os.path.join(os.getcwd(), "hassio-google-drive-backup", "config.json")) as file:
        config = json.load(file)
        assert param_name in config['schema']
        assert len(config['schema'][param_name]) > 0


def getHtmlParam(value):
    if isinstance(value, bool):
        if value:
            return "on"
        else:
            return None
    return str(value)


def asHtmlParams(values):
    ret = {}
    for key in values:
        value = getHtmlParam(values[key])
        if value:
            ret[key] = value
    return ret
