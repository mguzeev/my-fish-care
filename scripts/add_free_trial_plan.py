"""Add Free Trial plan to existing database."""
import asyncio
from decimal import Decimal

from app.core.database import AsyncSessionLocal
from app.models.billing import SubscriptionPlan, SubscriptionInterval
from sqlalchemy import select


async def add_free_trial_plan():
    """Add Free Trial plan if it doesn't exist."""
    async with AsyncSessionLocal() as db:
        # Check if Free Trial plan already exists
        result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.name == "Free Trial")
        )
        existing_plan = result.scalar_one_or_none()
        
        if existing_plan:
            print("✅ Free Trial plan already exists")
            print(f"   ID: {existing_plan.id}, Free requests: {existing_plan.free_requests_limit}")
            return
        
        # Create Free Trial plan
        free_trial_plan = SubscriptionPlan(
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
        )
        
        db.add(free_trial_plan)
        await db.commit()
        await db.refresh(free_trial_plan)
        
        print("✅ Created Free Trial plan")
        print(f"   ID: {free_trial_plan.id}")
        print(f"   Free requests limit: {free_trial_plan.free_requests_limit}")
        print(f"   Price: ${free_trial_plan.price}")


if __name__ == "__main__":
    asyncio.run(add_free_trial_plan())
