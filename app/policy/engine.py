"""Simple Policy Engine for access control and rate limiting."""
import json
import time
from typing import Optional, Tuple

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.policy import PolicyRule
from app.models.user import User
from app.models.agent import Agent
from app.models.billing import BillingAccount, SubscriptionPlan, SubscriptionStatus
from app.auth.dependencies import get_current_user


class PolicyEngine:
    def __init__(self):
        # in-memory rate limit counters: {(user_id, key): (reset_ts, count)}
        self._rate: dict[Tuple[int, str], Tuple[float, int]] = {}

    async def check_access(self, db: AsyncSession, user: User, resource: str, action: str) -> None:
        # Feature flag/resource access rules
        rules = (
            await db.execute(
                select(PolicyRule)
                .where(PolicyRule.is_active == True)
                .order_by(PolicyRule.priority.desc())
            )
        ).scalars().all()

        # Deny rules (explicit)
        for r in rules:
            if r.rule_type == "resource_access" and self._match(r, user, resource):
                conf = self._cfg(r)
                if conf.get("deny", False):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Rate limiting
        for r in rules:
            if r.rule_type == "rate_limit" and self._match(r, user, resource):
                conf = self._cfg(r)
                limit = int(conf.get("limit", 0))
                window = int(conf.get("window_sec", 60))
                if limit > 0:
                    now = time.time()
                    key = (user.id, conf.get("key") or resource)
                    reset_ts, count = self._rate.get(key, (now + window, 0))
                    if now > reset_ts:
                        reset_ts, count = now + window, 0
                    count += 1
                    self._rate[key] = (reset_ts, count)
                    if count > limit:
                        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    async def check_agent_access(self, db: AsyncSession, user: User, agent_id: int) -> None:
        """Check if user has access to specific agent based on subscription plan."""
        # Superusers have access to all agents
        if user.is_superuser:
            return
        
        # Check if agent exists and is active
        agent_result = await db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.is_active == True)
        )
        agent = agent_result.scalar_one_or_none()
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found or inactive"
            )
        
        # Public agents are accessible to everyone
        if agent.is_public:
            return
        
        # Check user's subscription and plan
        if not user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No organization. Subscribe to a plan to access agents."
            )
        
        billing_result = await db.execute(
            select(BillingAccount, SubscriptionPlan)
            .join(SubscriptionPlan, BillingAccount.subscription_plan_id == SubscriptionPlan.id)
            .where(BillingAccount.organization_id == user.organization_id)
        )
        row = billing_result.one_or_none()
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active subscription. Subscribe to a plan to access agents."
            )
        
        billing_account, plan = row
        
        # Check subscription status
        if billing_account.subscription_status not in [
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING
        ]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Subscription is {billing_account.subscription_status.value}. Please renew."
            )
        
        # Check if agent is included in the plan
        plan_with_agents = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == plan.id)
        )
        plan_obj = plan_with_agents.scalar_one()
        
        agent_ids_in_plan = [a.id for a in plan_obj.agents]
        if agent_id not in agent_ids_in_plan:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Agent not included in your '{plan.name}' plan. Please upgrade your subscription."
            )

    @staticmethod
    def _cfg(rule: PolicyRule) -> dict:
        try:
            return json.loads(rule.config or "{}")
        except Exception:
            return {}

    @staticmethod
    def _match(rule: PolicyRule, user: User, resource: str) -> bool:
        role_ok = (rule.target_role is None) or (rule.target_role == user.role) or user.is_superuser
        res_ok = (rule.target_resource is None) or (rule.target_resource == resource)
        return role_ok and res_ok


engine = PolicyEngine()


def enforce_policy(resource: str, action: str = "access"):
    async def _dep(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        await engine.check_access(db, current_user, resource, action)
        return current_user

    return _dep
