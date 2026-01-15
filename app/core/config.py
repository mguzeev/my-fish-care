"""Configuration settings for the application."""
import logging
from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings."""
    
    # Application
    app_name: str = "Bot Generic"
    app_version: str = "1.0.0"
    debug: bool = False
    api_base_url: str = "http://localhost:8000"  # Base URL for API endpoints and OAuth callbacks
    
    
    # Database
    database_url: str
    database_echo: bool = False
    
    # Security
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # CORS
    cors_origins: list[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]
    
    # Telegram
    telegram_bot_token: Optional[str] = None
    telegram_bot_username: Optional[str] = None
    telegram_base_url: Optional[str] = None
    telegram_webhook_url: Optional[str] = None
    telegram_webhook_path: str = "/webhook/telegram"
    telegram_use_webhook: bool = False
    telegram_webhook_secret: Optional[str] = None
    
    # OpenAI
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4"
    openai_max_tokens: int = 2000
    openai_temperature: float = 0.7
    
    # Redis (for caching and rate limiting)
    redis_url: Optional[str] = None

    # I18n
    supported_locales: list[str] = ["en", "uk", "ru"]
    
    # Paddle
    paddle_billing_enabled: bool = False
    paddle_api_key: Optional[str] = Field(default=None, alias="PADDLE_API_KEY")
    paddle_client_token: Optional[str] = Field(default=None, alias="PADDLE_CLIENT_TOKEN")
    paddle_webhook_secret: Optional[str] = Field(default=None, alias="PADDLE_WEBHOOK_SECRET")
    paddle_vendor_id: Optional[str] = Field(default=None, alias="PADDLE_VENDOR_ID")
    paddle_environment: str = Field(default="sandbox", alias="PADDLE_ENVIRONMENT")  # sandbox or production
    
    # Rate Limiting
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000
    rate_limit_per_day: int = 10000
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        import os as _os
        env_file = ".env.local" if _os.path.exists(".env.local") else ".env"
        case_sensitive = False
        populate_by_name = True  # Allow both field name and alias


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()


def validate_paddle_settings(current_settings: Settings) -> None:
    """Fail fast if Paddle billing is enabled but required settings are missing."""
    if not current_settings.paddle_billing_enabled:
        logger.info("Paddle billing: DISABLED")
        return

    logger.info(f"Paddle billing: ENABLED (environment: {current_settings.paddle_environment})")

    missing = [
        name
        for name in (
            "paddle_api_key",
            "paddle_webhook_secret",
        )
        if not getattr(current_settings, name)
    ]

    if current_settings.paddle_environment not in {"sandbox", "production"}:
        raise RuntimeError(
            "Invalid paddle_environment; expected 'sandbox' or 'production'"
        )

    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(
            f"Paddle billing enabled but missing settings: {missing_list}"
        )
    
    logger.info(f"Paddle configuration validated: API key present, webhook secret configured")
