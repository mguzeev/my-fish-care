from typing import Optional
from app.i18n.loader import i18n
from app.core.config import settings


def help_text(locale: Optional[str]) -> str:
    return i18n.t("help.text", locale)


def start_text_existing(name: str, locale: Optional[str]) -> str:
    return i18n.t("start.welcome_existing", locale, name=name)


def start_text_new(telegram_id: int, locale: Optional[str]) -> str:
    return i18n.t("start.welcome_new", locale, telegram_id=telegram_id)


def start_text_auto_registered(username: str, locale: Optional[str]) -> str:
    return i18n.t("start.auto_registered", locale, username=username)


def register_already_linked(email: str, username: str, locale: Optional[str]) -> str:
    return i18n.t("register.already_linked", locale, email=email, username=username)


def register_prompt_email(locale: Optional[str]) -> str:
    return i18n.t("register.prompt_email", locale)


def register_invalid_email(locale: Optional[str]) -> str:
    return i18n.t("register.invalid_email", locale)


def register_success(email: str, locale: Optional[str]) -> str:
    return i18n.t("register.success", locale, email=email)


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


def locale_usage(locale: Optional[str], locales: str) -> str:
    return i18n.t("locale.usage", locale, locales=locales)


def locale_success(code: str, locale: Optional[str]) -> str:
    return i18n.t("locale.success", locale, code=code)


def locale_invalid(locale: Optional[str], locales: str) -> str:
    return i18n.t("locale.invalid", locale, locales=locales)


def photo_processing(locale: Optional[str]) -> str:
    """Text shown while processing a photo."""
    return i18n.t("photo.processing", locale)


def photo_no_vision_agent(locale: Optional[str]) -> str:
    """Text shown when no vision-capable agent is available."""
    return i18n.t("photo.no_vision_agent", locale)
