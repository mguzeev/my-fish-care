"""Usage tracking model."""
from datetime import datetime
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class UsageRecord(Base):
    """Usage record model for tracking API usage."""
    
    __tablename__ = "usage_records"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Request info
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)  # telegram, web, api
    
    # LLM usage
    model_name: Mapped[Optional[str]] = mapped_column(String(100))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Performance
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Cost
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.000000"), nullable=False)
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # Metadata (column name preserved as 'metadata')
    meta: Mapped[Optional[str]] = mapped_column("metadata", Text)  # JSON string
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="usage_records")
    
    def __repr__(self) -> str:
        return f"<UsageRecord(id={self.id}, user_id={self.user_id}, endpoint={self.endpoint})>"
