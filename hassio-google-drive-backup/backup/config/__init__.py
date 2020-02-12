def strToBool(value) -> bool:
    return str(value).lower() in ['true', 't', 'on', 'yes', 'y', '1', 'hai', 'si', 'omgyesplease']


from .config import Config, GenConfig  # noqa: F401
from .settings import Setting, _DEFAULTS, _VALIDATORS, _LOOKUP  # noqa: F401
from .createoptions import CreateOptions  # noqa: F401
