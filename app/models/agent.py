"""Agent model."""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.billing import SubscriptionPlan
    from app.models.llm_model import LLMModel


class Agent(Base):
    """Agent/Bot model."""
    
    __tablename__ = "agents"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Prompt configuration
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_template: Mapped[Optional[str]] = mapped_column(Text)
    
    # LLM Model reference
    llm_model_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("llm_models.id", ondelete="RESTRICT"),
        nullable=False
    )
    
    # Model settings (kept for backward compatibility during migration)
    model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    temperature: Mapped[float] = mapped_column(default=0.7, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Version control
    version: Mapped[str] = mapped_column(String(20), default="1.0.0", nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Relationships - plans that include this agent
    plans: Mapped[List["SubscriptionPlan"]] = relationship(
        "SubscriptionPlan",
        secondary="plan_agents",
        back_populates="agents",
        lazy="selectin"
    )
    
    # Relationship to LLM Model
    llm_model: Mapped["LLMModel"] = relationship("LLMModel", lazy="selectin")
    
    def __repr__(self) -> str:
        return f"<Agent(id={self.id}, name={self.name}, version={self.version})>"
