from datetime import datetime

from ..logger import getLogger

logger = getLogger(__name__)

SNAPSHOT_NAME_KEYS = {
    "{type}": lambda snapshot_type, now_local, host_info: snapshot_type,
    "{year}": lambda snapshot_type, now_local, host_info: now_local.strftime("%Y"),
    "{year_short}": lambda snapshot_type, now_local, host_info: now_local.strftime("%y"),
    "{weekday}": lambda snapshot_type, now_local, host_info: now_local.strftime("%A"),
    "{weekday_short}": lambda snapshot_type, now_local, host_info: now_local.strftime("%a"),
    "{month}": lambda snapshot_type, now_local, host_info: now_local.strftime("%m"),
    "{month_long}": lambda snapshot_type, now_local, host_info: now_local.strftime("%B"),
    "{month_short}": lambda snapshot_type, now_local, host_info: now_local.strftime("%b"),
    "{ms}": lambda snapshot_type, now_local, host_info: now_local.strftime("%f"),
    "{day}": lambda snapshot_type, now_local, host_info: now_local.strftime("%d"),
    "{hr24}": lambda snapshot_type, now_local, host_info: now_local.strftime("%H"),
    "{hr12}": lambda snapshot_type, now_local, host_info: now_local.strftime("%I"),
    "{min}": lambda snapshot_type, now_local, host_info: now_local.strftime("%M"),
    "{sec}": lambda snapshot_type, now_local, host_info: now_local.strftime("%S"),
    "{ampm}": lambda snapshot_type, now_local, host_info: now_local.strftime("%p"),
    "{version_ha}": lambda snapshot_type, now_local, host_info: str(host_info.get('homeassistant', 'Unknown')),
    "{version_hassos}": lambda snapshot_type, now_local, host_info: str(host_info.get('hassos', 'Unknown')),
    "{version_super}": lambda snapshot_type, now_local, host_info: str(host_info.get('supervisor', 'Unknown')),
    "{date}": lambda snapshot_type, now_local, host_info: now_local.strftime("%x"),
    "{time}": lambda snapshot_type, now_local, host_info: now_local.strftime("%X"),
    "{datetime}": lambda snapshot_type, now_local, host_info: now_local.strftime("%c"),
    "{isotime}": lambda snapshot_type, now_local, host_info: now_local.isoformat(),
    "{hostname}": lambda snapshot_type, now_local, host_info: str(host_info.get('hostname', 'Unknown')),
}


class SnapshotName():
    def resolve(self, snapshot_type: str, template: str, now_local: datetime, host_info) -> str:
        for key in SNAPSHOT_NAME_KEYS:
            template = template.replace(key, SNAPSHOT_NAME_KEYS[key](
                snapshot_type, now_local, host_info))
        return template
