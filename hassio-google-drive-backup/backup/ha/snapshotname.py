from datetime import datetime

from ..logger import getLogger

logger = getLogger(__name__)

BACKUP_NAME_KEYS = {
    "{type}": lambda backup_type, now_local, host_info: backup_type,
    "{year}": lambda backup_type, now_local, host_info: now_local.strftime("%Y"),
    "{year_short}": lambda backup_type, now_local, host_info: now_local.strftime("%y"),
    "{weekday}": lambda backup_type, now_local, host_info: now_local.strftime("%A"),
    "{weekday_short}": lambda backup_type, now_local, host_info: now_local.strftime("%a"),
    "{month}": lambda backup_type, now_local, host_info: now_local.strftime("%m"),
    "{month_long}": lambda backup_type, now_local, host_info: now_local.strftime("%B"),
    "{month_short}": lambda backup_type, now_local, host_info: now_local.strftime("%b"),
    "{ms}": lambda backup_type, now_local, host_info: now_local.strftime("%f"),
    "{day}": lambda backup_type, now_local, host_info: now_local.strftime("%d"),
    "{hr24}": lambda backup_type, now_local, host_info: now_local.strftime("%H"),
    "{hr12}": lambda backup_type, now_local, host_info: now_local.strftime("%I"),
    "{min}": lambda backup_type, now_local, host_info: now_local.strftime("%M"),
    "{sec}": lambda backup_type, now_local, host_info: now_local.strftime("%S"),
    "{ampm}": lambda backup_type, now_local, host_info: now_local.strftime("%p"),
    "{version_ha}": lambda backup_type, now_local, host_info: str(host_info.get('homeassistant', 'Unknown')),
    "{version_hassos}": lambda backup_type, now_local, host_info: str(host_info.get('hassos', 'Unknown')),
    "{version_super}": lambda backup_type, now_local, host_info: str(host_info.get('supervisor', 'Unknown')),
    "{date}": lambda backup_type, now_local, host_info: now_local.strftime("%x"),
    "{time}": lambda backup_type, now_local, host_info: now_local.strftime("%X"),
    "{datetime}": lambda backup_type, now_local, host_info: now_local.strftime("%c"),
    "{isotime}": lambda backup_type, now_local, host_info: now_local.isoformat(),
    "{hostname}": lambda backup_type, now_local, host_info: str(host_info.get('hostname', 'Unknown')),
}


class BackupName():
    def resolve(self, backup_type: str, template: str, now_local: datetime, host_info) -> str:
        for key in BACKUP_NAME_KEYS:
            template = template.replace(key, BACKUP_NAME_KEYS[key](
                backup_type, now_local, host_info))
        return template
