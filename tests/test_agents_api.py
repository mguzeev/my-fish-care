import pytest
from app.agents.runtime import agent_runtime
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_agent_invoke_plain(client, db_session, agent_factory, user_factory, monkeypatch):
    user = await user_factory(email="agent@example.com", username="agent_user")
    token = create_access_token({"sub": user.id})
    agent = await agent_factory(slug="invoke-agent")

    async def fake_run(agent_obj, variables, stream=False):
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
async def test_agent_invoke_streaming(client, agent_factory, user_factory, monkeypatch):
    user = await user_factory(email="stream@example.com", username="stream_user")
    token = create_access_token({"sub": user.id})
    agent = await agent_factory(slug="stream-agent")

    async def fake_run(agent_obj, variables, stream=False):
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
