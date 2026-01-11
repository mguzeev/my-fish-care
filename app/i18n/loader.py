import json
from pathlib import Path
from typing import Any, Dict, Optional
from app.core.config import settings


class I18n:
    def __init__(self, default_locale: str = "en"):
        self.default_locale = default_locale
        self._translations: Dict[str, Dict[str, Any]] = {}
        self._load_all()

    def _load_all(self) -> None:
        base = Path(__file__).parent / "strings"
        for locale in settings.supported_locales:
            file = base / f"{locale}.json"
            if file.exists():
                try:
                    self._translations[locale] = json.loads(file.read_text(encoding="utf-8"))
                except Exception:
                    self._translations[locale] = {}
            else:
                self._translations[locale] = {}

    def _get(self, key: str, locale: str) -> Optional[str]:
        parts = key.split(".")
        data = self._translations.get(locale) or {}
        cur: Any = data
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return None
        return cur if isinstance(cur, str) else None

    def t(self, key: str, locale: Optional[str] = None, **params: Any) -> str:
        loc = locale or self.default_locale
        text = self._get(key, loc) or self._get(key, self.default_locale)
        if text is None:
            # Return key when not found
            return key
        try:
            return text.format(**params)
        except Exception:
            return text


# Global i18n instance
i18n = I18n()
