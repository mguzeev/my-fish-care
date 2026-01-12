"""Agent API endpoints."""
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.auth.dependencies import get_current_active_user
from app.agents.runtime import agent_runtime
from app.agents.schemas import AgentInvokeRequest, AgentResponse
from app.models.agent import Agent
from app.models.prompt import PromptVersion


router = APIRouter(prefix="/agents", tags=["Agents"])


async def _get_agent_or_404(agent_id: int, db: AsyncSession) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if not agent.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent is inactive")
    return agent


async def _get_active_prompt(agent_id: int, db: AsyncSession) -> PromptVersion | None:
    result = await db.execute(
        select(PromptVersion)
        .where(PromptVersion.agent_id == agent_id, PromptVersion.is_active.is_(True))
        .order_by(PromptVersion.updated_at.desc())
    )
    return result.scalars().first()


@router.post("/{agent_id}/invoke", response_model=AgentResponse)
async def invoke_agent(
    agent_id: int,
    payload: AgentInvokeRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_active_user),
):
    """Invoke an agent with user input (non-streaming by default)."""
    agent = await _get_agent_or_404(agent_id, db)

    # Merge variables ensuring 'input' is present
    variables = {"input": payload.input, **payload.variables}

    prompt_version = await _get_active_prompt(agent.id, db)

    if payload.stream:
        # Streaming response using text/event-stream
        async def streamer() -> AsyncGenerator[bytes, None]:
            async for chunk in await agent_runtime.run(agent, variables, prompt_version=prompt_version, stream=True):
                yield chunk.encode()

        return StreamingResponse(streamer(), media_type="text/plain")

    output = await agent_runtime.run(agent, variables, prompt_version=prompt_version, stream=False)
    return AgentResponse(agent_id=agent_id, output=output, model=agent.model_name)