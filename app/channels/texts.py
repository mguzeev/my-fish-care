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
    locale: Optional[str],
    plan_name: str,
    plan_type: str,
    status: str,
    free_requests_limit: int = 0,
    free_requests_remaining: int = 0,
    subscription_limit: Optional[int] = None,
    subscription_remaining: Optional[int] = None,
    onetime_total: Optional[int] = None,
    onetime_remaining: Optional[int] = None,
    next_billing_date: Optional[str] = None,
) -> str:
    lines = [i18n.t("profile.header", locale, name=name or "User")]
    lines.append(i18n.t("profile.current_plan", locale))
    lines.append(i18n.t("profile.plan_name", locale, plan_name=plan_name))
    lines.append(i18n.t("profile.plan_type", locale, plan_type=plan_type))
    lines.append(i18n.t("profile.plan_status", locale, status=status))
    
    # Free requests
    if free_requests_limit > 0:
        lines.append(i18n.t("profile.free_requests", locale, 
                          remaining=free_requests_remaining, 
                          limit=free_requests_limit))
    
    # Subscription requests
    if subscription_limit is not None and subscription_limit > 0:
        lines.append(i18n.t("profile.subscription_requests", locale,
                          remaining=subscription_remaining or 0,
                          limit=subscription_limit))
    elif subscription_limit == 0:
        lines.append(i18n.t("profile.unlimited", locale))
    
    # One-time credits
    if onetime_total is not None and onetime_total > 0:
        lines.append(i18n.t("profile.onetime_credits", locale,
                          remaining=onetime_remaining or 0,
                          total=onetime_total))
    
    # Next billing
    if next_billing_date:
        lines.append(i18n.t("profile.next_billing", locale, date=next_billing_date))
    
    # Upgrade prompt
    lines.append(i18n.t("profile.upgrade_prompt", locale))
    
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


def text_not_supported(locale: Optional[str]) -> str:
    """Text shown when agent doesn't support text."""
    return i18n.t("errors.text_not_supported", locale)


def vision_not_supported(locale: Optional[str]) -> str:
    """Text shown when agent doesn't support vision/images."""
    return i18n.t("errors.vision_not_supported", locale)
