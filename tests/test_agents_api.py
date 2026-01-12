import pytest
from app.agents.runtime import agent_runtime
from app.core.security import create_access_token
from app.models.billing import SubscriptionPlan, BillingAccount, SubscriptionInterval, SubscriptionStatus
from app.models.organization import Organization
from decimal import Decimal


@pytest.mark.asyncio
async def test_agent_invoke_plain(client, db_session, agent_factory, user_factory, monkeypatch):
    # Create organization
    org = Organization(name="Test Org", slug="test-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    
    # Create user with organization
    user = await user_factory(email="agent@example.com", username="agent_user", organization_id=org.id)
    token = create_access_token({"sub": user.id})
    
    # Create agent
    agent = await agent_factory(slug="invoke-agent")
    
    # Create plan with agent
    plan = SubscriptionPlan(
        name="Test Plan",
        interval=SubscriptionInterval.MONTHLY,
        price=Decimal("9.99"),
        currency="USD",
        max_requests_per_interval=1000,
        max_tokens_per_request=2000,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    
    # Add agent to plan
    plan.agents.append(agent)
    
    # Create billing account with subscription
    billing = BillingAccount(
        organization_id=org.id,
        subscription_plan_id=plan.id,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(billing)
    await db_session.commit()

    async def fake_run(agent_obj, variables, stream=False, prompt_version=None):
        assert variables["input"] == "ping"
        assert variables["extra"] == 1
        assert stream is False
        return "pong"

    monkeypatch.setattr(agent_runtime, "run", fake_run)

    resp = await client.post(
        f"/agents/{agent.id}/invoke",
        headers={"Authorization": f"Bearer {token}"},
        json={"input": "ping", "variables": {"extra": 1}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["output"] == "pong"
    assert body["agent_id"] == agent.id


@pytest.mark.asyncio
async def test_agent_invoke_streaming(client, db_session, agent_factory, user_factory, monkeypatch):
    # Create organization
    org = Organization(name="Test Org 2", slug="test-org-2")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    
    user = await user_factory(email="stream@example.com", username="stream_user", organization_id=org.id)
    token = create_access_token({"sub": user.id})
    agent = await agent_factory(slug="stream-agent")
    
    # Create plan with agent
    plan = SubscriptionPlan(
        name="Test Plan Stream",
        interval=SubscriptionInterval.MONTHLY,
        price=Decimal("9.99"),
        currency="USD",
        max_requests_per_interval=1000,
        max_tokens_per_request=2000,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    
    plan.agents.append(agent)
    
    billing = BillingAccount(
        organization_id=org.id,
        subscription_plan_id=plan.id,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(billing)
    await db_session.commit()

    async def fake_run(agent_obj, variables, stream=False, prompt_version=None):
        async def gen():
            yield "chunk-1"
            yield "chunk-2"
        return gen()

    monkeypatch.setattr(agent_runtime, "run", fake_run)

    async with client.stream(
        "POST",
        f"/agents/{agent.id}/invoke",
        headers={"Authorization": f"Bearer {token}"},
        json={"input": "hello", "stream": True},
    ) as response:
        assert response.status_code == 200
        text = "".join([chunk async for chunk in response.aiter_text()])

    assert "chunk-1" in text and "chunk-2" in text
