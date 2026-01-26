"""Simple test to verify SubscriptionPlan model fields."""
import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.billing import SubscriptionPlan, PlanType, SubscriptionInterval
from app.models.user import User
from app.models.organization import Organization
from app.models.billing import BillingAccount


async def test_subscription_plan_fields():
    """Test all SubscriptionPlan fields exist."""
    print("Testing SubscriptionPlan model fields...")
    
    async with AsyncSessionLocal() as db:
        # Get first plan
        result = await db.execute(select(SubscriptionPlan).limit(1))
        plan = result.scalar_one_or_none()
        
        if not plan:
            print("❌ No plans found in database")
            return False
        
        print(f"✓ Found plan: {plan.name}")
        
        # Test all fields
        fields = [
            'id', 'name', 'interval', 'plan_type', 'price', 'currency',
            'one_time_limit', 'max_requests_per_interval', 'max_tokens_per_request',
            'free_requests_limit', 'free_trial_days',
            'has_api_access', 'has_priority_support', 'has_advanced_analytics',
            'is_default', 'paddle_price_id', 'paddle_product_id',
            'created_at', 'updated_at', 'agents'
        ]
        
        missing_fields = []
        for field in fields:
            if not hasattr(plan, field):
                missing_fields.append(field)
                print(f"❌ Missing field: {field}")
            else:
                value = getattr(plan, field)
                print(f"✓ {field}: {value}")
        
        # Test properties
        print(f"✓ is_valid property: {plan.is_valid}")
        print(f"✓ validation_errors property: {plan.validation_errors}")
        
        if missing_fields:
            print(f"\n❌ Missing fields: {missing_fields}")
            return False
        
        print("\n✅ All fields exist!")
        return True


async def test_billing_account_fields():
    """Test BillingAccount fields."""
    print("\nTesting BillingAccount model fields...")
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BillingAccount).limit(1))
        billing = result.scalar_one_or_none()
        
        if not billing:
            print("❌ No billing accounts found")
            return False
        
        print(f"✓ Found billing account: {billing.id}")
        
        # Test fields used in telegram.py
        fields = [
            'subscription_status', 'subscription_plan_id', 'free_requests_used',
            'requests_used_current_period', 'one_time_purchases_count',
            'one_time_requests_used', 'next_billing_date'
        ]
        
        for field in fields:
            if not hasattr(billing, field):
                print(f"❌ Missing field: {field}")
                return False
            value = getattr(billing, field)
            print(f"✓ {field}: {value}")
        
        print("\n✅ All BillingAccount fields exist!")
        return True


async def test_profile_data_flow():
    """Test the full data flow for profile command."""
    print("\nTesting profile data flow...")
    
    async with AsyncSessionLocal() as db:
        # Get a user with telegram_id
        result = await db.execute(
            select(User).where(User.telegram_id.isnot(None)).limit(1)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print("⚠️  No users with telegram_id found")
            return True  # Not a failure, just no data
        
        print(f"✓ Found user: {user.full_name} (telegram_id: {user.telegram_id})")
        
        # Get organization
        org_result = await db.execute(
            select(Organization).where(Organization.id == user.organization_id)
        )
        organization = org_result.scalar_one_or_none()
        
        if not organization:
            print(f"⚠️  User has no organization")
            return True
        
        print(f"✓ Found organization: {organization.name}")
        
        # Get billing account
        billing_result = await db.execute(
            select(BillingAccount).where(BillingAccount.organization_id == organization.id)
        )
        billing = billing_result.scalar_one_or_none()
        
        if billing:
            print(f"✓ Found billing account")
            print(f"  - Status: {billing.subscription_status.value}")
            print(f"  - Free requests used: {billing.free_requests_used}")
            
            if billing.subscription_plan_id:
                plan_result = await db.execute(
                    select(SubscriptionPlan).where(SubscriptionPlan.id == billing.subscription_plan_id)
                )
                plan = plan_result.scalar_one_or_none()
                if plan:
                    print(f"✓ Found plan: {plan.name}")
                    print(f"  - Type: {plan.plan_type.value}")
                    print(f"  - Max requests: {plan.max_requests_per_interval}")
                    print(f"  - Free requests limit: {plan.free_requests_limit}")
                    print(f"  - One-time limit: {plan.one_time_limit}")
        else:
            print("⚠️  No billing account")
        
        # Get available plans
        plans_result = await db.execute(select(SubscriptionPlan))
        all_plans = plans_result.scalars().all()
        valid_plans = [p for p in all_plans if p.is_valid]
        
        print(f"\n✓ Total plans: {len(all_plans)}")
        print(f"✓ Valid plans (with agents): {len(valid_plans)}")
        
        for plan in valid_plans[:3]:
            print(f"  - {plan.name}: ${plan.price} ({plan.plan_type.value})")
        
        print("\n✅ Profile data flow test complete!")
        return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("TELEGRAM PROFILE MODEL FIELD TEST")
    print("=" * 60)
    
    try:
        result1 = await test_subscription_plan_fields()
        result2 = await test_billing_account_fields()
        result3 = await test_profile_data_flow()
        
        print("\n" + "=" * 60)
        if result1 and result2 and result3:
            print("✅ ALL TESTS PASSED!")
        else:
            print("❌ SOME TESTS FAILED")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
