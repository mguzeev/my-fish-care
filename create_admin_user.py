#!/usr/bin/env python3
"""Create admin user for testing."""

import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from app.core.config import settings
from app.models.user import User
from app.models.organization import Organization 
from app.models.billing import BillingAccount, SubscriptionPlan, SubscriptionStatus
from app.core.security import get_password_hash


async def create_admin_user():
    """Create admin user for testing."""
    
    # Create database engine and session
    engine = create_async_engine(settings.database_url)
    async_session = async_sessionmaker(engine)
    
    async with async_session() as db:
        # Check if admin already exists
        result = await db.execute(select(User).where(User.email == "admin@test.com"))
        if result.scalar_one_or_none():
            print("Admin user already exists!")
            return
        
        # Create admin user
        user = User(
            email="admin@test.com",
            username="admin",
            hashed_password=get_password_hash("password123"),
            full_name="Admin User",
            is_superuser=True,  # Make superuser
            is_active=True,
            email_verified_at=datetime.utcnow()
        )
        
        db.add(user)
        await db.flush()  # Flush to get user.id
        
        # Create organization for the user
        org = Organization(
            name="Admin Organization",
            slug="admin-org",
            description="Admin organization"
        )
        db.add(org)
        await db.flush()
        
        # Assign user to organization
        user.organization_id = org.id
        
        # Find or create default plan
        default_plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.is_default == True)
        )
        default_plan = default_plan_result.scalar_one_or_none()
        
        if not default_plan:
            # Create a default Free Trial plan
            from app.models.billing import SubscriptionInterval
            default_plan = SubscriptionPlan(
                name="Free Trial",
                interval=SubscriptionInterval.MONTHLY,
                price=0.00,
                currency="USD",
                max_requests_per_interval=0,
                max_tokens_per_request=2000,
                free_requests_limit=10,
                free_trial_days=0,
                has_api_access=False,
                has_priority_support=False,
                has_advanced_analytics=False,
                is_default=True
            )
            db.add(default_plan)
            await db.flush()
        
        # Create billing account
        billing_account = BillingAccount(
            organization_id=org.id,
            subscription_plan_id=default_plan.id,
            subscription_status=SubscriptionStatus.TRIALING,
            free_requests_used=0,
            requests_used_current_period=0,
            one_time_requests_used=0,
            trial_started_at=datetime.utcnow(),
            period_started_at=datetime.utcnow()
        )
        db.add(billing_account)
        
        await db.commit()
        await db.refresh(user)
        
        print(f"Admin user created successfully!")
        print(f"Email: admin@test.com")
        print(f"Password: password123")
        print(f"User ID: {user.id}")
        print(f"Organization ID: {org.id}")
        print(f"Superuser: {user.is_superuser}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_admin_user())