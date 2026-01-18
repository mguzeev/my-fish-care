#!/usr/bin/env python3
"""Link default plan with basic agents."""
import asyncio
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core.database import AsyncSessionLocal
from app.models.billing import SubscriptionPlan  
from app.models.agent import Agent
from sqlalchemy import select


async def setup_default_plan():
    """Ensure default plan is linked with at least one agent."""
    async with AsyncSessionLocal() as db:
        # Find default plan
        result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.is_default == True)
        )
        default_plan = result.scalar_one_or_none()
        
        if not default_plan:
            print("❌ No default plan found")
            return
            
        # Find basic agents
        agent_result = await db.execute(
            select(Agent).where(Agent.is_active == True)
        )
        agents = agent_result.scalars().all()
        
        if not agents:
            print("❌ No active agents found")
            return
            
        # Link first agent to default plan if not linked
        if len(default_plan.agents) == 0:
            default_plan.agents.append(agents[0])
            await db.commit()
            print(f"✅ Linked agent '{agents[0].name}' to default plan '{default_plan.name}'")
        else:
            print(f"✅ Default plan '{default_plan.name}' already has {len(default_plan.agents)} agents")


if __name__ == "__main__":
    asyncio.run(setup_default_plan())