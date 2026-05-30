"""
Lightweight internationalization (i18n) for the addon.

Source strings stay English in the codebase. Templates and code wrap them
with ``_()``; if a translation is available for the active language it is
returned, otherwise the original English string falls through unchanged.

Translations are loaded from ``backup/locales/<lang>.json`` at startup. To
add a language, drop a new JSON file in that directory and register it in
``LANGUAGES`` below.
"""
import json
import os
from typing import Dict, Optional

# Each entry is: language code -> display metadata.
# ``rtl`` toggles right-to-left rendering (HTML dir + rtl.css include).
LANGUAGES: Dict[str, Dict] = {
    "en": {"name": "English", "rtl": False},
    "he": {"name": "עברית", "rtl": True},
}

DEFAULT_LANGUAGE = "en"


def _locales_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "locales")


class Translations:
    """Loads locale files once and serves lookups in O(1)."""

    def __init__(self):
        self._current: str = DEFAULT_LANGUAGE
        self._maps: Dict[str, Dict[str, str]] = {}
        self._load_all()

    def _load_all(self) -> None:
        base = _locales_dir()
        for lang in LANGUAGES:
            path = os.path.join(base, "{}.json".format(lang))
            try:
                with open(path, encoding="utf-8") as f:
                    self._maps[lang] = json.load(f)
            except FileNotFoundError:
                self._maps[lang] = {}
            except (OSError, ValueError):
                # Bad/corrupt file: fall back to identity mapping rather than
                # taking down the addon over a translation.
                self._maps[lang] = {}

    def set_language(self, lang: Optional[str]) -> None:
        self._current = lang if (lang and lang in LANGUAGES) else DEFAULT_LANGUAGE

    @property
    def language(self) -> str:
        return self._current

    @property
    def is_rtl(self) -> bool:
        return bool(LANGUAGES.get(self._current, {}).get("rtl", False))

    @property
    def dir(self) -> str:
        return "rtl" if self.is_rtl else "ltr"

    def gettext(self, source: str) -> str:
        """Return the translation of ``source`` or ``source`` if none exists."""
        if not source:
            return source
        return self._maps.get(self._current, {}).get(source, source)

    def js_map(self) -> Dict[str, str]:
        """Translations to inject for the browser. Identity entries are
        omitted to keep the bootstrap payload small."""
        m = self._maps.get(self._current, {})
        return {k: v for k, v in m.items() if k != v}


_singleton: Optional[Translations] = None


def translations() -> Translations:
    global _singleton
    if _singleton is None:
        _singleton = Translations()
    return _singleton


def gettext(source: str) -> str:
    return translations().gettext(source)


# Alias used by templates and Python code.
_ = gettext


def set_language(lang: Optional[str]) -> None:
    translations().set_language(lang)


def install_jinja_globals(env) -> None:
    """Register translation helpers as Jinja2 globals so templates can
    use ``{{ _("English source") }}`` and ``{{ dir }}`` without imports."""
    env.globals["_"] = gettext
    env.globals["lang"] = lambda: translations().language
    env.globals["dir"] = lambda: translations().dir
    env.globals["is_rtl"] = lambda: translations().is_rtl
    env.globals["available_languages"] = LANGUAGES
