import pytest
from app.core.security import create_access_token
from app.agents.runtime import agent_runtime
from app.models.agent import Agent
from app.models.billing import SubscriptionPlan, BillingAccount, SubscriptionInterval, SubscriptionStatus
from app.models.organization import Organization
from app.models.user import User
from sqlalchemy import select
from decimal import Decimal


@pytest.mark.asyncio
async def test_e2e_register_login_invoke(client, db_session, monkeypatch, llm_model):
    # Register a user
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "flow@example.com",
            "username": "flow_user",
            "password": "FlowPass123",
        },
    )
    assert register_resp.status_code == 201

    # Login to obtain tokens
    login_resp = await client.post(
        "/auth/login",
        json={"email": "flow@example.com", "password": "FlowPass123"},
    )
    tokens = login_resp.json()
    
    # Get created user and create organization
    user_result = await db_session.execute(select(User).where(User.email == "flow@example.com"))
    user = user_result.scalar_one()
    
    org = Organization(name="Flow Org", slug="flow-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    
    user.organization_id = org.id
    await db_session.commit()

    # Create agent directly in DB
    agent = Agent(
        name="Flow Agent",
        slug="flow-agent",
        system_prompt="You are flow agent",
        prompt_template="Echo: {input}",
        model_name="gpt-4",
        is_public=False,
        llm_model_id=llm_model.id,
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    
    # Create plan with agent
    plan = SubscriptionPlan(
        name="E2E Test Plan",
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
    
    # Create billing account with subscription
    billing = BillingAccount(
        organization_id=org.id,
        subscription_plan_id=plan.id,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(billing)
    await db_session.commit()

    async def fake_run(agent_obj, variables, stream=False, prompt_version=None):
        assert variables["input"] == "Hello"
        return "Echo: Hello", {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}

    monkeypatch.setattr(agent_runtime, "run", fake_run)

    invoke_resp = await client.post(
        f"/agents/{agent.id}/invoke",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"input": "Hello"},
    )

    assert invoke_resp.status_code == 200
    assert invoke_resp.json()["output"].startswith("Echo")
