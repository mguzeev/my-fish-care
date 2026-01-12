"""Billing models."""
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, ForeignKey, Numeric, Enum as SQLEnum, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum
from app.core.database import Base


# Association table for Plan <-> Agent many-to-many relationship
plan_agents = Table(
    "plan_agents",
    Base.metadata,
    Column("plan_id", Integer, ForeignKey("subscription_plans.id", ondelete="CASCADE"), primary_key=True),
    Column("agent_id", Integer, ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
)


class SubscriptionInterval(str, Enum):
    """Subscription interval enum."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionStatus(str, Enum):
    """Subscription status enum."""
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"
    EXPIRED = "expired"


class SubscriptionPlan(Base):
    """Subscription plan model."""
    
    __tablename__ = "subscription_plans"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # Daily, Weekly, Monthly, Yearly
    interval: Mapped[SubscriptionInterval] = mapped_column(
        SQLEnum(SubscriptionInterval, native_enum=False), nullable=False
    )
    
    # Pricing
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    
    # Limits
    max_requests_per_interval: Mapped[int] = mapped_column(Integer, nullable=False)
    max_tokens_per_request: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    
    # Features
    has_api_access: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_priority_support: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_advanced_analytics: Mapped[bool] = mapped_column(default=False, nullable=False)
    
    # Paddle
    paddle_price_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    paddle_product_id: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Relationships - agents included in this plan
    agents: Mapped[List["Agent"]] = relationship(
        "Agent",
        secondary=plan_agents,
        back_populates="plans",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<SubscriptionPlan(id={self.id}, name={self.name}, interval={self.interval})>"


class BillingAccount(Base):
    """Billing account model."""
    
    __tablename__ = "billing_accounts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    
    # Paddle
    paddle_customer_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    paddle_subscription_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    
    # Current subscription
    subscription_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("subscription_plans.id", ondelete="SET NULL")
    )
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        SQLEnum(SubscriptionStatus, native_enum=False), default=SubscriptionStatus.TRIALING, nullable=False
    )
    
    # Subscription dates
    subscription_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    subscription_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    trial_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Balance and usage
    balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_spent: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="billing_account")
    subscription_plan: Mapped[Optional["SubscriptionPlan"]] = relationship("SubscriptionPlan")
    
    def __repr__(self) -> str:
        return f"<BillingAccount(id={self.id}, organization_id={self.organization_id})>"
