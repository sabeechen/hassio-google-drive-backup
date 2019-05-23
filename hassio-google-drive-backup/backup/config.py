import json
import os
import os.path
import os
import uuid
import logging

from .logbase import LogBase, console_handler
from typing import Dict, List, Any, Optional
from .resolver import Resolver
from .settings import Setting, _LOOKUP

ALWAYS_KEEP = {
    Setting.DAYS_BETWEEN_SNAPSHOTS,
    Setting.MAX_SNAPSHOTS_IN_HASSIO,
    Setting.MAX_SNAPSHOTS_IN_GOOGLE_DRIVE,
    Setting.USE_SSL
}

KEEP_DEFAULT = {
    Setting.SEND_ERROR_REPORTS
}


class Config(LogBase):
    def __init__(self, resolver: Resolver = None):
        self.overrides = {}
        self.config = {}
        self._clientIdentifier = uuid.uuid4()
        self.resolver = resolver
        console_handler.setLevel(logging.INFO)

        self.retained = self._loadRetained()
        self._gen_config_cache = self.getGenerationalConfig()
        self._refreshResolver()

    def _refreshResolver(self):
        if self.resolver is not None:
            if len(self.get(Setting.DRIVE_URL)) > 0:
                self.resolver.addOverride("www.googleapis.com", [self.get(Setting.DRIVE_URL)])
            else:
                self.resolver.clearOverrides()
            self.resolver.addResolveAddress("www.googleapis.com")
            self.resolver.setIgnoreIpv6(self.get(Setting.IGNORE_IPV6_ADDRESSES))
            self.resolver.setDnsServers(self.get(Setting.ALTERNATE_DNS_SERVERS).split(","))

    def getConfigFor(self, options):
        new_config = Config()
        new_config.overrides = self.overrides.copy()
        new_config.update(self.validate(options))
        return new_config

    def validateUpdate(self, additions):
        new_config = self.config.copy()
        new_config.update(additions)
        return self.validate(new_config)

    def validate(self, new_config) -> Dict[str, Any]:
        final_config = {}

        # validate each item
        for key in new_config:
            if type(key) == str:
                if key not in _LOOKUP:
                    # its not in the schema, just ignore it
                    continue
                setting = _LOOKUP[key]
            else:
                setting = key

            value = setting.validator().validate(new_config[key])
            if value is not None and (setting in KEEP_DEFAULT or value != setting.default()):
                final_config[setting] = value

        # add defaults
        for key in ALWAYS_KEEP:
            if key not in final_config:
                final_config[key] = key.default()

        if not final_config.get(Setting.USE_SSL, False):
            for key in [Setting.CERTFILE, Setting.KEYFILE]:
                if key in final_config:
                    del final_config[key]

        return final_config

    def update(self, new_config):
        self.config = self.validate(new_config)
        self._gen_config_cache = self.getGenerationalConfig()
        console_handler.setLevel(logging.DEBUG if self.get(Setting.VERBOSE) else logging.INFO)
        self._refreshResolver()

    def warnExposeIngressUpgrade(self):
        return False

    def useIngress(self):
        return False

    def warnIngress(self):
        return False

    def driveHost(self) -> str:
        return self.get(Setting.DRIVE_URL)

    def alternateDnsServers(self) -> str:
        return str(self.config['alternate_dns_servers'])

    def driveIpv4(self) -> str:
        return str(self.config['drive_ipv4'])

    def ignoreIpv6(self) -> bool:
        return bool(self.config['ignore_ipv6_addresses'])

    def clientIdentifier(self) -> str:
        return str(self._clientIdentifier)

    def getGenerationalConfig(self) -> Optional[Dict[str, Any]]:
        days = self.get(Setting.GENERATIONAL_DAYS)
        weeks = self.get(Setting.GENERATIONAL_WEEKS)
        months = self.get(Setting.GENERATIONAL_MONTHS)
        years = self.get(Setting.GENERATIONAL_YEARS)
        if days + weeks + months + years == 0:
            return None
        base = {
            'days': days,
            'weeks': weeks,
            'months': months,
            'years': years,
            'day_of_week': self.get(Setting.GENERATIONAL_DAY_OF_WEEK),
            'day_of_month': self.get(Setting.GENERATIONAL_DAY_OF_MONTH),
            'day_of_year': self.get(Setting.GENERATIONAL_DAY_OF_YEAR)
        }
        if base['days'] <= 1:
            # must always be >= 1, otherwise we'll just create and delete snapshots constantly.
            base['days'] = 1
        return base

    def _loadRetained(self) -> List[str]:
        if os.path.exists(self.get(Setting.RETAINED_FILE_PATH)):
            with open(self.get(Setting.RETAINED_FILE_PATH)) as f:
                try:
                    return json.load(f)['retained']
                except json.JSONDecodeError:
                    self.error("Unable to parse retained snapshot settings")
                    return []
        return []

    def isRetained(self, slug):
        return slug in self.retained

    def setRetained(self, slug, retain):
        if retain and slug not in self.retained:
            self.retained.append(slug)
            with open(self.get(Setting.RETAINED_FILE_PATH), "w") as f:
                json.dump({
                    'retained': self.retained
                }, f)
        elif not retain and slug in self.retained:
            self.retained.remove(slug)
            with open(self.get(Setting.RETAINED_FILE_PATH), "w") as f:
                json.dump({
                    'retained': self.retained
                }, f)

    def isExplicit(self, setting):
        return setting in self.config

    def override(self, setting: Setting, value):
        self.config[setting] = value
        self.overrides[setting] = value
        return self

    def get(self, setting: Setting):
        if setting in self.overrides:
            return self.overrides[setting]
        if setting in self.config:
            return self.config[setting]
        if setting.key() in self.config:
            return self.config[setting.key()]
        else:
            return setting.default()
