"""Tests for billing API endpoints."""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import select
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.models.organization import Organization
from app.models.billing import BillingAccount, SubscriptionPlan, SubscriptionStatus, SubscriptionInterval


@pytest.fixture
async def subscription_plan(db_session):
    """Create a test subscription plan."""
    plan = SubscriptionPlan(
        name="Monthly",
        interval=SubscriptionInterval.MONTHLY,
        price=Decimal("19.99"),
        currency="USD",
        max_requests_per_interval=10000,
        max_tokens_per_request=2000,
        has_api_access=True,
        has_priority_support=True,
        has_advanced_analytics=False,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    return plan


@pytest.mark.asyncio
async def test_get_billing_account_auto_provisions(
    client: AsyncClient, auth_header: dict, user: User, db_session
):
    """Test GET /billing/account auto-provisions empty account."""
    response = await client.get("/billing/account", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["organization_id"] == user.organization_id
    assert data["status"] == SubscriptionStatus.TRIALING.value
    assert data["balance"] == "0.00"


@pytest.mark.asyncio
async def test_get_billing_usage_empty(
    client: AsyncClient, auth_header: dict
):
    """Test GET /billing/usage with no usage records."""
    response = await client.get("/billing/usage?days=30", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["requests"] == 0
    assert data["tokens"] == 0
    assert data["cost"] == "0.000000"


@pytest.mark.asyncio
async def test_subscribe_to_plan(
    client: AsyncClient, auth_header: dict, subscription_plan, db_session
):
    """Test POST /billing/subscribe."""
    response = await client.post(
        "/billing/subscribe",
        json={"plan_id": subscription_plan.id},
        headers=auth_header,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["plan_id"] == subscription_plan.id
    assert data["plan_name"] == "Monthly"
    assert data["status"] == SubscriptionStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_subscribe_invalid_plan(
    client: AsyncClient, auth_header: dict
):
    """Test POST /billing/subscribe with invalid plan ID."""
    response = await client.post(
        "/billing/subscribe",
        json={"plan_id": 9999},
        headers=auth_header,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_subscription(
    client: AsyncClient, auth_header: dict, subscription_plan, db_session
):
    """Test POST /billing/cancel."""
    # First subscribe
    await client.post(
        "/billing/subscribe",
        json={"plan_id": subscription_plan.id},
        headers=auth_header,
    )
    
    # Then cancel
    response = await client.post("/billing/cancel", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == SubscriptionStatus.CANCELED.value
