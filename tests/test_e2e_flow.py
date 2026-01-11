import pytest
from app.core.security import create_access_token
from app.agents.runtime import agent_runtime
from app.models.agent import Agent


@pytest.mark.asyncio
async def test_e2e_register_login_invoke(client, db_session, monkeypatch):
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

    # Create agent directly in DB
    agent = Agent(
        name="Flow Agent",
        slug="flow-agent",
        system_prompt="You are flow agent",
        prompt_template="Echo: {input}",
        model_name="gpt-4",
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)

    async def fake_run(agent_obj, variables, stream=False):
        assert variables["input"] == "Hello"
        return "Echo: Hello"

    monkeypatch.setattr(agent_runtime, "run", fake_run)

    invoke_resp = await client.post(
        f"/agents/{agent.id}/invoke",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"input": "Hello"},
    )

    assert invoke_resp.status_code == 200
    assert invoke_resp.json()["output"].startswith("Echo")
