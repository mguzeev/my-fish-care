"""Admin API routes for SaaS management."""
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.models.billing import BillingAccount, SubscriptionPlan, SubscriptionStatus, PaddleWebhookEvent, WebhookEventStatus
from app.models.usage import UsageRecord
from app.models.policy import PolicyRule
from app.models.prompt import PromptVersion
from app.models.agent import Agent
from app.models.llm_model import LLMModel


router = APIRouter(prefix="/admin", tags=["Admin"])


async def require_admin(user: User = Depends(get_current_active_user)) -> None:
    """Dependency to require admin role."""
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )


# ============================================================================
# Dashboard & Statistics
# ============================================================================

class DashboardStats(BaseModel):
    total_users: int
    total_organizations: int
    active_subscriptions: int
    revenue_today: Decimal
    revenue_month: Decimal
    api_requests_today: int
    api_requests_month: int


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get admin dashboard statistics."""
    today = datetime.utcnow().date()
    month_start = (datetime.utcnow().replace(day=1)).date()
    
    # Total users and orgs
    users_result = await db.execute(select(func.count(User.id)))
    total_users = users_result.scalar() or 0
    
    orgs_result = await db.execute(select(func.count(Organization.id)))
    total_organizations = orgs_result.scalar() or 0
    
    # Active subscriptions
    active_subs = await db.execute(
        select(func.count(BillingAccount.id)).where(
            BillingAccount.subscription_status == SubscriptionStatus.ACTIVE
        )
    )
    active_subscriptions = active_subs.scalar() or 0
    
    # Revenue (today and month)
    revenue_today_result = await db.execute(
        select(func.coalesce(func.sum(BillingAccount.total_spent), Decimal("0.0"))).where(
            func.date(BillingAccount.updated_at) == today
        )
    )
    revenue_today = revenue_today_result.scalar() or Decimal("0.0")
    
    revenue_month_result = await db.execute(
        select(func.coalesce(func.sum(BillingAccount.total_spent), Decimal("0.0"))).where(
            func.date(BillingAccount.updated_at) >= month_start
        )
    )
    revenue_month = revenue_month_result.scalar() or Decimal("0.0")
    
    # API requests (today and month)
    requests_today_result = await db.execute(
        select(func.count(UsageRecord.id)).where(
            func.date(UsageRecord.created_at) == today
        )
    )
    api_requests_today = requests_today_result.scalar() or 0
    
    requests_month_result = await db.execute(
        select(func.count(UsageRecord.id)).where(
            func.date(UsageRecord.created_at) >= month_start
        )
    )
    api_requests_month = requests_month_result.scalar() or 0
    
    return DashboardStats(
        total_users=total_users,
        total_organizations=total_organizations,
        active_subscriptions=active_subscriptions,
        revenue_today=revenue_today,
        revenue_month=revenue_month,
        api_requests_today=api_requests_today,
        api_requests_month=api_requests_month,
    )


# ============================================================================
# Users Management
# ============================================================================

class UserResponse(BaseModel):
    id: int
    email: str
    username: Optional[str]
    full_name: Optional[str]
    is_active: bool
    is_verified: bool
    is_superuser: bool
    created_at: datetime
    last_login_at: Optional[datetime]
    telegram_id: Optional[int]
    telegram_username: Optional[str]


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """List all users."""
    result = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    users = result.scalars().all()
    
    return [
        UserResponse(
            id=u.id,
            email=u.email,
            username=u.username,
            full_name=u.full_name,
            is_active=u.is_active,
            is_verified=u.is_verified,
            is_superuser=u.is_superuser,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
            telegram_id=u.telegram_id,
            telegram_username=u.telegram_username,
        )
        for u in users
    ]


# ============================================================================
# Subscriptions Management
# ============================================================================

class SubscriptionResponse(BaseModel):
    id: int
    organization_id: int
    organization_name: str
    user_count: int = 0
    plan_name: Optional[str]
    plan_id: Optional[int] = None  # Added for plan selection in edit
    status: str
    paddle_subscription_id: Optional[str]
    total_spent: Decimal
    created_at: datetime
    updated_at: datetime


class BillingAccountDetailedResponse(BaseModel):
    """Detailed billing account information including Paddle details."""
    id: int
    organization_id: int
    organization_name: str
    user_count: int
    user_email: Optional[str]  # Primary contact email
    
    # Subscription info
    plan_name: Optional[str]
    plan_id: Optional[int]
    status: str
    
    # Paddle info
    paddle_customer_id: Optional[str]
    paddle_subscription_id: Optional[str]
    last_webhook_event_id: Optional[str]
    last_transaction_id: Optional[str]
    
    # Dates
    subscription_start_date: Optional[datetime]
    subscription_end_date: Optional[datetime]
    trial_end_date: Optional[datetime]
    next_billing_date: Optional[datetime]
    cancelled_at: Optional[datetime]
    trial_started_at: Optional[datetime]
    
    # Financial
    balance: Decimal
    total_spent: Decimal
    
    # Usage tracking
    free_requests_used: int
    requests_used_current_period: int
    period_started_at: Optional[datetime]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime


class BillingAccountFilterRequest(BaseModel):
    """Filter parameters for billing accounts."""
    status: Optional[str] = None  # active, canceled, trialing, past_due
    plan_id: Optional[int] = None
    organization_id: Optional[int] = None
    has_paddle: Optional[bool] = None  # True: has paddle_subscription_id, False: doesn't


@router.get("/subscriptions", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """List all subscriptions (billing accounts)."""
    # Get all billing accounts with their organizations and plans
    result = await db.execute(
        select(BillingAccount, Organization, SubscriptionPlan)
        .join(Organization, BillingAccount.organization_id == Organization.id)
        .outerjoin(SubscriptionPlan, BillingAccount.subscription_plan_id == SubscriptionPlan.id)
        .order_by(BillingAccount.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()
    
    # Count users for each organization
    subscriptions = []
    for billing, org, plan in rows:
        user_count_result = await db.execute(
            select(func.count(User.id)).where(User.organization_id == org.id)
        )
        user_count = user_count_result.scalar() or 0
        
        subscriptions.append(
            SubscriptionResponse(
                id=billing.id,
                organization_id=billing.organization_id,
                organization_name=org.name,
                user_count=user_count,
                plan_name=plan.name if plan else None,
                plan_id=plan.id if plan else None,
                status=billing.subscription_status.value,
                paddle_subscription_id=billing.paddle_subscription_id,
                total_spent=billing.total_spent,
                created_at=billing.created_at,
                updated_at=billing.updated_at,
            )
        )
    
    return subscriptions


@router.get("/subscriptions/{billing_account_id}/details", response_model=BillingAccountDetailedResponse)
async def get_billing_account_details(
    billing_account_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information about a billing account including Paddle data."""
    result = await db.execute(
        select(BillingAccount, Organization, SubscriptionPlan)
        .join(Organization, BillingAccount.organization_id == Organization.id)
        .outerjoin(SubscriptionPlan, BillingAccount.subscription_plan_id == SubscriptionPlan.id)
        .where(BillingAccount.id == billing_account_id)
    )
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(status_code=404, detail="Billing account not found")
    
    billing, org, plan = row
    
    # Count users in organization
    user_count_result = await db.execute(
        select(func.count(User.id)).where(User.organization_id == org.id)
    )
    user_count = user_count_result.scalar() or 0
    
    # Get primary contact email (first user in org or org creator)
    user_result = await db.execute(
        select(User.email)
        .where(User.organization_id == org.id)
        .limit(1)
    )
    user_email = user_result.scalar()
    
    return BillingAccountDetailedResponse(
        id=billing.id,
        organization_id=billing.organization_id,
        organization_name=org.name,
        user_count=user_count,
        user_email=user_email,
        plan_name=plan.name if plan else None,
        plan_id=plan.id if plan else None,
        status=billing.subscription_status.value,
        paddle_customer_id=billing.paddle_customer_id,
        paddle_subscription_id=billing.paddle_subscription_id,
        last_webhook_event_id=billing.last_webhook_event_id,
        last_transaction_id=billing.last_transaction_id,
        subscription_start_date=billing.subscription_start_date,
        subscription_end_date=billing.subscription_end_date,
        trial_end_date=billing.trial_end_date,
        next_billing_date=billing.next_billing_date,
        cancelled_at=billing.cancelled_at,
        trial_started_at=billing.trial_started_at,
        balance=billing.balance,
        total_spent=billing.total_spent,
        free_requests_used=billing.free_requests_used,
        requests_used_current_period=billing.requests_used_current_period,
        period_started_at=billing.period_started_at,
        created_at=billing.created_at,
        updated_at=billing.updated_at,
    )


@router.get("/subscriptions/filter", response_model=list[SubscriptionResponse])
async def filter_billing_accounts(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    plan_id: Optional[int] = Query(None),
    organization_id: Optional[int] = Query(None),
    has_paddle: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Filter billing accounts by various criteria."""
    query = select(BillingAccount, Organization, SubscriptionPlan).join(
        Organization, BillingAccount.organization_id == Organization.id
    ).outerjoin(
        SubscriptionPlan, BillingAccount.subscription_plan_id == SubscriptionPlan.id
    )
    
    # Apply filters
    filters = []
    if status:
        from app.models.billing import SubscriptionStatus
        try:
            status_enum = SubscriptionStatus(status)
            filters.append(BillingAccount.subscription_status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    if plan_id:
        filters.append(BillingAccount.subscription_plan_id == plan_id)
    
    if organization_id:
        filters.append(BillingAccount.organization_id == organization_id)
    
    if has_paddle is not None:
        if has_paddle:
            filters.append(BillingAccount.paddle_subscription_id != None)
        else:
            filters.append(BillingAccount.paddle_subscription_id == None)
    
    if filters:
        query = query.where(and_(*filters))
    
    # Order and pagination
    query = query.order_by(BillingAccount.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    rows = result.all()
    
    subscriptions = []
    for billing, org, plan in rows:
        user_count_result = await db.execute(
            select(func.count(User.id)).where(User.organization_id == org.id)
        )
        user_count = user_count_result.scalar() or 0
        
        subscriptions.append(
            SubscriptionResponse(
                id=billing.id,
                organization_id=billing.organization_id,
                organization_name=org.name,
                user_count=user_count,
                plan_name=plan.name if plan else None,
                plan_id=plan.id if plan else None,
                status=billing.subscription_status.value,
                paddle_subscription_id=billing.paddle_subscription_id,
                total_spent=billing.total_spent,
                created_at=billing.created_at,
                updated_at=billing.updated_at,
            )
        )
    
    return subscriptions


# ============================================================================
# Subscription Plans Management
# ============================================================================

class SubscriptionPlanResponse(BaseModel):
    id: int
    name: str
    interval: str
    price: Decimal
    currency: str
    max_requests_per_interval: int
    max_tokens_per_request: int
    free_requests_limit: int
    free_trial_days: int
    has_api_access: bool
    has_priority_support: bool
    has_advanced_analytics: bool
    paddle_price_id: Optional[str] = None
    paddle_product_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CreateSubscriptionPlanRequest(BaseModel):
    name: str
    interval: str  # DAILY, WEEKLY, MONTHLY, YEARLY
    price: Decimal
    currency: str = "USD"
    max_requests_per_interval: int
    max_tokens_per_request: int
    free_requests_limit: int = 0
    free_trial_days: int = 0
    has_api_access: bool = False
    has_priority_support: bool = False
    has_advanced_analytics: bool = False
    paddle_price_id: Optional[str] = None
    paddle_product_id: Optional[str] = None


@router.get("/plans", response_model=list[SubscriptionPlanResponse])
async def list_subscription_plans(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all subscription plans."""
    result = await db.execute(select(SubscriptionPlan))
    plans = result.scalars().all()
    return [
        SubscriptionPlanResponse(
            id=p.id,
            name=p.name,
            interval=p.interval.value,
            price=p.price,
            currency=p.currency,
            max_requests_per_interval=p.max_requests_per_interval,
            max_tokens_per_request=p.max_tokens_per_request,
            free_requests_limit=p.free_requests_limit,
            free_trial_days=p.free_trial_days,
            has_api_access=p.has_api_access,
            has_priority_support=p.has_priority_support,
            has_advanced_analytics=p.has_advanced_analytics,
            paddle_price_id=p.paddle_price_id,
            paddle_product_id=p.paddle_product_id,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in plans
    ]


@router.post("/plans", response_model=SubscriptionPlanResponse)
async def create_subscription_plan(
    request: CreateSubscriptionPlanRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create new subscription plan."""
    from app.models.billing import SubscriptionInterval
    
    plan = SubscriptionPlan(
        name=request.name,
        interval=SubscriptionInterval(request.interval),
        price=request.price,
        currency=request.currency,
        max_requests_per_interval=request.max_requests_per_interval,
        max_tokens_per_request=request.max_tokens_per_request,
        free_requests_limit=request.free_requests_limit,
        free_trial_days=request.free_trial_days,
        has_api_access=request.has_api_access,
        has_priority_support=request.has_priority_support,
        has_advanced_analytics=request.has_advanced_analytics,
        paddle_price_id=request.paddle_price_id,
        paddle_product_id=request.paddle_product_id,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    
    return SubscriptionPlanResponse(
        id=plan.id,
        name=plan.name,
        interval=plan.interval.value,
        price=plan.price,
        currency=plan.currency,
        max_requests_per_interval=plan.max_requests_per_interval,
        max_tokens_per_request=plan.max_tokens_per_request,
        free_requests_limit=plan.free_requests_limit,
        free_trial_days=plan.free_trial_days,
        has_api_access=plan.has_api_access,
        has_priority_support=plan.has_priority_support,
        has_advanced_analytics=plan.has_advanced_analytics,
        paddle_price_id=plan.paddle_price_id,
        paddle_product_id=plan.paddle_product_id,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.get("/plans/{plan_id}", response_model=SubscriptionPlanResponse)
async def get_plan(
    plan_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get a single subscription plan by ID"""
    stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    return SubscriptionPlanResponse(
        id=plan.id,
        name=plan.name,
        interval=plan.interval.value,
        price=plan.price,
        currency=plan.currency,
        max_requests_per_interval=plan.max_requests_per_interval,
        max_tokens_per_request=plan.max_tokens_per_request,
        free_requests_limit=plan.free_requests_limit,
        free_trial_days=plan.free_trial_days,
        has_api_access=plan.has_api_access,
        has_priority_support=plan.has_priority_support,
        has_advanced_analytics=plan.has_advanced_analytics,
        paddle_price_id=plan.paddle_price_id,
        paddle_product_id=plan.paddle_product_id,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.put("/plans/{plan_id}", response_model=SubscriptionPlanResponse)
async def update_subscription_plan(
    plan_id: int,
    request: CreateSubscriptionPlanRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update subscription plan."""
    from app.models.billing import SubscriptionInterval
    
    result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    plan.name = request.name
    plan.interval = SubscriptionInterval(request.interval)
    plan.price = request.price
    plan.currency = request.currency
    plan.max_requests_per_interval = request.max_requests_per_interval
    plan.max_tokens_per_request = request.max_tokens_per_request
    plan.free_requests_limit = request.free_requests_limit
    plan.free_trial_days = request.free_trial_days
    plan.has_api_access = request.has_api_access
    plan.has_priority_support = request.has_priority_support
    plan.has_advanced_analytics = request.has_advanced_analytics
    plan.paddle_price_id = request.paddle_price_id
    plan.paddle_product_id = request.paddle_product_id
    
    await db.commit()
    await db.refresh(plan)
    
    return SubscriptionPlanResponse(
        id=plan.id,
        name=plan.name,
        interval=plan.interval.value,
        price=plan.price,
        currency=plan.currency,
        max_requests_per_interval=plan.max_requests_per_interval,
        max_tokens_per_request=plan.max_tokens_per_request,
        free_requests_limit=plan.free_requests_limit,
        free_trial_days=plan.free_trial_days,
        has_api_access=plan.has_api_access,
        has_priority_support=plan.has_priority_support,
        has_advanced_analytics=plan.has_advanced_analytics,
        paddle_price_id=plan.paddle_price_id,
        paddle_product_id=plan.paddle_product_id,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.delete("/plans/{plan_id}")
async def delete_subscription_plan(
    plan_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete subscription plan."""
    result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    await db.delete(plan)
    await db.commit()
    return {"detail": "Plan deleted"}


# ============================================================================
# Paddle Webhook Management
# ============================================================================

class WebhookEventResponse(BaseModel):
    """Webhook event details."""
    id: int
    paddle_event_id: str
    event_type: str
    paddle_subscription_id: Optional[str]
    paddle_customer_id: Optional[str]
    paddle_transaction_id: Optional[str]
    billing_account_id: Optional[int]
    status: str
    error_message: Optional[str]
    signature_valid: bool
    signature_timestamp: Optional[datetime]
    received_at: datetime
    processed_at: Optional[datetime]


class WebhookEventDetailedResponse(WebhookEventResponse):
    """Webhook event with full payload."""
    payload_json: str


@router.get("/webhooks", response_model=list[WebhookEventResponse])
async def list_webhook_events(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    event_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    billing_account_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """List Paddle webhook events with filters."""
    query = select(PaddleWebhookEvent)
    
    filters = []
    if event_type:
        filters.append(PaddleWebhookEvent.event_type == event_type)
    
    if status:
        try:
            status_enum = WebhookEventStatus(status)
            filters.append(PaddleWebhookEvent.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    if billing_account_id:
        filters.append(PaddleWebhookEvent.billing_account_id == billing_account_id)
    
    if filters:
        query = query.where(and_(*filters))
    
    query = query.order_by(PaddleWebhookEvent.received_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    events = result.scalars().all()
    
    return [
        WebhookEventResponse(
            id=e.id,
            paddle_event_id=e.paddle_event_id,
            event_type=e.event_type,
            paddle_subscription_id=e.paddle_subscription_id,
            paddle_customer_id=e.paddle_customer_id,
            paddle_transaction_id=e.paddle_transaction_id,
            billing_account_id=e.billing_account_id,
            status=e.status.value,
            error_message=e.error_message,
            signature_valid=e.signature_valid,
            signature_timestamp=e.signature_timestamp,
            received_at=e.received_at,
            processed_at=e.processed_at,
        )
        for e in events
    ]


@router.get("/webhooks/{event_id}", response_model=WebhookEventDetailedResponse)
async def get_webhook_event_details(
    event_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get full webhook event details including payload."""
    result = await db.execute(
        select(PaddleWebhookEvent).where(PaddleWebhookEvent.id == event_id)
    )
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=404, detail="Webhook event not found")
    
    return WebhookEventDetailedResponse(
        id=event.id,
        paddle_event_id=event.paddle_event_id,
        event_type=event.event_type,
        paddle_subscription_id=event.paddle_subscription_id,
        paddle_customer_id=event.paddle_customer_id,
        paddle_transaction_id=event.paddle_transaction_id,
        billing_account_id=event.billing_account_id,
        status=event.status.value,
        error_message=event.error_message,
        signature_valid=event.signature_valid,
        signature_timestamp=event.signature_timestamp,
        received_at=event.received_at,
        processed_at=event.processed_at,
        payload_json=event.payload_json,
    )


@router.get("/webhooks/stats")
async def get_webhook_stats(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get webhook processing statistics."""
    # Total webhooks
    total_result = await db.execute(select(func.count(PaddleWebhookEvent.id)))
    total = total_result.scalar() or 0
    
    # By status
    processed_result = await db.execute(
        select(func.count(PaddleWebhookEvent.id)).where(
            PaddleWebhookEvent.status == WebhookEventStatus.PROCESSED
        )
    )
    processed = processed_result.scalar() or 0
    
    failed_result = await db.execute(
        select(func.count(PaddleWebhookEvent.id)).where(
            PaddleWebhookEvent.status == WebhookEventStatus.FAILED
        )
    )
    failed = failed_result.scalar() or 0
    
    skipped_result = await db.execute(
        select(func.count(PaddleWebhookEvent.id)).where(
            PaddleWebhookEvent.status == WebhookEventStatus.SKIPPED
        )
    )
    skipped = skipped_result.scalar() or 0
    
    # Recent failures (last 24h)
    from datetime import timedelta
    day_ago = datetime.utcnow() - timedelta(days=1)
    recent_failures_result = await db.execute(
        select(func.count(PaddleWebhookEvent.id)).where(
            (PaddleWebhookEvent.status == WebhookEventStatus.FAILED) &
            (PaddleWebhookEvent.received_at >= day_ago)
        )
    )
    recent_failures = recent_failures_result.scalar() or 0
    
    # Most common event types
    event_types_result = await db.execute(
        select(
            PaddleWebhookEvent.event_type,
            func.count(PaddleWebhookEvent.id).label("count")
        )
        .group_by(PaddleWebhookEvent.event_type)
        .order_by(func.count(PaddleWebhookEvent.id).desc())
        .limit(10)
    )
    event_types = [{"event_type": row[0], "count": row[1]} for row in event_types_result.all()]
    
    return {
        "total_webhooks": total,
        "by_status": {
            "processed": processed,
            "failed": failed,
            "skipped": skipped,
            "pending": total - processed - failed - skipped,
        },
        "health": {
            "recent_failures_24h": recent_failures,
            "success_rate": f"{(processed / total * 100) if total > 0 else 0:.1f}%",
            "failure_rate": f"{(failed / total * 100) if total > 0 else 0:.1f}%",
        },
        "top_event_types": event_types
    }


@router.post("/webhooks/{event_id}/reprocess")
async def reprocess_webhook_event(
    event_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Reprocess a failed webhook event."""
    result = await db.execute(
        select(PaddleWebhookEvent).where(PaddleWebhookEvent.id == event_id)
    )
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=404, detail="Webhook event not found")
    
    if event.status != WebhookEventStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail="Only failed events can be reprocessed"
        )
    
    # NOTE: In production, this should call the actual webhook handler
    # For now, just return a message
    return {
        "status": "queued",
        "message": "Webhook reprocessing queued (manual implementation required)",
        "event_id": event_id,
        "paddle_event_id": event.paddle_event_id,
        "note": "To fully implement, integrate with webhook processing logic"
    }


# ============================================================================
# Paddle Plans Management
# ============================================================================

class PaddlePriceInfo(BaseModel):
    """Info about a Paddle price."""
    id: str
    product_id: str
    name: str
    description: Optional[str] = None
    type: str  # standard, tiered
    billing_cycle: Optional[dict] = None
    unit_price: dict  # Contains amount and currency_code


class SyncPaddlePlansResponse(BaseModel):
    """Response from syncing Paddle plans."""
    synced_count: int
    created_plans: list[int]
    updated_plans: list[int]
    skipped_plans: list[str]  # IDs of plans that couldn't be synced


class LinkPaddlePriceRequest(BaseModel):
    """Link a plan to a Paddle price."""
    plan_id: int
    paddle_price_id: str
    paddle_product_id: Optional[str] = None


@router.post("/plans/link-paddle", response_model=SubscriptionPlanResponse)
async def link_plan_to_paddle_price_body(
    request: LinkPaddlePriceRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Link a subscription plan to a Paddle price (plan_id in request body)."""
    plan_id = request.plan_id
    result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    # Check if paddle_price_id is already used by another plan
    existing = await db.execute(
        select(SubscriptionPlan).where(
            (SubscriptionPlan.paddle_price_id == request.paddle_price_id) &
            (SubscriptionPlan.id != plan_id)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="This Paddle price is already linked to another plan"
        )
    
    plan.paddle_price_id = request.paddle_price_id
    if request.paddle_product_id:
        plan.paddle_product_id = request.paddle_product_id
    
    await db.commit()
    await db.refresh(plan)
    
    return SubscriptionPlanResponse(
        id=plan.id,
        name=plan.name,
        interval=plan.interval.value,
        price=plan.price,
        currency=plan.currency,
        max_requests_per_interval=plan.max_requests_per_interval,
        max_tokens_per_request=plan.max_tokens_per_request,
        free_requests_limit=plan.free_requests_limit,
        free_trial_days=plan.free_trial_days,
        has_api_access=plan.has_api_access,
        has_priority_support=plan.has_priority_support,
        has_advanced_analytics=plan.has_advanced_analytics,
        paddle_price_id=plan.paddle_price_id,
        paddle_product_id=plan.paddle_product_id,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.post("/plans/{plan_id}/link-paddle", response_model=SubscriptionPlanResponse)
async def link_plan_to_paddle_price(
    plan_id: int,
    request: LinkPaddlePriceRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Link a subscription plan to a Paddle price."""
    result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    # Check if paddle_price_id is already used by another plan
    existing = await db.execute(
        select(SubscriptionPlan).where(
            (SubscriptionPlan.paddle_price_id == request.paddle_price_id) &
            (SubscriptionPlan.id != plan_id)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="This Paddle price is already linked to another plan"
        )
    
    plan.paddle_price_id = request.paddle_price_id
    if request.paddle_product_id:
        plan.paddle_product_id = request.paddle_product_id
    
    await db.commit()
    await db.refresh(plan)
    
    return SubscriptionPlanResponse(
        id=plan.id,
        name=plan.name,
        interval=plan.interval.value,
        price=plan.price,
        currency=plan.currency,
        max_requests_per_interval=plan.max_requests_per_interval,
        max_tokens_per_request=plan.max_tokens_per_request,
        free_requests_limit=plan.free_requests_limit,
        free_trial_days=plan.free_trial_days,
        has_api_access=plan.has_api_access,
        has_priority_support=plan.has_priority_support,
        has_advanced_analytics=plan.has_advanced_analytics,
        paddle_price_id=plan.paddle_price_id,
        paddle_product_id=plan.paddle_product_id,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.get("/paddle/validate-config")
async def validate_paddle_config(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
):
    """Validate Paddle configuration and connection."""
    from app.core.config import settings
    
    if not settings.paddle_billing_enabled:
        return {
            "status": "disabled",
            "message": "Paddle billing is disabled",
            "enabled": False,
            "environment": None,
            "vendor_id": None,
            "api_key_configured": False,
            "webhook_secret_configured": False,
            "validation_errors": []
        }
    
    # Check if required settings are present
    missing_settings = []
    if not settings.paddle_api_key:
        missing_settings.append("PADDLE_API_KEY")
    if not settings.paddle_webhook_secret:
        missing_settings.append("PADDLE_WEBHOOK_SECRET")
    
    if missing_settings:
        return {
            "status": "error",
            "message": f"Missing Paddle settings: {', '.join(missing_settings)}",
            "enabled": True,
            "environment": settings.paddle_environment,
            "vendor_id": settings.paddle_vendor_id,
            "api_key_configured": bool(settings.paddle_api_key),
            "webhook_secret_configured": bool(settings.paddle_webhook_secret),
            "validation_errors": missing_settings
        }
    
    # Try to validate by creating a client
    try:
        from app.core.paddle import PaddleClient
        client = PaddleClient()
        # If we got here, config is valid
        return {
            "status": "ok",
            "message": "Paddle configuration is valid",
            "enabled": True,
            "environment": settings.paddle_environment,
            "vendor_id": settings.paddle_vendor_id,
            "api_key_configured": bool(settings.paddle_api_key),
            "webhook_secret_configured": bool(settings.paddle_webhook_secret),
            "validation_errors": []
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to validate Paddle config: {str(e)}",
            "enabled": True,
            "environment": settings.paddle_environment,
            "vendor_id": settings.paddle_vendor_id,
            "api_key_configured": bool(settings.paddle_api_key),
            "webhook_secret_configured": bool(settings.paddle_webhook_secret),
            "validation_errors": [str(e)]
        }


@router.get("/plans/paddle/missing-price-ids")
async def get_plans_missing_paddle_prices(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get list of plans that are missing Paddle price IDs."""
    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.paddle_price_id == None)
    )
    plans = result.scalars().all()
    
    return [
        {
            "id": p.id,
            "name": p.name,
            "interval": p.interval.value,
            "price": str(p.price),
            "currency": p.currency,
        }
        for p in plans
    ]


@router.post("/plans/sync-paddle")
async def sync_plans_from_paddle(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Sync subscription plans from Paddle API."""
    from app.core.config import settings
    from app.core.paddle import PaddleClient
    
    if not settings.paddle_billing_enabled:
        raise HTTPException(
            status_code=400,
            detail="Paddle billing is not enabled"
        )
    
    try:
        client = PaddleClient()
        # Get all prices from Paddle
        prices = client.list_prices()
        
        if not prices:
            return {
                "synced_count": 0,
                "created_plans": [],
                "updated_plans": [],
                "skipped_plans": [],
                "message": "No prices found in Paddle"
            }
        
        created = []
        updated = []
        skipped = []
        
        # Process each price from Paddle
        for price in prices:
            price_id = price.get("id")
            product_id = price.get("product_id")
            
            if not price_id:
                skipped.append({"reason": "No ID", "price": str(price)})
                continue
            
            # Check if plan already exists with this paddle_price_id
            existing_plan = await db.execute(
                select(SubscriptionPlan).where(
                    SubscriptionPlan.paddle_price_id == price_id
                )
            )
            existing = existing_plan.scalar_one_or_none()
            
            if existing:
                # Just update product_id if needed
                if not existing.paddle_product_id and product_id:
                    existing.paddle_product_id = product_id
                    await db.commit()
                    updated.append(existing.id)
            else:
                # Create new plan from Paddle price
                try:
                    billing_cycle = price.get("billing_cycle") or {}
                    interval = billing_cycle.get("interval", "monthly") if billing_cycle else "monthly"
                    interval = interval.lower() if interval else "monthly"
                    
                    # Map Paddle interval to our enum
                    from app.models.billing import SubscriptionInterval
                    # Paddle uses 'month', 'year', 'week', 'day' - map to our values
                    interval_map = {
                        "month": "monthly",
                        "year": "yearly",
                        "week": "weekly",
                        "day": "daily",
                    }
                    interval = interval_map.get(interval, interval)
                    if interval not in ["daily", "weekly", "monthly", "yearly"]:
                        interval = "monthly"
                    
                    # Get price amount
                    unit_price = price.get("unit_price") or {}
                    amount = unit_price.get("amount", "0")
                    # Convert from cents/smallest unit to decimal
                    if amount:
                        amount = str(int(amount) / 100)
                    else:
                        amount = "0"
                    
                    currency = unit_price.get("currency_code", "USD")
                    # Use price name or product name
                    price_name = price.get("name") or price.get("description") or f"Plan {price_id}"
                    
                    new_plan = SubscriptionPlan(
                        name=price_name,
                        interval=SubscriptionInterval(interval),
                        price=Decimal(amount),
                        currency=currency,
                        max_requests_per_interval=1000,  # Default value
                        max_tokens_per_request=2000,  # Default value
                        paddle_price_id=price_id,
                        paddle_product_id=product_id,
                    )
                    db.add(new_plan)
                    await db.commit()
                    await db.refresh(new_plan)
                    created.append(new_plan.id)
                except Exception as e:
                    skipped.append({"reason": str(e), "price_id": price_id})
        
        return {
            "synced_count": len(created) + len(updated),
            "created_plans": created,
            "updated_plans": updated,
            "skipped_plans": skipped
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync plans from Paddle: {str(e)}"
        )


@router.post("/subscriptions/{billing_account_id}/sync-paddle")
async def sync_billing_account_from_paddle(
    billing_account_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Sync Paddle subscription data for a specific billing account."""
    from app.core.config import settings
    from app.core.paddle import PaddleClient
    from app.models.billing import SubscriptionStatus
    
    if not settings.paddle_billing_enabled:
        raise HTTPException(
            status_code=400,
            detail="Paddle billing is not enabled"
        )
    
    # Get billing account
    billing_result = await db.execute(
        select(BillingAccount).where(BillingAccount.id == billing_account_id)
    )
    billing = billing_result.scalar_one_or_none()
    if not billing:
        raise HTTPException(status_code=404, detail="Billing account not found")
    
    if not billing.paddle_subscription_id:
        return {
            "status": "skipped",
            "message": "Billing account has no Paddle subscription ID",
            "billing_account_id": billing_account_id
        }
    
    try:
        client = PaddleClient()
        # Fetch current subscription state from Paddle
        subscription_data = await client.get_subscription(billing.paddle_subscription_id)
        
        if not subscription_data:
            return {
                "status": "error",
                "message": "Failed to fetch subscription from Paddle",
                "billing_account_id": billing_account_id
            }
        
        # Update billing account with current Paddle state
        paddle_status = subscription_data.get("status", "").lower()
        
        # Map Paddle status to our enum
        status_map = {
            "active": SubscriptionStatus.ACTIVE,
            "canceled": SubscriptionStatus.CANCELED,
            "past_due": SubscriptionStatus.PAST_DUE,
            "trialing": SubscriptionStatus.TRIALING,
            "paused": SubscriptionStatus.TRIALING,  # Treat paused as trialing
        }
        
        if paddle_status in status_map:
            billing.subscription_status = status_map[paddle_status]
        
        # Update dates if available
        if subscription_data.get("next_billed_at"):
            from dateutil.parser import parse as parse_date
            billing.next_billing_date = parse_date(subscription_data.get("next_billed_at"))
        
        if subscription_data.get("cancelled_at"):
            from dateutil.parser import parse as parse_date
            billing.cancelled_at = parse_date(subscription_data.get("cancelled_at"))
        
        if subscription_data.get("started_at"):
            from dateutil.parser import parse as parse_date
            billing.subscription_start_date = parse_date(subscription_data.get("started_at"))
        
        if subscription_data.get("trial_ends_at"):
            from dateutil.parser import parse as parse_date
            billing.trial_end_date = parse_date(subscription_data.get("trial_ends_at"))
        
        await db.commit()
        await db.refresh(billing)
        
        return {
            "status": "synced",
            "message": "Successfully synced Paddle subscription data",
            "billing_account_id": billing_account_id,
            "subscription_status": billing.subscription_status.value,
            "next_billing_date": str(billing.next_billing_date) if billing.next_billing_date else None,
            "paddle_subscription_id": billing.paddle_subscription_id
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to sync from Paddle: {str(e)}",
            "billing_account_id": billing_account_id
        }


@router.get("/subscriptions/paddle/drift-detection")
async def detect_paddle_drift(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Detect drift between local and Paddle subscription states."""
    from app.core.config import settings
    from app.core.paddle import PaddleClient
    from app.models.billing import SubscriptionStatus
    
    if not settings.paddle_billing_enabled:
        raise HTTPException(
            status_code=400,
            detail="Paddle billing is not enabled"
        )
    
    try:
        # Get all billing accounts with Paddle subscriptions
        result = await db.execute(
            select(BillingAccount)
            .where(BillingAccount.paddle_subscription_id != None)
            .limit(100)  # Limit to 100 to avoid timeout
        )
        accounts = result.scalars().all()
        
        drift_detected = []
        client = PaddleClient()
        
        for account in accounts:
            try:
                subscription_data = await client.get_subscription(account.paddle_subscription_id)
                paddle_status = subscription_data.get("status", "").lower()
                
                # Check if statuses match
                local_status = account.subscription_status.value.lower()
                
                if paddle_status != local_status:
                    drift_detected.append({
                        "billing_account_id": account.id,
                        "local_status": local_status,
                        "paddle_status": paddle_status,
                        "paddle_subscription_id": account.paddle_subscription_id,
                        "organization_id": account.organization_id,
                    })
            except Exception as e:
                drift_detected.append({
                    "billing_account_id": account.id,
                    "error": str(e),
                    "paddle_subscription_id": account.paddle_subscription_id,
                })
        
        return {
            "checked_count": len(accounts),
            "drift_count": len(drift_detected),
            "drifted_accounts": drift_detected
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect drift: {str(e)}"
        )


# ============================================================================
# Paddle Reconciliation & Background Jobs
# ============================================================================

class ReconciliationRequest(BaseModel):
    """Request to reconcile specific accounts or all."""
    billing_account_ids: Optional[list[int]] = None  # None means all
    fix_drift: bool = True  # If True, fix detected drift by syncing from Paddle


class BulkSyncResponse(BaseModel):
    """Response from bulk sync operation."""
    total_processed: int
    successful: int
    failed: int
    skipped: int  # No Paddle ID
    details: list[dict]


@router.post("/subscriptions/reconcile", response_model=BulkSyncResponse)
async def reconcile_all_subscriptions(
    request: ReconciliationRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Reconcile subscriptions between local DB and Paddle API."""
    from app.core.config import settings
    from app.core.paddle import PaddleClient
    from app.models.billing import SubscriptionStatus
    
    if not settings.paddle_billing_enabled:
        raise HTTPException(
            status_code=400,
            detail="Paddle billing is not enabled"
        )
    
    try:
        # Get billing accounts to process
        query = select(BillingAccount).where(BillingAccount.paddle_subscription_id != None)
        
        if request.billing_account_ids:
            query = query.where(BillingAccount.id.in_(request.billing_account_ids))
        
        result = await db.execute(query.limit(500))  # Limit to prevent timeout
        accounts = result.scalars().all()
        
        details = []
        successful = 0
        failed = 0
        skipped = 0
        
        client = PaddleClient()
        status_map = {
            "active": SubscriptionStatus.ACTIVE,
            "canceled": SubscriptionStatus.CANCELED,
            "past_due": SubscriptionStatus.PAST_DUE,
            "trialing": SubscriptionStatus.TRIALING,
            "paused": SubscriptionStatus.TRIALING,
        }
        
        for account in accounts:
            try:
                subscription_data = await client.get_subscription(account.paddle_subscription_id)
                
                if not subscription_data:
                    details.append({
                        "billing_account_id": account.id,
                        "status": "failed",
                        "reason": "No data from Paddle"
                    })
                    failed += 1
                    continue
                
                paddle_status = subscription_data.get("status", "").lower()
                local_status = account.subscription_status.value.lower()
                
                # Check for drift
                has_drift = paddle_status != local_status
                
                if has_drift and request.fix_drift:
                    # Update to match Paddle
                    if paddle_status in status_map:
                        account.subscription_status = status_map[paddle_status]
                    
                    # Update dates
                    try:
                        from dateutil.parser import parse as parse_date
                        if subscription_data.get("next_billed_at"):
                            account.next_billing_date = parse_date(subscription_data.get("next_billed_at"))
                        if subscription_data.get("cancelled_at"):
                            account.cancelled_at = parse_date(subscription_data.get("cancelled_at"))
                        if subscription_data.get("started_at"):
                            account.subscription_start_date = parse_date(subscription_data.get("started_at"))
                    except Exception:
                        pass  # Skip date parsing if it fails
                    
                    await db.commit()
                    
                    details.append({
                        "billing_account_id": account.id,
                        "status": "fixed",
                        "previous_status": local_status,
                        "current_status": paddle_status,
                    })
                    successful += 1
                elif has_drift:
                    details.append({
                        "billing_account_id": account.id,
                        "status": "drift_detected",
                        "local_status": local_status,
                        "paddle_status": paddle_status,
                    })
                    successful += 1
                else:
                    details.append({
                        "billing_account_id": account.id,
                        "status": "synced",
                    })
                    successful += 1
            
            except Exception as e:
                details.append({
                    "billing_account_id": account.id,
                    "status": "error",
                    "error": str(e)
                })
                failed += 1
        
        return BulkSyncResponse(
            total_processed=len(accounts),
            successful=successful,
            failed=failed,
            skipped=skipped,
            details=details
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Reconciliation failed: {str(e)}"
        )


@router.post("/paddle/auto-backfill-paddle-ids")
async def backfill_paddle_ids(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Find accounts with paddle_subscription_id but no paddle_customer_id and backfill."""
    result = await db.execute(
        select(BillingAccount).where(
            (BillingAccount.paddle_subscription_id != None) &
            (BillingAccount.paddle_customer_id == None)
        )
    )
    accounts = result.scalars().all()
    
    if not accounts:
        return {
            "status": "ok",
            "message": "No accounts to backfill",
            "count": 0
        }
    
    # Note: Can't extract customer_id from subscription_id via Paddle API
    # Would need to fetch subscription details, but we don't store customer_id there
    return {
        "status": "info",
        "message": "Paddle subscription IDs found but customer IDs cannot be backfilled without Paddle API",
        "affected_count": len(accounts),
        "recommendation": "Use admin panel to manually link Paddle customer IDs or sync from Paddle"
    }


@router.get("/paddle/billing-status")
async def get_paddle_billing_status(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get overall Paddle billing status and statistics."""
    from app.core.config import settings
    
    # Count billing accounts
    total_accounts_result = await db.execute(
        select(func.count(BillingAccount.id))
    )
    total_accounts = total_accounts_result.scalar() or 0
    
    # Count accounts with Paddle subscription
    paddle_accounts_result = await db.execute(
        select(func.count(BillingAccount.id)).where(
            BillingAccount.paddle_subscription_id != None
        )
    )
    paddle_accounts = paddle_accounts_result.scalar() or 0
    
    # Count by status
    from app.models.billing import SubscriptionStatus
    active_result = await db.execute(
        select(func.count(BillingAccount.id)).where(
            BillingAccount.subscription_status == SubscriptionStatus.ACTIVE
        )
    )
    active_count = active_result.scalar() or 0
    
    canceled_result = await db.execute(
        select(func.count(BillingAccount.id)).where(
            BillingAccount.subscription_status == SubscriptionStatus.CANCELED
        )
    )
    canceled_count = canceled_result.scalar() or 0
    
    trialing_result = await db.execute(
        select(func.count(BillingAccount.id)).where(
            BillingAccount.subscription_status == SubscriptionStatus.TRIALING
        )
    )
    trialing_count = trialing_result.scalar() or 0
    
    # Revenue stats
    total_revenue_result = await db.execute(
        select(func.coalesce(func.sum(BillingAccount.total_spent), Decimal("0.0")))
    )
    total_revenue = total_revenue_result.scalar() or Decimal("0.0")
    
    # Active revenue (sum of balance for active subscriptions)
    active_revenue_result = await db.execute(
        select(func.coalesce(func.sum(BillingAccount.balance), Decimal("0.0"))).where(
            BillingAccount.subscription_status == SubscriptionStatus.ACTIVE
        )
    )
    active_revenue = active_revenue_result.scalar() or Decimal("0.0")
    
    return {
        "paddle_enabled": settings.paddle_billing_enabled,
        "total_billing_accounts": total_accounts,
        "paddle_linked_accounts": paddle_accounts,
        "paddle_coverage": f"{(paddle_accounts / total_accounts * 100) if total_accounts > 0 else 0:.1f}%",
        "subscriptions_by_status": {
            "active": active_count,
            "canceled": canceled_count,
            "trialing": trialing_count,
        },
        "revenue_metrics": {
            "total_all_time": str(total_revenue),
            "current_balance": str(active_revenue),
            "currency": "USD"
        },
        "health": {
            "missing_paddle_ids": total_accounts - paddle_accounts,
            "recommendation": "Link remaining accounts to Paddle for full billing tracking"
        }
    }


# ============================================================================
# Paddle Subscription Management (Sandbox Testing)
# ============================================================================

class SubscriptionItemRequest(BaseModel):
    """Subscription item (price + quantity)."""
    price_id: str
    quantity: int = 1


class UpdateSubscriptionItemsRequest(BaseModel):
    """Request to update subscription items."""
    items: list[SubscriptionItemRequest]
    proration_billing_mode: str = "prorated_immediately"


class AddSubscriptionItemsRequest(BaseModel):
    """Request to add items to subscription."""
    items: list[SubscriptionItemRequest]
    proration_billing_mode: str = "prorated_immediately"


class RemoveSubscriptionItemsRequest(BaseModel):
    """Request to remove items from subscription."""
    price_ids: list[str]
    proration_billing_mode: str = "prorated_immediately"


class CancelSubscriptionRequest(BaseModel):
    """Request to cancel subscription."""
    effective_from: str = "next_billing_period"  # or "immediately"


class PauseSubscriptionRequest(BaseModel):
    """Request to pause subscription."""
    effective_from: str = "next_billing_period"
    resume_at: Optional[str] = None  # ISO timestamp


class ResumeSubscriptionRequest(BaseModel):
    """Request to resume subscription."""
    effective_from: str = "immediately"


@router.post("/subscriptions/{billing_account_id}/paddle/update-items")
async def paddle_update_subscription_items(
    billing_account_id: int,
    request: UpdateSubscriptionItemsRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update subscription items via Paddle API (replace all items)."""
    from app.core.config import settings
    from app.core.paddle import PaddleClient
    
    if not settings.paddle_billing_enabled:
        raise HTTPException(status_code=400, detail="Paddle billing is not enabled")
    
    # Get billing account
    result = await db.execute(
        select(BillingAccount).where(BillingAccount.id == billing_account_id)
    )
    billing = result.scalar_one_or_none()
    if not billing:
        raise HTTPException(status_code=404, detail="Billing account not found")
    
    if not billing.paddle_subscription_id:
        raise HTTPException(
            status_code=400,
            detail="No Paddle subscription linked to this account"
        )
    
    try:
        client = PaddleClient()
        items = [{"price_id": item.price_id, "quantity": item.quantity} for item in request.items]
        
        updated_sub = await client.update_subscription(
            subscription_id=billing.paddle_subscription_id,
            items=items,
            proration_billing_mode=request.proration_billing_mode
        )
        
        return {
            "status": "success",
            "message": "Subscription items updated successfully",
            "subscription_id": billing.paddle_subscription_id,
            "paddle_status": updated_sub.get("status"),
            "items_count": len(items)
        }
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to update subscription in Paddle: {str(e)}"
        )


@router.post("/subscriptions/{billing_account_id}/paddle/add-items")
async def paddle_add_subscription_items(
    billing_account_id: int,
    request: AddSubscriptionItemsRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add items to subscription via Paddle API."""
    from app.core.config import settings
    from app.core.paddle import PaddleClient
    
    if not settings.paddle_billing_enabled:
        raise HTTPException(status_code=400, detail="Paddle billing is not enabled")
    
    result = await db.execute(
        select(BillingAccount).where(BillingAccount.id == billing_account_id)
    )
    billing = result.scalar_one_or_none()
    if not billing:
        raise HTTPException(status_code=404, detail="Billing account not found")
    
    if not billing.paddle_subscription_id:
        raise HTTPException(
            status_code=400,
            detail="No Paddle subscription linked to this account"
        )
    
    try:
        client = PaddleClient()
        items = [{"price_id": item.price_id, "quantity": item.quantity} for item in request.items]
        
        updated_sub = await client.add_subscription_items(
            subscription_id=billing.paddle_subscription_id,
            new_items=items,
            proration_billing_mode=request.proration_billing_mode
        )
        
        return {
            "status": "success",
            "message": "Items added to subscription successfully",
            "subscription_id": billing.paddle_subscription_id,
            "paddle_status": updated_sub.get("status")
        }
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to add items in Paddle: {str(e)}"
        )


@router.post("/subscriptions/{billing_account_id}/paddle/remove-items")
async def paddle_remove_subscription_items(
    billing_account_id: int,
    request: RemoveSubscriptionItemsRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Remove items from subscription via Paddle API."""
    from app.core.config import settings
    from app.core.paddle import PaddleClient
    
    if not settings.paddle_billing_enabled:
        raise HTTPException(status_code=400, detail="Paddle billing is not enabled")
    
    result = await db.execute(
        select(BillingAccount).where(BillingAccount.id == billing_account_id)
    )
    billing = result.scalar_one_or_none()
    if not billing:
        raise HTTPException(status_code=404, detail="Billing account not found")
    
    if not billing.paddle_subscription_id:
        raise HTTPException(
            status_code=400,
            detail="No Paddle subscription linked to this account"
        )
    
    try:
        client = PaddleClient()
        
        updated_sub = await client.remove_subscription_items(
            subscription_id=billing.paddle_subscription_id,
            price_ids_to_remove=request.price_ids,
            proration_billing_mode=request.proration_billing_mode
        )
        
        return {
            "status": "success",
            "message": "Items removed from subscription successfully",
            "subscription_id": billing.paddle_subscription_id,
            "paddle_status": updated_sub.get("status")
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to remove items in Paddle: {str(e)}"
        )


@router.post("/subscriptions/{billing_account_id}/paddle/cancel")
async def paddle_cancel_subscription(
    billing_account_id: int,
    request: CancelSubscriptionRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Cancel subscription via Paddle API."""
    from app.core.config import settings
    from app.core.paddle import PaddleClient
    from app.models.billing import SubscriptionStatus
    
    if not settings.paddle_billing_enabled:
        raise HTTPException(status_code=400, detail="Paddle billing is not enabled")
    
    result = await db.execute(
        select(BillingAccount).where(BillingAccount.id == billing_account_id)
    )
    billing = result.scalar_one_or_none()
    if not billing:
        raise HTTPException(status_code=404, detail="Billing account not found")
    
    if not billing.paddle_subscription_id:
        raise HTTPException(
            status_code=400,
            detail="No Paddle subscription linked to this account"
        )
    
    try:
        client = PaddleClient()
        
        canceled_sub = await client.cancel_subscription(
            subscription_id=billing.paddle_subscription_id,
            effective_from=request.effective_from
        )
        
        # Update local status if canceled immediately
        if request.effective_from == "immediately":
            billing.subscription_status = SubscriptionStatus.CANCELED
            billing.cancelled_at = datetime.utcnow()
            await db.commit()
        
        return {
            "status": "success",
            "message": f"Subscription canceled ({request.effective_from})",
            "subscription_id": billing.paddle_subscription_id,
            "paddle_status": canceled_sub.get("status"),
            "effective_from": request.effective_from
        }
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to cancel subscription in Paddle: {str(e)}"
        )


@router.post("/subscriptions/{billing_account_id}/paddle/pause")
async def paddle_pause_subscription(
    billing_account_id: int,
    request: PauseSubscriptionRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Pause subscription via Paddle API."""
    from app.core.config import settings
    from app.core.paddle import PaddleClient
    
    if not settings.paddle_billing_enabled:
        raise HTTPException(status_code=400, detail="Paddle billing is not enabled")
    
    result = await db.execute(
        select(BillingAccount).where(BillingAccount.id == billing_account_id)
    )
    billing = result.scalar_one_or_none()
    if not billing:
        raise HTTPException(status_code=404, detail="Billing account not found")
    
    if not billing.paddle_subscription_id:
        raise HTTPException(
            status_code=400,
            detail="No Paddle subscription linked to this account"
        )
    
    try:
        client = PaddleClient()
        
        paused_sub = await client.pause_subscription(
            subscription_id=billing.paddle_subscription_id,
            effective_from=request.effective_from,
            resume_at=request.resume_at
        )
        
        return {
            "status": "success",
            "message": f"Subscription paused ({request.effective_from})",
            "subscription_id": billing.paddle_subscription_id,
            "paddle_status": paused_sub.get("status"),
            "resume_at": request.resume_at or "Manual resume required"
        }
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to pause subscription in Paddle: {str(e)}"
        )


@router.post("/subscriptions/{billing_account_id}/paddle/resume")
async def paddle_resume_subscription(
    billing_account_id: int,
    request: ResumeSubscriptionRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Resume paused subscription via Paddle API."""
    from app.core.config import settings
    from app.core.paddle import PaddleClient
    
    if not settings.paddle_billing_enabled:
        raise HTTPException(status_code=400, detail="Paddle billing is not enabled")
    
    result = await db.execute(
        select(BillingAccount).where(BillingAccount.id == billing_account_id)
    )
    billing = result.scalar_one_or_none()
    if not billing:
        raise HTTPException(status_code=404, detail="Billing account not found")
    
    if not billing.paddle_subscription_id:
        raise HTTPException(
            status_code=400,
            detail="No Paddle subscription linked to this account"
        )
    
    try:
        client = PaddleClient()
        
        resumed_sub = await client.resume_subscription(
            subscription_id=billing.paddle_subscription_id,
            effective_from=request.effective_from
        )
        
        return {
            "status": "success",
            "message": f"Subscription resumed ({request.effective_from})",
            "subscription_id": billing.paddle_subscription_id,
            "paddle_status": resumed_sub.get("status")
        }
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to resume subscription in Paddle: {str(e)}"
        )


@router.get("/subscriptions/{billing_account_id}/paddle/items")
async def get_paddle_subscription_items(
    billing_account_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get current subscription items from Paddle API."""
    from app.core.config import settings
    from app.core.paddle import PaddleClient
    
    if not settings.paddle_billing_enabled:
        raise HTTPException(status_code=400, detail="Paddle billing is not enabled")
    
    result = await db.execute(
        select(BillingAccount).where(BillingAccount.id == billing_account_id)
    )
    billing = result.scalar_one_or_none()
    if not billing:
        raise HTTPException(status_code=404, detail="Billing account not found")
    
    if not billing.paddle_subscription_id:
        raise HTTPException(
            status_code=400,
            detail="No Paddle subscription linked to this account"
        )
    
    try:
        client = PaddleClient()
        subscription = await client.get_subscription(billing.paddle_subscription_id)
        
        items = subscription.get("items", [])
        formatted_items = []
        
        for item in items:
            price = item.get("price", {})
            price_id = price.get("id") if isinstance(price, dict) else item.get("price_id")
            
            formatted_items.append({
                "price_id": price_id,
                "quantity": item.get("quantity", 1),
                "status": item.get("status"),
                "product_name": price.get("product", {}).get("name") if isinstance(price, dict) else None,
                "unit_price": price.get("unit_price") if isinstance(price, dict) else None
            })
        
        return {
            "subscription_id": billing.paddle_subscription_id,
            "status": subscription.get("status"),
            "items": formatted_items,
            "billing_cycle": subscription.get("billing_cycle"),
            "next_billed_at": subscription.get("next_billed_at")
        }
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch subscription from Paddle: {str(e)}"
        )


@router.post("/plans/{plan_id}/agents/{agent_id}")

async def add_agent_to_plan(
    plan_id: int,
    agent_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add an agent to a subscription plan."""
    from app.models.agent import Agent
    
    plan_result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Check if already added
    if agent not in plan.agents:
        plan.agents.append(agent)
        await db.commit()
    
    return {"detail": "Agent added to plan", "plan_id": plan_id, "agent_id": agent_id}


@router.delete("/plans/{plan_id}/agents/{agent_id}")
async def remove_agent_from_plan(
    plan_id: int,
    agent_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Remove an agent from a subscription plan."""
    from app.models.agent import Agent
    
    plan_result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if agent in plan.agents:
        plan.agents.remove(agent)
        await db.commit()
    
    return {"detail": "Agent removed from plan", "plan_id": plan_id, "agent_id": agent_id}


@router.get("/plans/{plan_id}/agents", response_model=list[int])
async def get_plan_agents(
    plan_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get list of agent IDs included in a plan."""
    plan_result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    return [agent.id for agent in plan.agents]


# ============================================================================
# Policy Rules Management
# ============================================================================

class PolicyRuleResponse(BaseModel):
    id: int
    name: str
    rule_type: str
    target_resource: str
    target_role: str
    config: dict
    is_active: bool
    priority: int


class CreatePolicyRuleRequest(BaseModel):
    name: str
    rule_type: str  # rate_limit, resource_access
    target_resource: str
    target_role: str  # user, admin, owner
    config: dict
    is_active: bool = True
    priority: int = 10


@router.get("/policies", response_model=list[PolicyRuleResponse])
async def list_policy_rules(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all policy rules."""
    result = await db.execute(select(PolicyRule))
    rules = result.scalars().all()
    import json
    return [
        PolicyRuleResponse(
            id=r.id,
            name=r.name,
            rule_type=r.rule_type,
            target_resource=r.target_resource,
            target_role=r.target_role,
            config=json.loads(r.config) if isinstance(r.config, str) else r.config,
            is_active=r.is_active,
            priority=r.priority,
        )
        for r in rules
    ]


@router.post("/policies", response_model=PolicyRuleResponse)
async def create_policy_rule(
    request: CreatePolicyRuleRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create new policy rule."""
    import json
    
    rule = PolicyRule(
        name=request.name,
        rule_type=request.rule_type,
        target_resource=request.target_resource,
        target_role=request.target_role,
        config=json.dumps(request.config),
        is_active=request.is_active,
        priority=request.priority,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    
    return PolicyRuleResponse(
        id=rule.id,
        name=rule.name,
        rule_type=rule.rule_type,
        target_resource=rule.target_resource,
        target_role=rule.target_role,
        config=json.loads(rule.config),
        is_active=rule.is_active,
        priority=rule.priority,
    )


@router.put("/policies/{policy_id}", response_model=PolicyRuleResponse)
async def update_policy_rule(
    policy_id: int,
    request: CreatePolicyRuleRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update policy rule."""
    import json
    
    result = await db.execute(select(PolicyRule).where(PolicyRule.id == policy_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    
    rule.name = request.name
    rule.rule_type = request.rule_type
    rule.target_resource = request.target_resource
    rule.target_role = request.target_role
    rule.config = json.dumps(request.config)
    rule.is_active = request.is_active
    rule.priority = request.priority
    
    await db.commit()
    await db.refresh(rule)
    
    return PolicyRuleResponse(
        id=rule.id,
        name=rule.name,
        rule_type=rule.rule_type,
        target_resource=rule.target_resource,
        target_role=rule.target_role,
        config=json.loads(rule.config),
        is_active=rule.is_active,
        priority=rule.priority,
    )


@router.delete("/policies/{policy_id}")
async def delete_policy_rule(
    policy_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete policy rule."""
    result = await db.execute(select(PolicyRule).where(PolicyRule.id == policy_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    
    await db.delete(rule)
    await db.commit()
    return {"detail": "Policy rule deleted"}


# ============================================================================
# Prompt Versions Management
# ============================================================================


class PromptVersionResponse(BaseModel):
    id: int
    agent_id: int
    name: str
    version: str
    system_prompt: str
    user_template: str
    variables: list[dict]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreatePromptVersionRequest(BaseModel):
    name: str
    version: str = "1.0.0"
    system_prompt: str
    user_template: str
    variables: list[dict] = Field(default_factory=list)
    is_active: bool = True


def _parse_variables(raw: str) -> list[dict]:
    try:
        return json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []


def _dump_variables(variables: list[dict]) -> str:
    return json.dumps(variables or [])


async def _ensure_single_active(agent_id: int, db: AsyncSession, active_prompt_id: int) -> None:
    await db.execute(
        update(PromptVersion)
        .where(
            and_(
                PromptVersion.agent_id == agent_id,
                PromptVersion.id != active_prompt_id,
            )
        )
        .values(is_active=False)
    )


@router.get("/agents/{agent_id}/prompts", response_model=list[PromptVersionResponse])
async def list_agent_prompts(
    agent_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List prompt versions for an agent."""
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await db.execute(
        select(PromptVersion)
        .where(PromptVersion.agent_id == agent_id)
        .order_by(PromptVersion.updated_at.desc())
    )
    prompts = result.scalars().all()
    return [
        PromptVersionResponse(
            id=p.id,
            agent_id=p.agent_id,
            name=p.name,
            version=p.version,
            system_prompt=p.system_prompt,
            user_template=p.user_template,
            variables=_parse_variables(p.variables_json),
            is_active=p.is_active,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in prompts
    ]


@router.post("/agents/{agent_id}/prompts", response_model=PromptVersionResponse)
async def create_prompt_version(
    agent_id: int,
    request: CreatePromptVersionRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new prompt version for an agent."""
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    prompt = PromptVersion(
        agent_id=agent.id,
        name=request.name,
        version=request.version,
        system_prompt=request.system_prompt,
        user_template=request.user_template,
        variables_json=_dump_variables(request.variables),
        is_active=request.is_active,
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)

    if prompt.is_active:
        await _ensure_single_active(agent.id, db, prompt.id)
        await db.commit()

    return PromptVersionResponse(
        id=prompt.id,
        agent_id=prompt.agent_id,
        name=prompt.name,
        version=prompt.version,
        system_prompt=prompt.system_prompt,
        user_template=prompt.user_template,
        variables=_parse_variables(prompt.variables_json),
        is_active=prompt.is_active,
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
    )


@router.put("/prompts/{prompt_id}", response_model=PromptVersionResponse)
async def update_prompt_version(
    prompt_id: int,
    request: CreatePromptVersionRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing prompt version."""
    result = await db.execute(select(PromptVersion).where(PromptVersion.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    prompt.name = request.name
    prompt.version = request.version
    prompt.system_prompt = request.system_prompt
    prompt.user_template = request.user_template
    prompt.variables_json = _dump_variables(request.variables)
    prompt.is_active = request.is_active

    await db.commit()
    await db.refresh(prompt)

    if prompt.is_active:
        await _ensure_single_active(prompt.agent_id, db, prompt.id)
        await db.commit()

    return PromptVersionResponse(
        id=prompt.id,
        agent_id=prompt.agent_id,
        name=prompt.name,
        version=prompt.version,
        system_prompt=prompt.system_prompt,
        user_template=prompt.user_template,
        variables=_parse_variables(prompt.variables_json),
        is_active=prompt.is_active,
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
    )


@router.post("/prompts/{prompt_id}/activate", response_model=PromptVersionResponse)
async def activate_prompt_version(
    prompt_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mark a prompt version as active and deactivate others for the agent."""
    result = await db.execute(select(PromptVersion).where(PromptVersion.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    prompt.is_active = True
    await db.commit()
    await _ensure_single_active(prompt.agent_id, db, prompt.id)
    await db.commit()
    await db.refresh(prompt)

    return PromptVersionResponse(
        id=prompt.id,
        agent_id=prompt.agent_id,
        name=prompt.name,
        version=prompt.version,
        system_prompt=prompt.system_prompt,
        user_template=prompt.user_template,
        variables=_parse_variables(prompt.variables_json),
        is_active=prompt.is_active,
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
    )


@router.delete("/prompts/{prompt_id}")
async def delete_prompt_version(
    prompt_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a prompt version."""
    result = await db.execute(select(PromptVersion).where(PromptVersion.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    await db.delete(prompt)
    await db.commit()
    return {"detail": "Prompt deleted"}


# ============================================================================
# Agent Management
# ============================================================================

class AgentResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    system_prompt: str
    model_name: str
    llm_model_id: int  # Added for frontend to select correct model
    temperature: float
    max_tokens: int
    is_active: bool
    is_public: bool
    version: str
    created_at: datetime
    updated_at: datetime

class AgentListResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    model_name: str
    is_active: bool
    created_at: datetime


class CreateAgentRequest(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    system_prompt: str = "You are a helpful assistant"
    llm_model_id: int
    model_name: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 2000
    is_active: bool = True
    is_public: bool = False


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_model_id: Optional[int] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None


@router.get("/agents", response_model=list[AgentListResponse])
async def list_agents(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    active_only: bool = Query(False),
):
    """List all agents."""
    query = select(Agent)
    if active_only:
        query = query.where(Agent.is_active == True)
    query = query.order_by(Agent.created_at.desc())
    
    result = await db.execute(query)
    agents = result.scalars().all()
    
    return [
        AgentListResponse(
            id=a.id,
            name=a.name,
            slug=a.slug,
            description=a.description,
            model_name=a.model_name,
            is_active=a.is_active,
            created_at=a.created_at,
        )
        for a in agents
    ]


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get agent details."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        slug=agent.slug,
        description=agent.description,
        system_prompt=agent.system_prompt,
        model_name=agent.model_name,
        llm_model_id=agent.llm_model_id,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        is_active=agent.is_active,
        is_public=agent.is_public,
        version=agent.version,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.post("/agents", response_model=AgentResponse)
async def create_agent(
    request: CreateAgentRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create new agent."""
    # Check if slug already exists
    existing = await db.execute(select(Agent).where(Agent.slug == request.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Agent with this slug already exists")
    
    agent = Agent(
        name=request.name,
        slug=request.slug,
        description=request.description,
        system_prompt=request.system_prompt,
        llm_model_id=request.llm_model_id,
        model_name=request.model_name,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        is_active=request.is_active,
        is_public=request.is_public,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        slug=agent.slug,
        description=agent.description,
        system_prompt=agent.system_prompt,
        model_name=agent.model_name,
        llm_model_id=agent.llm_model_id,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        is_active=agent.is_active,
        is_public=agent.is_public,
        version=agent.version,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.put("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: int,
    request: UpdateAgentRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update agent."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if request.name is not None:
        agent.name = request.name
    if request.description is not None:
        agent.description = request.description
    if request.system_prompt is not None:
        agent.system_prompt = request.system_prompt
    if request.llm_model_id is not None:
        agent.llm_model_id = request.llm_model_id
    if request.model_name is not None:
        agent.model_name = request.model_name
    if request.temperature is not None:
        agent.temperature = request.temperature
    if request.max_tokens is not None:
        agent.max_tokens = request.max_tokens
    if request.is_active is not None:
        agent.is_active = request.is_active
    if request.is_public is not None:
        agent.is_public = request.is_public
    
    await db.commit()
    await db.refresh(agent)
    
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        slug=agent.slug,
        description=agent.description,
        system_prompt=agent.system_prompt,
        model_name=agent.model_name,
        llm_model_id=agent.llm_model_id,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        is_active=agent.is_active,
        is_public=agent.is_public,
        version=agent.version,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete agent (soft delete - mark as inactive)."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent.is_active = False
    await db.commit()
    
    return {"detail": "Agent deleted"}


# ============================================================================
# User Activity & Monitoring
# ============================================================================

class UserActivityResponse(BaseModel):
    user_id: int
    user_email: str
    organization_id: int
    requests_today: int
    requests_month: int
    tokens_today: int
    tokens_month: int
    cost_today: Decimal
    cost_month: Decimal


@router.get("/users/activity", response_model=list[UserActivityResponse])
async def get_user_activity(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=90),
):
    """Get user activity metrics."""
    today = datetime.utcnow().date()
    month_start = (datetime.utcnow().replace(day=1)).date()
    
    # Get all users
    users_result = await db.execute(select(User))
    users = users_result.scalars().all()
    
    activity_list = []
    for user in users:
        # Today stats
        today_result = await db.execute(
            select(
                func.count(UsageRecord.id),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0),
                func.coalesce(func.sum(UsageRecord.cost), Decimal("0.0")),
            ).where(
                (UsageRecord.user_id == user.id)
                & (func.date(UsageRecord.created_at) == today)
            )
        )
        today_data = today_result.one()
        
        # Month stats
        month_result = await db.execute(
            select(
                func.count(UsageRecord.id),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0),
                func.coalesce(func.sum(UsageRecord.cost), Decimal("0.0")),
            ).where(
                (UsageRecord.user_id == user.id)
                & (func.date(UsageRecord.created_at) >= month_start)
            )
        )
        month_data = month_result.one()
        
        activity_list.append(
            UserActivityResponse(
                user_id=user.id,
                user_email=user.email,
                organization_id=user.organization_id or 0,
                requests_today=int(today_data[0]),
                requests_month=int(month_data[0]),
                tokens_today=int(today_data[1] or 0),
                tokens_month=int(month_data[1] or 0),
                cost_today=today_data[2] or Decimal("0.0"),
                cost_month=month_data[2] or Decimal("0.0"),
            )
        )
    
    return activity_list


# ============================================================================
# Organization Management
# ============================================================================

class OrganizationResponse(BaseModel):
    id: int
    name: str
    slug: str
    member_count: int
    description: Optional[str] = None
    max_users: int = 10
    is_active: bool = True


@router.get("/organizations", response_model=list[OrganizationResponse])
async def list_organizations(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all organizations."""
    result = await db.execute(select(Organization))
    orgs = result.scalars().all()
    
    org_list = []
    for org in orgs:
        members_result = await db.execute(
            select(func.count(User.id)).where(User.organization_id == org.id)
        )
        member_count = members_result.scalar() or 0
        
        org_list.append(
            OrganizationResponse(
                id=org.id,
                name=org.name,
                slug=org.slug,
                member_count=member_count,
                description=org.description,
                max_users=org.max_users,
                is_active=org.is_active,
            )
        )
    
    return org_list


class CreateOrganizationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    max_users: int = Field(10, gt=0)
    is_active: bool = True


class UpdateOrganizationRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    max_users: Optional[int] = Field(None, gt=0)
    is_active: Optional[bool] = None


@router.post("/organizations", response_model=OrganizationResponse)
async def create_organization(
    request: CreateOrganizationRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create new organization."""
    # Check if slug already exists
    existing = await db.execute(select(Organization).where(Organization.slug == request.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Organization with this slug already exists")
    
    org = Organization(
        name=request.name,
        slug=request.slug,
        description=request.description,
        max_users=request.max_users,
        is_active=request.is_active,
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)
    
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        member_count=0,
        description=org.description,
        max_users=org.max_users,
        is_active=org.is_active,
    )


@router.get("/organizations/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get organization details."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    members_result = await db.execute(
        select(func.count(User.id)).where(User.organization_id == org.id)
    )
    member_count = members_result.scalar() or 0
    
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        member_count=member_count,
        description=org.description,
        max_users=org.max_users,
        is_active=org.is_active,
    )


@router.put("/organizations/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: int,
    request: UpdateOrganizationRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update organization."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    if request.name is not None:
        org.name = request.name
    if request.description is not None:
        org.description = request.description
    if request.max_users is not None:
        org.max_users = request.max_users
    if request.is_active is not None:
        org.is_active = request.is_active
    
    await db.commit()
    await db.refresh(org)
    
    members_result = await db.execute(
        select(func.count(User.id)).where(User.organization_id == org.id)
    )
    member_count = members_result.scalar() or 0
    
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        member_count=member_count,
        description=org.description,
        max_users=org.max_users,
        is_active=org.is_active,
    )


@router.delete("/organizations/{org_id}")
async def delete_organization(
    org_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete organization (only if no users)."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check if any users belong to this organization
    users_count = await db.execute(
        select(func.count(User.id)).where(User.organization_id == org_id)
    )
    count = users_count.scalar()
    
    if count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete organization: {count} user(s) belong to it"
        )
    
    await db.delete(org)
    await db.commit()
    
    return {"detail": "Organization deleted"}


# ============================================================================
# User Details & Modifications
# ============================================================================

class UpdateUserRequest(BaseModel):
    is_active: bool
    is_superuser: bool


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get user details."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: UpdateUserRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update user status and role."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = request.is_active
    user.is_superuser = request.is_superuser
    
    await db.commit()
    await db.refresh(user)
    
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete user (soft delete by marking as inactive)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Soft delete - just mark as inactive
    user.is_active = False
    await db.commit()
    
    return {"detail": "User deleted (marked as inactive)"}


# ============================================================================
# Subscription Details & Modifications
# ============================================================================

class UpdateSubscriptionRequest(BaseModel):
    subscription_status: Optional[str] = None
    subscription_plan_id: Optional[int] = None


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get subscription details."""
    result = await db.execute(
        select(BillingAccount, Organization, SubscriptionPlan)
        .join(Organization, BillingAccount.organization_id == Organization.id)
        .outerjoin(SubscriptionPlan, BillingAccount.subscription_plan_id == SubscriptionPlan.id)
        .where(BillingAccount.id == subscription_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    billing, org, plan = row
    
    user_count_result = await db.execute(
        select(func.count(User.id)).where(User.organization_id == org.id)
    )
    user_count = user_count_result.scalar() or 0
    
    return SubscriptionResponse(
        id=billing.id,
        organization_id=billing.organization_id,
        organization_name=org.name,
        user_count=user_count,
        plan_name=plan.name if plan else None,
        plan_id=plan.id if plan else None,
        status=billing.subscription_status.value,
        paddle_subscription_id=billing.paddle_subscription_id,
        total_spent=billing.total_spent,
        created_at=billing.created_at,
        updated_at=billing.updated_at,
    )


@router.put("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: int,
    request: UpdateSubscriptionRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update subscription status."""
    from app.models.billing import SubscriptionStatus
    
    result = await db.execute(select(BillingAccount).where(BillingAccount.id == subscription_id))
    billing = result.scalar_one_or_none()
    if not billing:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    # Update status if provided
    if request.subscription_status:
        billing.subscription_status = SubscriptionStatus(request.subscription_status)
    
    # Update plan if provided
    if request.subscription_plan_id:
        # Verify plan exists
        plan_check = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == request.subscription_plan_id)
        )
        if not plan_check.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Plan not found")
        
        billing.subscription_plan_id = request.subscription_plan_id
        # Reset period counters when changing plan
        billing.requests_used_current_period = 0
        billing.period_started_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(billing)
    
    # Get full response
    result = await db.execute(
        select(BillingAccount, Organization, SubscriptionPlan)
        .join(Organization, BillingAccount.organization_id == Organization.id)
        .outerjoin(SubscriptionPlan, BillingAccount.subscription_plan_id == SubscriptionPlan.id)
        .where(BillingAccount.id == subscription_id)
    )
    row = result.one()
    billing, org, plan = row
    
    user_count_result = await db.execute(
        select(func.count(User.id)).where(User.organization_id == org.id)
    )
    user_count = user_count_result.scalar() or 0
    
    return SubscriptionResponse(
        id=billing.id,
        organization_id=billing.organization_id,
        organization_name=org.name,
        user_count=user_count,
        plan_name=plan.name if plan else None,
        plan_id=plan.id if plan else None,
        status=billing.subscription_status.value,
        paddle_subscription_id=billing.paddle_subscription_id,
        total_spent=billing.total_spent,
        created_at=billing.created_at,
        updated_at=billing.updated_at,
    )


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete subscription (cancel it)."""
    from app.models.billing import SubscriptionStatus
    
    result = await db.execute(select(BillingAccount).where(BillingAccount.id == subscription_id))
    billing = result.scalar_one_or_none()
    if not billing:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    billing.subscription_status = SubscriptionStatus.CANCELED
    await db.commit()
    
    return {"detail": "Subscription canceled"}


# ============================================================================
# LLM Models Management
# ============================================================================

class LLMModelResponse(BaseModel):
    id: int
    name: str
    display_name: str
    provider: str
    api_key: str  # Will be masked in response
    api_base_url: Optional[str]
    max_tokens_limit: int
    context_window: int
    cost_per_1k_input_tokens: Optional[float]
    cost_per_1k_output_tokens: Optional[float]
    is_active: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime


class CreateLLMModelRequest(BaseModel):
    name: str = Field(..., description="Model identifier (e.g., 'gpt-4')")
    display_name: str = Field(..., description="Human-readable name")
    provider: str = Field(..., description="Provider: openai, anthropic, google")
    api_key: str = Field(..., description="API key for this model")
    api_base_url: Optional[str] = Field(None, description="Custom API endpoint")
    max_tokens_limit: int = Field(4096, description="Maximum tokens per request")
    context_window: int = Field(8192, description="Model context window size")
    cost_per_1k_input_tokens: Optional[float] = None
    cost_per_1k_output_tokens: Optional[float] = None
    is_active: bool = True
    is_default: bool = False


class UpdateLLMModelRequest(BaseModel):
    display_name: Optional[str] = None
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    max_tokens_limit: Optional[int] = None
    context_window: Optional[int] = None
    cost_per_1k_input_tokens: Optional[float] = None
    cost_per_1k_output_tokens: Optional[float] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


@router.get("/llm-models", response_model=list[LLMModelResponse])
async def list_llm_models(
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all LLM models."""
    result = await db.execute(select(LLMModel).order_by(LLMModel.name))
    models = result.scalars().all()
    
    # Mask API keys (show only first 8 and last 4 characters)
    response = []
    for model in models:
        model_dict = {
            "id": model.id,
            "name": model.name,
            "display_name": model.display_name,
            "provider": model.provider,
            "api_key": f"{model.api_key[:8]}...{model.api_key[-4:]}" if len(model.api_key) > 12 else "***",
            "api_base_url": model.api_base_url,
            "max_tokens_limit": model.max_tokens_limit,
            "context_window": model.context_window,
            "cost_per_1k_input_tokens": float(model.cost_per_1k_input_tokens) if model.cost_per_1k_input_tokens else None,
            "cost_per_1k_output_tokens": float(model.cost_per_1k_output_tokens) if model.cost_per_1k_output_tokens else None,
            "is_active": model.is_active,
            "is_default": model.is_default,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
        response.append(LLMModelResponse(**model_dict))
    
    return response


@router.get("/llm-models/{model_id}", response_model=LLMModelResponse)
async def get_llm_model(
    model_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get LLM model by ID."""
    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="LLM model not found")
    
    # Mask API key
    model_dict = {
        "id": model.id,
        "name": model.name,
        "display_name": model.display_name,
        "provider": model.provider,
        "api_key": f"{model.api_key[:8]}...{model.api_key[-4:]}" if len(model.api_key) > 12 else "***",
        "api_base_url": model.api_base_url,
        "max_tokens_limit": model.max_tokens_limit,
        "context_window": model.context_window,
        "cost_per_1k_input_tokens": float(model.cost_per_1k_input_tokens) if model.cost_per_1k_input_tokens else None,
        "cost_per_1k_output_tokens": float(model.cost_per_1k_output_tokens) if model.cost_per_1k_output_tokens else None,
        "is_active": model.is_active,
        "is_default": model.is_default,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }
    return LLMModelResponse(**model_dict)


@router.post("/llm-models", response_model=LLMModelResponse)
async def create_llm_model(
    request: CreateLLMModelRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create new LLM model."""
    # Check if name already exists
    existing = await db.execute(select(LLMModel).where(LLMModel.name == request.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="LLM model with this name already exists")
    
    # If setting as default, unset other defaults
    if request.is_default:
        await db.execute(
            update(LLMModel)
            .where(LLMModel.is_default == True)
            .values(is_default=False)
        )
    
    model = LLMModel(
        name=request.name,
        display_name=request.display_name,
        provider=request.provider,
        api_key=request.api_key,
        api_base_url=request.api_base_url,
        max_tokens_limit=request.max_tokens_limit,
        context_window=request.context_window,
        cost_per_1k_input_tokens=request.cost_per_1k_input_tokens,
        cost_per_1k_output_tokens=request.cost_per_1k_output_tokens,
        is_active=request.is_active,
        is_default=request.is_default,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    
    # Mask API key in response
    model_dict = {
        "id": model.id,
        "name": model.name,
        "display_name": model.display_name,
        "provider": model.provider,
        "api_key": f"{model.api_key[:8]}...{model.api_key[-4:]}",
        "api_base_url": model.api_base_url,
        "max_tokens_limit": model.max_tokens_limit,
        "context_window": model.context_window,
        "cost_per_1k_input_tokens": float(model.cost_per_1k_input_tokens) if model.cost_per_1k_input_tokens else None,
        "cost_per_1k_output_tokens": float(model.cost_per_1k_output_tokens) if model.cost_per_1k_output_tokens else None,
        "is_active": model.is_active,
        "is_default": model.is_default,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }
    return LLMModelResponse(**model_dict)


@router.put("/llm-models/{model_id}", response_model=LLMModelResponse)
async def update_llm_model(
    model_id: int,
    request: UpdateLLMModelRequest,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update LLM model."""
    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="LLM model not found")
    
    # If setting as default, unset other defaults
    if request.is_default and not model.is_default:
        await db.execute(
            update(LLMModel)
            .where(LLMModel.is_default == True)
            .values(is_default=False)
        )
    
    # Update fields
    if request.display_name is not None:
        model.display_name = request.display_name
    if request.api_key is not None:
        model.api_key = request.api_key
    if request.api_base_url is not None:
        model.api_base_url = request.api_base_url
    if request.max_tokens_limit is not None:
        model.max_tokens_limit = request.max_tokens_limit
    if request.context_window is not None:
        model.context_window = request.context_window
    if request.cost_per_1k_input_tokens is not None:
        model.cost_per_1k_input_tokens = request.cost_per_1k_input_tokens
    if request.cost_per_1k_output_tokens is not None:
        model.cost_per_1k_output_tokens = request.cost_per_1k_output_tokens
    if request.is_active is not None:
        model.is_active = request.is_active
    if request.is_default is not None:
        model.is_default = request.is_default
    
    await db.commit()
    await db.refresh(model)
    
    # Mask API key in response
    model_dict = {
        "id": model.id,
        "name": model.name,
        "display_name": model.display_name,
        "provider": model.provider,
        "api_key": f"{model.api_key[:8]}...{model.api_key[-4:]}" if len(model.api_key) > 12 else "***",
        "api_base_url": model.api_base_url,
        "max_tokens_limit": model.max_tokens_limit,
        "context_window": model.context_window,
        "cost_per_1k_input_tokens": float(model.cost_per_1k_input_tokens) if model.cost_per_1k_input_tokens else None,
        "cost_per_1k_output_tokens": float(model.cost_per_1k_output_tokens) if model.cost_per_1k_output_tokens else None,
        "is_active": model.is_active,
        "is_default": model.is_default,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }
    return LLMModelResponse(**model_dict)


@router.delete("/llm-models/{model_id}")
async def delete_llm_model(
    model_id: int,
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete LLM model (only if not used by any agents)."""
    # Check if any agents use this model
    agents_count = await db.execute(
        select(func.count(Agent.id)).where(Agent.llm_model_id == model_id)
    )
    count = agents_count.scalar()
    
    if count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete LLM model: {count} agent(s) are using it"
        )
    
    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="LLM model not found")
    
    await db.delete(model)
    await db.commit()
    
    return {"detail": "LLM model deleted"}

