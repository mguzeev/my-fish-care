"""Seed initial subscription plans and policy rules for local development."""
import asyncio
import json
from decimal import Decimal

from app.core.database import AsyncSessionLocal, init_db
from app.models.billing import SubscriptionPlan, SubscriptionInterval
from app.models.policy import PolicyRule


async def seed_data():
    """Seed database with initial data."""
    await init_db()
    
    async with AsyncSessionLocal() as db:
        # Seed subscription plans
        plans = [
            SubscriptionPlan(
                name="Free Trial",
                interval=SubscriptionInterval.MONTHLY,
                price=Decimal("0.00"),
                currency="USD",
                max_requests_per_interval=0,  # После бесплатных - блокировка
                max_tokens_per_request=2000,
                free_requests_limit=10,  # 10 бесплатных обращений
                free_trial_days=0,  # Без временного лимита
                has_api_access=False,
                has_priority_support=False,
                has_advanced_analytics=False,
            ),
            SubscriptionPlan(
                name="Daily",
                interval=SubscriptionInterval.DAILY,
                price=Decimal("0.99"),
                currency="USD",
                max_requests_per_interval=100,
                max_tokens_per_request=1000,
                has_api_access=False,
                has_priority_support=False,
                has_advanced_analytics=False,
            ),
            SubscriptionPlan(
                name="Weekly",
                interval=SubscriptionInterval.WEEKLY,
                price=Decimal("4.99"),
                currency="USD",
                max_requests_per_interval=1000,
                max_tokens_per_request=1500,
                has_api_access=False,
                has_priority_support=True,
                has_advanced_analytics=False,
            ),
            SubscriptionPlan(
                name="Monthly",
                interval=SubscriptionInterval.MONTHLY,
                price=Decimal("19.99"),
                currency="USD",
                max_requests_per_interval=10000,
                max_tokens_per_request=2000,
                has_api_access=True,
                has_priority_support=True,
                has_advanced_analytics=False,
            ),
            SubscriptionPlan(
                name="Yearly",
                interval=SubscriptionInterval.YEARLY,
                price=Decimal("199.99"),
                currency="USD",
                max_requests_per_interval=150000,
                max_tokens_per_request=3000,
                has_api_access=True,
                has_priority_support=True,
                has_advanced_analytics=True,
            ),
        ]
        
        for plan in plans:
            db.add(plan)
        
        # Seed policy rules
        rules = [
            PolicyRule(
                name="User rate limit 100/min",
                rule_type="rate_limit",
                target_resource="/agents",
                target_role="user",
                config=json.dumps({"limit": 100, "window_sec": 60, "key": "user_agents"}),
                is_active=True,
                priority=10,
            ),
            PolicyRule(
                name="Admin rate limit 1000/min",
                rule_type="rate_limit",
                target_resource="/admin",
                target_role="admin",
                config=json.dumps({"limit": 1000, "window_sec": 60, "key": "admin_ops"}),
                is_active=True,
                priority=10,
            ),
        ]
        
        for rule in rules:
            db.add(rule)
        
        await db.commit()
        print("✅ Seeded subscription plans and policy rules")


if __name__ == "__main__":
    asyncio.run(seed_data())
