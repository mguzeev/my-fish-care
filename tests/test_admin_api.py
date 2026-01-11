"""Tests for admin panel API."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.organization import Organization
from app.models.billing import SubscriptionPlan, SubscriptionInterval, BillingAccount, SubscriptionStatus
from app.models.policy import PolicyRule
import json


@pytest.mark.asyncio
async def test_admin_dashboard_requires_admin(client: AsyncClient, auth_header: dict):
    """Test that dashboard requires admin role."""
    response = await client.get("/admin/dashboard", headers=auth_header)
    # Regular user should get 403
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_dashboard_stats(client: AsyncClient, db_session: AsyncSession):
    """Test admin dashboard statistics endpoint."""
    # Create admin user
    from app.core.security import get_password_hash, create_access_token
    
    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        role="admin",
        organization_id=None,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.get("/admin/dashboard", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "total_users" in data
    assert "total_organizations" in data
    assert "active_subscriptions" in data
    assert "revenue_today" in data
    assert data["total_users"] >= 1


@pytest.mark.asyncio
async def test_admin_list_plans(client: AsyncClient, db_session: AsyncSession):
    """Test listing subscription plans."""
    from app.core.security import get_password_hash, create_access_token
    
    # Create admin
    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    # Create a plan
    plan = SubscriptionPlan(
        name="Test Plan",
        interval=SubscriptionInterval.MONTHLY,
        price=19.99,
        currency="USD",
        max_requests_per_interval=1000,
        max_tokens_per_request=2000,
        has_api_access=True,
    )
    db_session.add(plan)
    await db_session.commit()
    
    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.get("/admin/plans", headers=headers)
    assert response.status_code == 200
    plans = response.json()
    assert len(plans) >= 1
    assert plans[0]["name"] == "Test Plan"


@pytest.mark.asyncio
async def test_admin_create_plan(client: AsyncClient, db_session: AsyncSession):
    """Test creating subscription plan."""
    from app.core.security import get_password_hash, create_access_token
    
    # Create admin
    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.post(
        "/admin/plans",
        headers=headers,
        json={
            "name": "Premium Plan",
            "interval": "yearly",
            "price": 199.99,
            "currency": "USD",
            "max_requests_per_interval": 150000,
            "max_tokens_per_request": 3000,
            "has_api_access": True,
            "has_priority_support": True,
            "has_advanced_analytics": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Premium Plan"
    assert data["interval"] == "yearly"


@pytest.mark.asyncio
async def test_admin_list_policies(client: AsyncClient, db_session: AsyncSession):
    """Test listing policy rules."""
    from app.core.security import get_password_hash, create_access_token
    
    # Create admin
    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    # Create a policy rule
    rule = PolicyRule(
        name="Test Rate Limit",
        rule_type="rate_limit",
        target_resource="/api",
        target_role="user",
        config=json.dumps({"limit": 100, "window_sec": 60}),
        is_active=True,
        priority=10,
    )
    db_session.add(rule)
    await db_session.commit()
    
    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.get("/admin/policies", headers=headers)
    assert response.status_code == 200
    policies = response.json()
    assert len(policies) >= 1
    assert policies[0]["name"] == "Test Rate Limit"


@pytest.mark.asyncio
async def test_admin_create_policy(client: AsyncClient, db_session: AsyncSession):
    """Test creating policy rule."""
    from app.core.security import get_password_hash, create_access_token
    
    # Create admin
    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.post(
        "/admin/policies",
        headers=headers,
        json={
            "name": "Admin Rate Limit",
            "rule_type": "rate_limit",
            "target_resource": "/admin",
            "target_role": "admin",
            "config": {"limit": 1000, "window_sec": 60},
            "is_active": True,
            "priority": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Admin Rate Limit"
    assert data["target_role"] == "admin"


@pytest.mark.asyncio
async def test_admin_list_user_activity(client: AsyncClient, db_session: AsyncSession, user: User):
    """Test listing user activity."""
    from app.core.security import get_password_hash, create_access_token
    
    # Create admin
    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.get("/admin/users/activity", headers=headers)
    assert response.status_code == 200
    activities = response.json()
    assert isinstance(activities, list)
    # Should have at least the regular user
    assert len(activities) >= 1


@pytest.mark.asyncio
async def test_admin_list_organizations(client: AsyncClient, db_session: AsyncSession, user: User):
    """Test listing organizations."""
    from app.core.security import get_password_hash, create_access_token
    
    # Create admin
    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.get("/admin/organizations", headers=headers)
    assert response.status_code == 200
    orgs = response.json()
    assert isinstance(orgs, list)
    assert len(orgs) >= 1  # At least the test org


@pytest.mark.asyncio
async def test_admin_update_plan(client: AsyncClient, db_session: AsyncSession):
    """Test updating subscription plan."""
    from app.core.security import get_password_hash, create_access_token
    
    # Create admin
    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    # Create a plan to update
    plan = SubscriptionPlan(
        name="Old Name",
        interval=SubscriptionInterval.MONTHLY,
        price=19.99,
        currency="USD",
        max_requests_per_interval=1000,
        max_tokens_per_request=2000,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    
    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.put(
        f"/admin/plans/{plan.id}",
        headers=headers,
        json={
            "name": "New Name",
            "interval": "yearly",
            "price": 99.99,
            "currency": "USD",
            "max_requests_per_interval": 100000,
            "max_tokens_per_request": 3000,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    # Price is returned as string due to Decimal serialization
    assert float(data["price"]) == 99.99


@pytest.mark.asyncio
async def test_admin_delete_plan(client: AsyncClient, db_session: AsyncSession):
    """Test deleting subscription plan."""
    from app.core.security import get_password_hash, create_access_token
    
    # Create admin
    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    # Create a plan to delete
    plan = SubscriptionPlan(
        name="Plan to Delete",
        interval=SubscriptionInterval.DAILY,
        price=0.99,
        currency="USD",
        max_requests_per_interval=100,
        max_tokens_per_request=1000,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    
    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.delete(f"/admin/plans/{plan.id}", headers=headers)
    assert response.status_code == 200
    
    # Verify it's deleted
    result = await db_session.execute(
        __import__('sqlalchemy').select(SubscriptionPlan).where(SubscriptionPlan.id == plan.id)
    )
    assert result.scalar_one_or_none() is None
