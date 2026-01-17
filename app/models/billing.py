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
    PAUSED = "paused"
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"
    EXPIRED = "expired"


class PlanType(str, Enum):
    """Plan type enum - subscription (time-based) vs one-time purchase (item-based)."""
    SUBSCRIPTION = "subscription"  # Time-based: user can use unlimited times within period
    ONE_TIME = "one_time"          # Item-based: user gets fixed count of uses, cumulative


class SubscriptionPlan(Base):
    """Subscription plan model."""
    
    __tablename__ = "subscription_plans"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # Daily, Weekly, Monthly, Yearly
    interval: Mapped[SubscriptionInterval] = mapped_column(
        SQLEnum(SubscriptionInterval, native_enum=False), nullable=False
    )
    
    # Plan type: subscription (time-based) or one-time purchase (item-based)
    plan_type: Mapped[PlanType] = mapped_column(
        SQLEnum(PlanType, native_enum=False), default=PlanType.SUBSCRIPTION, nullable=False
    )
    
    # Pricing
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    
    # For ONE_TIME plans: total number of items/uses user gets
    one_time_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Limits
    max_requests_per_interval: Mapped[int] = mapped_column(Integer, nullable=False)
    max_tokens_per_request: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    
    # Free trial limits
    free_requests_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    free_trial_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
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
    last_webhook_event_id: Mapped[Optional[str]] = mapped_column(String(150), index=True)
    last_transaction_id: Mapped[Optional[str]] = mapped_column(String(150))
    
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
    next_billing_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # For ONE_TIME purchases: cumulative count of items/uses purchased
    one_time_purchases_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Balance and usage
    balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_spent: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    
    # Usage tracking
    free_requests_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests_used_current_period: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    trial_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
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

class WebhookEventStatus(str, Enum):
    """Webhook processing status."""
    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"
    SKIPPED = "skipped"  # Duplicate or unsupported


class PaddleWebhookEvent(Base):
    """Log of Paddle webhook events for audit and troubleshooting."""
    
    __tablename__ = "paddle_webhook_events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    
    # Webhook identifiers
    paddle_event_id: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)  # subscription.created, etc
    
    # Related IDs
    paddle_subscription_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    paddle_customer_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    paddle_transaction_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    
    # Local reference
    billing_account_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("billing_accounts.id", ondelete="SET NULL"), index=True
    )
    
    # Processing
    status: Mapped[WebhookEventStatus] = mapped_column(
        SQLEnum(WebhookEventStatus, native_enum=False), default=WebhookEventStatus.RECEIVED, nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Signature verification
    signature_valid: Mapped[bool] = mapped_column(default=False, nullable=False)
    signature_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Payload
    payload_json: Mapped[str] = mapped_column(String(10000), nullable=False)  # Full webhook payload
    
    # Timestamps
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    def __repr__(self) -> str:
        return f"<PaddleWebhookEvent(id={self.id}, event_id={self.paddle_event_id}, type={self.event_type})>"