"""Configuration settings for the application."""
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    # Application
    app_name: str = "Bot Generic"
    app_version: str = "1.0.0"
    debug: bool = False
    # Base URL for API endpoints used by templates/frontend
    api_base_url: str = "https://bulletguru.com"
    
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
    paddle_api_key: Optional[str] = None
    paddle_webhook_secret: Optional[str] = None
    paddle_vendor_id: Optional[str] = None
    paddle_environment: str = "sandbox"  # sandbox or production
    
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


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
