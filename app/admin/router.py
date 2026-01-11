"""Admin API routes for SaaS management."""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.models.billing import BillingAccount, SubscriptionPlan, SubscriptionStatus
from app.models.usage import UsageRecord
from app.models.policy import PolicyRule


router = APIRouter(prefix="/admin", tags=["Admin"])


async def require_admin(user: User = Depends(get_current_active_user)) -> None:
    """Dependency to require admin role."""
    if user.role != "admin":
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


@router.get("/dashboard", response_model=DashboardStats)
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
    has_api_access: bool
    has_priority_support: bool
    has_advanced_analytics: bool


class CreateSubscriptionPlanRequest(BaseModel):
    name: str
    interval: str  # DAILY, WEEKLY, MONTHLY, YEARLY
    price: Decimal
    currency: str = "USD"
    max_requests_per_interval: int
    max_tokens_per_request: int
    has_api_access: bool = False
    has_priority_support: bool = False
    has_advanced_analytics: bool = False


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
            has_api_access=p.has_api_access,
            has_priority_support=p.has_priority_support,
            has_advanced_analytics=p.has_advanced_analytics,
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
        has_api_access=request.has_api_access,
        has_priority_support=request.has_priority_support,
        has_advanced_analytics=request.has_advanced_analytics,
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
        has_api_access=plan.has_api_access,
        has_priority_support=plan.has_priority_support,
        has_advanced_analytics=plan.has_advanced_analytics,
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
    plan.has_api_access = request.has_api_access
    plan.has_priority_support = request.has_priority_support
    plan.has_advanced_analytics = request.has_advanced_analytics
    
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
        has_api_access=plan.has_api_access,
        has_priority_support=plan.has_priority_support,
        has_advanced_analytics=plan.has_advanced_analytics,
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
            )
        )
    
    return org_list
