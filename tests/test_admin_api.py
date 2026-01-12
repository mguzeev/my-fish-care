"""Tests for admin panel API."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.organization import Organization
from app.models.billing import SubscriptionPlan, SubscriptionInterval, BillingAccount, SubscriptionStatus
from app.models.policy import PolicyRule
from app.models.prompt import PromptVersion
from app.models.agent import Agent
import json


@pytest.mark.asyncio
async def test_admin_dashboard_requires_admin(client: AsyncClient, auth_header: dict):
    """Test that dashboard requires admin role."""
    response = await client.get("/admin/dashboard/stats", headers=auth_header)
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
        is_superuser=True,
        organization_id=None,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.get("/admin/dashboard/stats", headers=headers)
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
        is_superuser=True,
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
        is_superuser=True,
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
        is_superuser=True,
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
        is_superuser=True,
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
        is_superuser=True,
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
        is_superuser=True,
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
        is_superuser=True,
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
        is_superuser=True,
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


@pytest.mark.asyncio
async def test_admin_create_and_list_prompts(
    client: AsyncClient, db_session: AsyncSession, agent_factory
):
    """Create prompt version for an agent and list it."""
    from app.core.security import get_password_hash, create_access_token

    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        is_superuser=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    agent: Agent = await agent_factory(name="Prompted", slug="prompted")

    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        f"/admin/agents/{agent.id}/prompts",
        headers=headers,
        json={
            "name": "Welcome",
            "version": "1.0.0",
            "system_prompt": "Be nice",
            "user_template": "Hello {name}",
            "variables": [{"name": "name", "required": True}],
            "is_active": True,
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["agent_id"] == agent.id
    assert created["is_active"] is True

    list_resp = await client.get(f"/admin/agents/{agent.id}/prompts", headers=headers)
    assert list_resp.status_code == 200
    prompts = list_resp.json()
    assert len(prompts) == 1
    assert prompts[0]["name"] == "Welcome"


@pytest.mark.asyncio
async def test_admin_activate_prompt_version(
    client: AsyncClient, db_session: AsyncSession, agent_factory
):
    """Activating a prompt deactivates previous active version."""
    from app.core.security import get_password_hash, create_access_token

    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        is_superuser=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    agent: Agent = await agent_factory(name="Prompted2", slug="prompted2")
    agent_id = agent.id

    # Seed two prompt versions
    p1 = PromptVersion(
        agent_id=agent_id,
        name="Old",
        version="1.0",
        system_prompt="S1",
        user_template="Hi {name}",
        variables_json="[]",
        is_active=True,
    )
    p2 = PromptVersion(
        agent_id=agent_id,
        name="New",
        version="2.0",
        system_prompt="S2",
        user_template="Hello {name}",
        variables_json="[]",
        is_active=False,
    )
    db_session.add_all([p1, p2])
    await db_session.commit()
    await db_session.refresh(p1)
    await db_session.refresh(p2)

    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(f"/admin/prompts/{p2.id}/activate", headers=headers)
    assert resp.status_code == 200
    activated = resp.json()
    assert activated["id"] == p2.id
    assert activated["is_active"] is True

    # Check DB states
    db_session.expire_all()
    result = await db_session.execute(
        __import__('sqlalchemy').select(PromptVersion).where(PromptVersion.agent_id == agent_id)
    )
    prompts = result.scalars().all()
    active_count = sum(1 for p in prompts if p.is_active)
    assert active_count == 1
    assert any(p.id == p2.id and p.is_active for p in prompts)

@pytest.mark.asyncio
async def test_admin_list_agents(client: AsyncClient, admin_client: AsyncClient, db_session: AsyncSession):
    """Test listing agents."""
    # Create test agents
    agents = [
        Agent(name="Agent 1", slug="agent-1", system_prompt="You are helpful", model_name="gpt-4", is_active=True),
        Agent(name="Agent 2", slug="agent-2", system_prompt="You are kind", model_name="gpt-3.5-turbo", is_active=False),
    ]
    for agent in agents:
        db_session.add(agent)
    await db_session.commit()
    
    response = await admin_client.get("/admin/agents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    assert any(a["slug"] == "agent-1" for a in data)
    assert any(a["slug"] == "agent-2" for a in data)


@pytest.mark.asyncio
async def test_admin_list_agents_active_only(client: AsyncClient, admin_client: AsyncClient, db_session: AsyncSession):
    """Test listing only active agents."""
    # Create test agents
    agents = [
        Agent(name="Active Agent", slug="active-agent", system_prompt="Active", is_active=True),
        Agent(name="Inactive Agent", slug="inactive-agent", system_prompt="Inactive", is_active=False),
    ]
    for agent in agents:
        db_session.add(agent)
    await db_session.commit()
    
    response = await admin_client.get("/admin/agents?active_only=true")
    assert response.status_code == 200
    data = response.json()
    assert all(a["is_active"] for a in data)


@pytest.mark.asyncio
async def test_admin_get_agent(client: AsyncClient, admin_client: AsyncClient, db_session: AsyncSession):
    """Test getting single agent details."""
    agent = Agent(
        name="Test Agent",
        slug="test-agent",
        description="A test agent",
        system_prompt="Test prompt",
        model_name="gpt-4",
        temperature=0.8,
        max_tokens=1500,
        is_active=True,
        is_public=False,
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    
    response = await admin_client.get(f"/admin/agents/{agent.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == agent.id
    assert data["name"] == "Test Agent"
    assert data["slug"] == "test-agent"
    assert data["temperature"] == 0.8
    assert data["max_tokens"] == 1500


@pytest.mark.asyncio
async def test_admin_create_agent(client: AsyncClient, admin_client: AsyncClient):
    """Test creating new agent."""
    payload = {
        "name": "New Agent",
        "slug": "new-agent",
        "description": "A new test agent",
        "system_prompt": "You are a helpful assistant",
        "model_name": "gpt-4-turbo",
        "temperature": 0.5,
        "max_tokens": 3000,
        "is_active": True,
        "is_public": True,
    }
    
    response = await admin_client.post("/admin/agents", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Agent"
    assert data["slug"] == "new-agent"
    assert data["model_name"] == "gpt-4-turbo"
    assert data["temperature"] == 0.5
    assert data["is_public"] is True
    
    # Verify it can be retrieved
    get_response = await admin_client.get(f"/admin/agents/{data['id']}")
    assert get_response.status_code == 200


@pytest.mark.asyncio
async def test_admin_create_agent_duplicate_slug(client: AsyncClient, admin_client: AsyncClient, db_session: AsyncSession):
    """Test that duplicate slugs are rejected."""
    # Create first agent
    agent = Agent(name="Agent 1", slug="duplicate-slug", system_prompt="Test")
    db_session.add(agent)
    await db_session.commit()
    
    # Try to create another with same slug
    payload = {
        "name": "Agent 2",
        "slug": "duplicate-slug",
    }
    
    response = await admin_client.post("/admin/agents", json=payload)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_update_agent(client: AsyncClient, admin_client: AsyncClient, db_session: AsyncSession):
    """Test updating agent."""
    agent = Agent(
        name="Original Name",
        slug="original-slug",
        system_prompt="Test prompt",
        model_name="gpt-3.5-turbo",
        temperature=0.7,
        is_active=True,
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    
    payload = {
        "name": "Updated Name",
        "model_name": "gpt-4",
        "temperature": 0.9,
        "is_active": False,
    }
    
    response = await admin_client.put(f"/admin/agents/{agent.id}", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["model_name"] == "gpt-4"
    assert data["temperature"] == 0.9
    assert data["is_active"] is False
    # Slug should not change if not provided
    assert data["slug"] == "original-slug"


@pytest.mark.asyncio
async def test_admin_delete_agent(client: AsyncClient, admin_client: AsyncClient, db_session: AsyncSession):
    """Test soft delete agent."""
    agent = Agent(name="To Delete", slug="to-delete", system_prompt="Test", is_active=True)
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    agent_id = agent.id
    
    response = await admin_client.delete(f"/admin/agents/{agent_id}")
    assert response.status_code == 200
    
    # Verify it's marked inactive but still exists
    verify = await admin_client.get(f"/admin/agents/{agent_id}")
    assert verify.status_code == 200
    assert verify.json()["is_active"] is False