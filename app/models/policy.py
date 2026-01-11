"""Policy model."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PolicyRule(Base):
    """Policy rule model for access control and rate limiting."""
    
    __tablename__ = "policy_rules"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # rate_limit, resource_access, quota, feature_flag
    
    # Target
    target_resource: Mapped[Optional[str]] = mapped_column(String(255))  # endpoint, agent, feature
    target_role: Mapped[Optional[str]] = mapped_column(String(50))  # user, admin, owner
    
    # Rule configuration (JSON string)
    config: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Higher priority = evaluated first
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<PolicyRule(id={self.id}, name={self.name}, type={self.rule_type})>"
