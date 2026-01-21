"""LLM Model configuration."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Integer, Text, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class LLMModel(Base):
    """LLM Model configuration with API credentials."""
    
    __tablename__ = "llm_models"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)  # "gpt-4", "gpt-3.5-turbo", "claude-3"
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)  # "GPT-4 (OpenAI)"
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # "openai", "anthropic", "google"
    
    # API Configuration
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)  # Encrypted or from env
    api_base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Custom endpoint if needed
    
    # Model limits
    max_tokens_limit: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, default=8192, nullable=False)
    
    # Pricing (for cost tracking)
    cost_per_1k_input_tokens: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    cost_per_1k_output_tokens: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Capabilities
    supports_text: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<LLMModel(id={self.id}, name={self.name}, provider={self.provider})>"
