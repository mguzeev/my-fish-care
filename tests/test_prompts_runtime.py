import types
import json
import pytest
from app.prompts.models import PromptTemplate, PromptVariable
from app.agents.runtime import agent_runtime
from app.models.agent import Agent
from app.models.prompt import PromptVersion


def test_prompt_template_rendering():
    template = PromptTemplate(
        name="welcome",
        version="1.0.0",
        system="Be concise",
        user="Hello {name}",
        variables=[PromptVariable(name="name", required=True)],
    )

    rendered = template.render({"name": "Alice"})
    messages = rendered.to_messages()

    assert messages[0]["content"] == "Be concise"
    assert messages[1]["content"] == "Hello Alice"

    with pytest.raises(ValueError):
        template.render({})


@pytest.mark.asyncio
async def test_agent_runtime_completion(monkeypatch, llm_model):
    class FakeMessage:
        def __init__(self, content: str):
            self.content = content

    class FakeChoice:
        def __init__(self, content: str):
            self.message = FakeMessage(content)
            self.delta = types.SimpleNamespace(content=content)

    class FakeResponse:
        def __init__(self, content: str):
            self.choices = [FakeChoice(content)]

    class FakeStreamChoice:
        def __init__(self, content: str):
            self.delta = types.SimpleNamespace(content=content)

    class FakeStreamChunk:
        def __init__(self, content: str):
            self.choices = [FakeStreamChoice(content)]

    async def fake_create(*args, **kwargs):
        if kwargs.get("stream"):
            async def gen():
                yield FakeStreamChunk("hello")
                yield FakeStreamChunk(" world")
            return gen()
        return FakeResponse("ok")

    class FakeCompletions:
        async def create(self, *args, **kwargs):
            return await fake_create(*args, **kwargs)

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    # Mock _get_client_for_agent to return our fake client
    fake_client = FakeClient()
    monkeypatch.setattr(agent_runtime, "_get_client_for_agent", lambda agent: fake_client)

    agent = Agent(
        name="Demo",
        slug="demo",
        system_prompt="You are a demo agent",
        prompt_template="{input}",
        llm_model_id=llm_model.id,
        max_tokens=2000,
    )
    agent.llm_model = llm_model

    result = await agent_runtime.run(agent, {"input": "Ping"}, stream=False)
    assert result == "ok"

    chunks = []
    stream_gen = await agent_runtime.run(agent, {"input": "Ping"}, stream=True)
    async for chunk in stream_gen:
        chunks.append(chunk)
    assert "hello" in "".join(chunks)


@pytest.mark.asyncio
async def test_agent_runtime_uses_prompt_version(monkeypatch, llm_model):
    class FakeMessage:
        def __init__(self, content: str):
            self.content = content

    class FakeChoice:
        def __init__(self, content: str):
            self.message = FakeMessage(content)
            self.delta = types.SimpleNamespace(content=content)

    class FakeResponse:
        def __init__(self, content: str):
            self.choices = [FakeChoice(content)]

    async def fake_create(*args, **kwargs):
        return FakeResponse("prompt-version-ok")

    class FakeCompletions:
        async def create(self, *args, **kwargs):
            return await fake_create(*args, **kwargs)

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    # Mock _get_client_for_agent to return our fake client
    fake_client = FakeClient()
    monkeypatch.setattr(agent_runtime, "_get_client_for_agent", lambda agent: fake_client)

    agent = Agent(
        name="Demo",
        slug="demo",
        system_prompt="You are a demo agent",
        prompt_template="{input}",
        llm_model_id=llm_model.id,
        max_tokens=2000,
    )
    agent.llm_model = llm_model

    prompt_version = PromptVersion(
        agent_id=1,
        name="DB Prompt",
        version="2.0",
        system_prompt="DB system",
        user_template="Hello {topic}",
        variables_json=json.dumps([{"name": "topic", "required": True}]),
    )

    result = await agent_runtime.run(
        agent,
        {"topic": "AI", "input": "Hi"},
        prompt_version=prompt_version,
        stream=False,
    )

    assert result == "prompt-version-ok"
