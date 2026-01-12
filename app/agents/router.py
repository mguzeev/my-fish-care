"""Agent API endpoints."""
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.core.database import get_db
from app.auth.dependencies import get_current_active_user
from app.agents.runtime import agent_runtime
from app.agents.schemas import AgentInvokeRequest, AgentResponse
from app.models.agent import Agent
from app.models.prompt import PromptVersion
from app.models.user import User
from app.models.billing import BillingAccount, SubscriptionPlan, SubscriptionStatus
from app.policy.engine import engine as policy_engine


router = APIRouter(prefix="/agents", tags=["Agents"])


class AgentListResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool
    version: str


@router.get("", response_model=list[AgentListResponse])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List agents accessible to the current user based on their subscription."""
    # Superusers see all active agents
    if current_user.is_superuser:
        result = await db.execute(select(Agent).where(Agent.is_active == True))
        agents = result.scalars().all()
        return [
            AgentListResponse(
                id=agent.id,
                name=agent.name,
                slug=agent.slug,
                description=agent.description,
                is_active=agent.is_active,
                version=agent.version,
            )
            for agent in agents
        ]
    
    # Get public agents
    public_result = await db.execute(
        select(Agent).where(Agent.is_active == True, Agent.is_public == True)
    )
    public_agents = list(public_result.scalars().all())
    
    # Get agents from user's subscription plan
    plan_agents = []
    if current_user.organization_id:
        billing_result = await db.execute(
            select(BillingAccount, SubscriptionPlan)
            .join(SubscriptionPlan, BillingAccount.subscription_plan_id == SubscriptionPlan.id)
            .where(
                BillingAccount.organization_id == current_user.organization_id,
                BillingAccount.subscription_status.in_([
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.TRIALING
                ])
            )
        )
        row = billing_result.one_or_none()
        if row:
            _, plan = row
            plan_with_agents = await db.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.id == plan.id)
            )
            plan_obj = plan_with_agents.scalar_one()
            plan_agents = [a for a in plan_obj.agents if a.is_active]
    
    # Combine and deduplicate
    all_agents = {agent.id: agent for agent in public_agents + plan_agents}
    
    return [
        AgentListResponse(
            id=agent.id,
            name=agent.name,
            slug=agent.slug,
            description=agent.description,
            is_active=agent.is_active,
            version=agent.version,
        )
        for agent in all_agents.values()
    ]



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
    current_user: User = Depends(get_current_active_user),
):
    """Invoke an agent with user input (non-streaming by default)."""
    # Check access through Policy Engine
    await policy_engine.check_agent_access(db, current_user, agent_id)
    
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