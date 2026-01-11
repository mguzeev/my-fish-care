from typing import Optional
from app.i18n.loader import i18n


def help_text(locale: Optional[str]) -> str:
    return i18n.t("help.text", locale)


def start_text_existing(name: str, locale: Optional[str]) -> str:
    return i18n.t("start.welcome_existing", locale, name=name)


def start_text_new(telegram_id: int, locale: Optional[str]) -> str:
    return i18n.t("start.welcome_new", locale, telegram_id=telegram_id)


def profile_text(
    name: Optional[str],
    username: str,
    email: str,
    role: str,
    is_active: bool,
    is_verified: bool,
    locale: Optional[str],
) -> str:
    header = i18n.t("profile.header", locale)
    lines = [
        header,
        i18n.t("profile.name", locale, name=name or "Not set"),
        i18n.t("profile.username", locale, username=username),
        i18n.t("profile.email", locale, email=email),
        i18n.t("profile.role", locale, role=role),
        i18n.t("profile.status_active", locale) if is_active else i18n.t("profile.status_inactive", locale),
        i18n.t("profile.verified_yes", locale) if is_verified else i18n.t("profile.verified_no", locale),
    ]
    return "\n".join(lines)


def profile_not_linked_text(telegram_id: int, locale: Optional[str]) -> str:
    return i18n.t("profile.not_linked", locale, telegram_id=telegram_id)


def echo_text(message_text: str, locale: Optional[str]) -> str:
    return i18n.t("echo.response", locale, text=message_text)


def error_text(key: str, locale: Optional[str]) -> str:
    return i18n.t(f"errors.{key}", locale)
