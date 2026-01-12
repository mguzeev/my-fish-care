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
from app.models.billing import BillingAccount, SubscriptionPlan, SubscriptionStatus
from app.models.usage import UsageRecord
from app.models.policy import PolicyRule
from app.models.prompt import PromptVersion
from app.models.agent import Agent


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
    status: str
    paddle_subscription_id: Optional[str]
    total_spent: Decimal
    created_at: datetime
    updated_at: datetime


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
    subscription_status: str


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
    
    billing.subscription_status = SubscriptionStatus(request.subscription_status)
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
