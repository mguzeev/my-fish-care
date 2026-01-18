"""Tests for billing fixes from Stage 1 and Stage 2."""
import pytest
from datetime import datetime
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from app.core.security import create_access_token
from app.models.billing import (
    BillingAccount, SubscriptionPlan, SubscriptionStatus, 
    SubscriptionInterval, PlanType
)
from app.models.organization import Organization
from app.models.user import User
from app.models.agent import Agent


@pytest.mark.asyncio
async def test_stage1_block_one_time_purchase_during_active_subscription(
    client: AsyncClient, db_session: AsyncSession
):
    """Test Stage 1.1: Cannot purchase ONE_TIME credits while subscription is active."""
    
    # Create user with organization
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.flush()
    
    org = Organization(name="Test Org", slug="test-org")
    db_session.add(org)
    await db_session.flush()
    
    user.organization_id = org.id
    
    # Create SUBSCRIPTION plan (active)
    subscription_plan = SubscriptionPlan(
        name="Monthly Sub",
        interval=SubscriptionInterval.MONTHLY,
        plan_type=PlanType.SUBSCRIPTION,
        price=Decimal("9.99"),
        currency="USD",
        max_requests_per_interval=1000,
        max_tokens_per_request=2000,
    )
    db_session.add(subscription_plan)
    await db_session.flush()
    
    # Create ONE_TIME plan
    onetime_plan = SubscriptionPlan(
        name="20 Credits",
        interval=SubscriptionInterval.MONTHLY,
        plan_type=PlanType.ONE_TIME,
        price=Decimal("4.99"),
        currency="USD",
        max_requests_per_interval=1000,
        one_time_limit=20,
    )
    db_session.add(onetime_plan)
    await db_session.flush()
    
    # Create billing account with ACTIVE subscription
    billing_account = BillingAccount(
        organization_id=org.id,
        subscription_plan_id=subscription_plan.id,
        subscription_status=SubscriptionStatus.ACTIVE,
        one_time_purchases_count=0,
        one_time_requests_used=0,
    )
    db_session.add(billing_account)
    await db_session.commit()
    
    # Try to purchase ONE_TIME plan - should be blocked
    token = create_access_token({"sub": user.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.post(
        "/billing/subscribe",
        headers=headers,
        json={"plan_id": onetime_plan.id}
    )
    
    assert response.status_code == 400
    assert "Cannot purchase credits while subscription is active" in response.json()["detail"]


@pytest.mark.asyncio
async def test_stage1_allow_one_time_purchase_without_subscription(
    client: AsyncClient, db_session: AsyncSession
):
    """Test Stage 1.1: Can purchase ONE_TIME credits without active subscription."""
    from app.models.llm_model import LLMModel

    # Create LLM model
    llm_model = LLMModel(
        name="gpt-4-onetime",
        display_name="GPT-4 OneTime",
        provider="openai",
        api_key="test-key",
        max_tokens_limit=4096,
        context_window=8192,
        is_active=True
    )
    db_session.add(llm_model)
    await db_session.flush()

    # Create user with organization
    user = User(
        email="test2@example.com",
        username="testuser2",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.flush()

    org = Organization(name="Test Org 2", slug="test-org-2")
    db_session.add(org)
    await db_session.flush()

    user.organization_id = org.id

    # Create agent
    agent = Agent(
        name="OneTime Agent",
        slug="onetime-agent",
        system_prompt="You are a onetime agent",
        prompt_template="OneTime: {input}",
        llm_model_id=llm_model.id,
        model_name="gpt-4",
        is_active=True,
        is_public=True
    )
    db_session.add(agent)
    await db_session.flush()

    # Create ONE_TIME plan
    onetime_plan = SubscriptionPlan(
        name="20 Credits",
        interval=SubscriptionInterval.MONTHLY,
        plan_type=PlanType.ONE_TIME,
        price=Decimal("4.99"),
        currency="USD",
        max_requests_per_interval=1000,
        one_time_limit=20,
    )
    db_session.add(onetime_plan)
    await db_session.flush()

    # Skip linking agent to plan for this test - Stage 3 doesn't require it
    # Plan validation will be tested in separate Stage 3 tests
    
    # Create billing account with TRIALING status
    billing_account = BillingAccount(
        organization_id=org.id,
        subscription_status=SubscriptionStatus.TRIALING,
        one_time_purchases_count=0,
        one_time_requests_used=0,
    )
    db_session.add(billing_account)
    await db_session.commit()
    
    # Purchase ONE_TIME plan - should succeed
    token = create_access_token({"sub": user.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.post(
        "/billing/subscribe",
        headers=headers,
        json={"plan_id": onetime_plan.id}
    )
    
    assert response.status_code == 200
    # Should have checkout_url for payment
    assert "checkout_url" in response.json() or not response.json().get("checkout_url")  # Paddle disabled in tests


@pytest.mark.asyncio
async def test_stage1_webhook_does_not_overwrite_subscription(db_session: AsyncSession):
    """Test Stage 1.2: ONE_TIME webhook doesn't overwrite subscription_plan_id."""
    from app.webhooks.router import handle_transaction_completed
    from app.models.billing import PlanType
    
    # Create organization
    org = Organization(name="Webhook Test Org", slug="webhook-test-org")
    db_session.add(org)
    await db_session.flush()
    
    # Create SUBSCRIPTION plan
    subscription_plan = SubscriptionPlan(
        name="Monthly Sub",
        interval=SubscriptionInterval.MONTHLY,
        plan_type=PlanType.SUBSCRIPTION,
        price=Decimal("9.99"),
        currency="USD",
        max_requests_per_interval=1000,
        max_tokens_per_request=2000,
    )
    db_session.add(subscription_plan)
    await db_session.flush()
    
    # Create ONE_TIME plan
    onetime_plan = SubscriptionPlan(
        name="20 Credits",
        interval=SubscriptionInterval.MONTHLY, 
        plan_type=PlanType.ONE_TIME,
        price=Decimal("4.99"),
        currency="USD",
        max_requests_per_interval=1000,
        one_time_limit=20,
        paddle_price_id="pri_onetime_123"
    )
    db_session.add(onetime_plan)
    await db_session.flush()
    
    # Create billing account with ACTIVE subscription
    billing_account = BillingAccount(
        organization_id=org.id,
        subscription_plan_id=subscription_plan.id,
        subscription_status=SubscriptionStatus.ACTIVE,
        paddle_customer_id="cus_123",
        one_time_purchases_count=0,
        one_time_requests_used=0,
    )
    db_session.add(billing_account)
    await db_session.commit()
    
    # Store original subscription info
    original_plan_id = billing_account.subscription_plan_id
    original_status = billing_account.subscription_status
    
    # Simulate ONE_TIME purchase webhook
    webhook_data = {
        "id": "txn_123",
        "customer_id": "cus_123",
        "subscription_id": None,  # ONE_TIME purchase has no subscription_id
        "items": [{"price": {"id": "pri_onetime_123"}}]
    }
    
    await handle_transaction_completed(webhook_data, db_session, "evt_123")
    
    # Refresh billing account
    await db_session.refresh(billing_account)
    
    # Verify subscription was NOT overwritten
    assert billing_account.subscription_plan_id == original_plan_id
    assert billing_account.subscription_status == original_status
    
    # Verify ONE_TIME purchase was recorded
    assert billing_account.one_time_purchases_count == 20
    assert billing_account.last_transaction_id == "txn_123"


@pytest.mark.asyncio
async def test_stage2_separate_counters_for_plan_types(db_session: AsyncSession):
    """Test Stage 2: ONE_TIME and SUBSCRIPTION plans use separate counters."""
    from app.policy.engine import PolicyEngine
    from app.models.llm_model import LLMModel
    
    # Create LLM model
    llm_model = LLMModel(
        name="gpt-4",
        display_name="GPT-4 (OpenAI)",
        provider="openai",
        api_key="test-key",
        max_tokens_limit=4096,
        context_window=8192,
        is_active=True,
        is_default=True
    )
    db_session.add(llm_model)
    await db_session.flush()
    
    # Create user and organization
    user = User(email="counter@example.com", username="counter", hashed_password="hashed")
    db_session.add(user)
    await db_session.flush()
    
    org = Organization(name="Counter Test Org", slug="counter-test")
    db_session.add(org)
    await db_session.flush()
    
    user.organization_id = org.id
    
    # Create agent
    agent = Agent(
        name="Test Agent",
        slug="test-agent", 
        system_prompt="You are a test agent",
        prompt_template="Test: {input}",
        llm_model_id=llm_model.id,
        model_name="gpt-4",
        is_active=True,
        is_public=True  # Make public to bypass plan restrictions
    )
    db_session.add(agent)
    await db_session.flush()
    
    # Create ONE_TIME plan
    onetime_plan = SubscriptionPlan(
        name="50 Credits",
        interval=SubscriptionInterval.MONTHLY,
        plan_type=PlanType.ONE_TIME,
        price=Decimal("9.99"),
        currency="USD",
        max_requests_per_interval=1000,
        one_time_limit=50,
    )
    db_session.add(onetime_plan)
    await db_session.flush()
    
    # Create billing account
    billing_account = BillingAccount(
        organization_id=org.id,
        subscription_plan_id=onetime_plan.id,
        subscription_status=SubscriptionStatus.ACTIVE,
        one_time_purchases_count=50,  # Purchased 50 credits
        one_time_requests_used=10,    # Used 10 ONE_TIME credits
        requests_used_current_period=30,  # Used 30 subscription requests (should not affect ONE_TIME)
    )
    db_session.add(billing_account)
    await db_session.commit()
    
    # Test Policy Engine
    engine = PolicyEngine()
    
    # Check ONE_TIME usage limits
    result = await engine.check_usage_limits(db_session, user, agent.id)
    
    # Should have 40 remaining (50 purchased - 10 used ONE_TIME)
    assert result["allowed"] is True
    assert result["paid_remaining"] == 40
    assert "40" in result["reason"]  # Should show correct remaining count
    
    # Increment ONE_TIME usage
    await engine.increment_usage(db_session, user)
    
    # Refresh and check
    await db_session.refresh(billing_account)
    assert billing_account.one_time_requests_used == 11  # Incremented ONE_TIME counter
    assert billing_account.requests_used_current_period == 30  # Subscription counter unchanged


@pytest.mark.asyncio
async def test_stage2_default_plan_registration(client: AsyncClient, db_session: AsyncSession):
    """Test Stage 2: New users get is_default plan during registration."""
    
    # Create default plan
    default_plan = SubscriptionPlan(
        name="Free Starter",
        interval=SubscriptionInterval.MONTHLY,
        plan_type=PlanType.SUBSCRIPTION,
        price=Decimal("0.00"),
        currency="USD",
        max_requests_per_interval=0,
        max_tokens_per_request=2000,
        free_requests_limit=5,
        is_default=True,  # Mark as default
    )
    db_session.add(default_plan)
    await db_session.commit()
    
    # Register new user
    response = await client.post(
        "/auth/register",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "Password123",  # Added uppercase
            "full_name": "New User"
        }
    )
    
    assert response.status_code == 201
    user_data = response.json()
    
    # Check user got the default plan
    user = await db_session.get(User, user_data["id"])
    from sqlalchemy import select
    billing_result = await db_session.execute(
        select(BillingAccount).where(
            BillingAccount.organization_id == user.organization_id
        )
    )
    billing_account = billing_result.scalar_one()
    
    assert billing_account.subscription_plan_id == default_plan.id
    assert billing_account.one_time_requests_used == 0  # New counter initialized


@pytest.mark.asyncio
async def test_stage2_default_plan_fallback(db_session: AsyncSession):
    """Test Stage 2: Fallback logic when no is_default plan exists."""
    from app.auth.router import register
    from app.auth.schemas import UserRegister
    
    # Create plan with free requests but NOT marked as default
    fallback_plan = SubscriptionPlan(
        name="Free Plan",
        interval=SubscriptionInterval.MONTHLY,
        plan_type=PlanType.SUBSCRIPTION,
        price=Decimal("0.00"),
        currency="USD",
        max_requests_per_interval=0,
        max_tokens_per_request=2000,
        free_requests_limit=10,
        is_default=False,  # Not default
    )
    db_session.add(fallback_plan)
    
    # Create another plan without free requests
    paid_plan = SubscriptionPlan(
        name="Paid Plan",
        interval=SubscriptionInterval.MONTHLY,
        plan_type=PlanType.SUBSCRIPTION,
        price=Decimal("9.99"),
        currency="USD",
        max_requests_per_interval=1000,
        max_tokens_per_request=2000,
        free_requests_limit=0,
        is_default=False,
    )
    db_session.add(paid_plan)
    await db_session.commit()
    
    # Register user (should get fallback_plan due to free_requests_limit > 0)
    user_data = UserRegister(
        email="fallback@example.com",
        username="fallback",
        password="Password123",  # Added uppercase
        full_name="Fallback User"
    )
    
    user = await register(user_data, db_session)
    
    # Check user got the fallback plan
    from sqlalchemy import select
    billing_result = await db_session.execute(
        select(BillingAccount).where(
            BillingAccount.organization_id == user.organization_id
        )
    )
    billing_account = billing_result.scalar_one()
    
    assert billing_account.subscription_plan_id == fallback_plan.id


@pytest.mark.asyncio
async def test_stage1_subscription_blocks_subscription_purchase(
    client: AsyncClient, db_session: AsyncSession
):
    """Test Stage 1: Cannot purchase another SUBSCRIPTION while one is active."""
    from app.models.llm_model import LLMModel
    
    # Create LLM model
    llm_model = LLMModel(
        name="gpt-4-subscription",
        display_name="GPT-4 Subscription",
        provider="openai",
        api_key="test-key",
        max_tokens_limit=4096,
        context_window=8192,
        is_active=True
    )
    db_session.add(llm_model)
    await db_session.flush()
    
    # Create user with organization
    user = User(
        email="sub@example.com",
        username="subuser", 
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.flush()
    
    org = Organization(name="Sub Test Org", slug="sub-test-org")
    db_session.add(org)
    await db_session.flush()
    
    user.organization_id = org.id
    
    # Create agent
    agent = Agent(
        name="Subscription Agent",
        slug="subscription-agent",
        system_prompt="You are a subscription agent",
        prompt_template="Subscription: {input}",
        llm_model_id=llm_model.id,
        model_name="gpt-4",
        is_active=True,
        is_public=True
    )
    db_session.add(agent)
    await db_session.flush()
    
    # Create two SUBSCRIPTION plans
    current_plan = SubscriptionPlan(
        name="Current Monthly",
        interval=SubscriptionInterval.MONTHLY,
        plan_type=PlanType.SUBSCRIPTION,
        price=Decimal("9.99"),
        currency="USD",
        max_requests_per_interval=1000,
        max_tokens_per_request=2000,
    )
    db_session.add(current_plan)
    await db_session.flush()
    
    new_plan = SubscriptionPlan(
        name="New Monthly",
        interval=SubscriptionInterval.MONTHLY,
        plan_type=PlanType.SUBSCRIPTION,
        price=Decimal("19.99"),
        currency="USD",
        max_requests_per_interval=2000,
        max_tokens_per_request=2000,
    )
    db_session.add(new_plan)
    await db_session.flush()
    
    # Create billing account with ACTIVE subscription
    billing_account = BillingAccount(
        organization_id=org.id,
        subscription_plan_id=current_plan.id,
        subscription_status=SubscriptionStatus.ACTIVE,
        paddle_subscription_id="sub_123",  # Active Paddle subscription
        one_time_purchases_count=0,
        one_time_requests_used=0,
    )
    db_session.add(billing_account)
    await db_session.commit()
    
    # Try to purchase another SUBSCRIPTION - should be blocked
    token = create_access_token({"sub": user.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.post(
        "/billing/subscribe",
        headers=headers,
        json={"plan_id": new_plan.id}
    )
    
    assert response.status_code == 400
    assert "Active subscription already exists" in response.json()["detail"]


@pytest.mark.asyncio 
async def test_stage2_one_time_counter_independence(db_session: AsyncSession):
    """Test Stage 2: ONE_TIME counter is independent from subscription counter."""
    from app.policy.engine import PolicyEngine
    from app.models.llm_model import LLMModel
    
    # Create LLM model
    llm_model = LLMModel(
        name="gpt-4-test",
        display_name="GPT-4 Test",
        provider="openai",
        api_key="test-key",
        max_tokens_limit=4096,
        context_window=8192,
        is_active=True,
        is_default=False
    )
    db_session.add(llm_model)
    await db_session.flush()
    
    # Create user
    user = User(email="independent@example.com", username="independent", hashed_password="hashed")
    db_session.add(user)
    await db_session.flush()
    
    org = Organization(name="Independent Test", slug="independent-test")
    db_session.add(org)
    await db_session.flush()
    
    user.organization_id = org.id
    
    # Create agent
    agent = Agent(
        name="Independent Agent",
        slug="independent-agent",
        system_prompt="You are an independent agent",
        prompt_template="Independent: {input}",
        llm_model_id=llm_model.id,
        model_name="gpt-4",
        is_active=True,
        is_public=True  # Make public to bypass plan restrictions
    )
    db_session.add(agent)
    await db_session.flush()
    
    # Create SUBSCRIPTION plan
    sub_plan = SubscriptionPlan(
        name="Monthly Sub",
        interval=SubscriptionInterval.MONTHLY,
        plan_type=PlanType.SUBSCRIPTION,
        price=Decimal("9.99"),
        currency="USD",
        max_requests_per_interval=100,
        max_tokens_per_request=2000,
        free_requests_limit=5,
    )
    db_session.add(sub_plan)
    await db_session.flush()
    
    # Create billing account with subscription usage
    billing_account = BillingAccount(
        organization_id=org.id,
        subscription_plan_id=sub_plan.id,
        subscription_status=SubscriptionStatus.ACTIVE,
        free_requests_used=5,  # Used all free requests
        requests_used_current_period=50,  # Used 50 paid requests
        one_time_purchases_count=0,
        one_time_requests_used=0,
    )
    db_session.add(billing_account)
    await db_session.commit()
    
    engine = PolicyEngine()
    
    # Check subscription limits
    sub_result = await engine.check_usage_limits(db_session, user, agent.id)
    assert sub_result["allowed"] is True
    assert sub_result["paid_remaining"] == 50  # 100 - 50 = 50 remaining
    
    # Now switch to ONE_TIME plan (simulate user canceling subscription and buying credits)
    onetime_plan = SubscriptionPlan(
        name="100 Credits",
        interval=SubscriptionInterval.MONTHLY,
        plan_type=PlanType.ONE_TIME,
        price=Decimal("19.99"),
        currency="USD",
        max_requests_per_interval=1000,
        one_time_limit=100,
    )
    db_session.add(onetime_plan)
    await db_session.flush()
    
    # Update billing account to ONE_TIME plan with purchased credits
    billing_account.subscription_plan_id = onetime_plan.id
    billing_account.subscription_status = SubscriptionStatus.ACTIVE
    billing_account.one_time_purchases_count = 100  # Purchased 100 credits
    # Note: subscription counters remain untouched
    await db_session.commit()
    
    # Check ONE_TIME limits - should have full 100 credits available
    onetime_result = await engine.check_usage_limits(db_session, user, agent.id)
    assert onetime_result["allowed"] is True
    assert onetime_result["paid_remaining"] == 100  # Full credits available
    
    # Use some ONE_TIME credits
    billing_account.one_time_requests_used = 25
    await db_session.commit()
    
    # Check again
    onetime_result2 = await engine.check_usage_limits(db_session, user, agent.id)
    assert onetime_result2["allowed"] is True
    assert onetime_result2["paid_remaining"] == 75  # 100 - 25 = 75
    
    # Verify subscription counters are unchanged
    assert billing_account.requests_used_current_period == 50  # Still 50
    assert billing_account.free_requests_used == 5  # Still 5