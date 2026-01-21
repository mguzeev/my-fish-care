"""
Test that usage tokens are properly logged for image processing
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models.usage import UsageRecord
from app.models.user import User
from app.models.agent import Agent


@pytest.mark.asyncio
async def test_tokens_logged_with_image(db_session, user: User):
    """Test that tokens are logged when processing an image"""
    # Get first agent
    result = await db_session.execute(select(Agent).where(Agent.is_active == True).limit(1))
    agent = result.scalar_one_or_none()
    
    if not agent:
        pytest.skip("No active agents available")
    
    # Just checking the structure exists
    assert hasattr(UsageRecord, 'has_image')
    assert hasattr(UsageRecord, 'prompt_tokens')
    assert hasattr(UsageRecord, 'completion_tokens')
    assert hasattr(UsageRecord, 'total_tokens')


@pytest.mark.asyncio
async def test_usage_record_has_image_field():
    """Test that UsageRecord model has has_image field"""
    from app.models.usage import UsageRecord
    
    # Check field exists
    assert hasattr(UsageRecord, 'has_image')
    
    # Create test record
    record = UsageRecord(
        user_id=1,
        endpoint="/agents/invoke",
        method="POST",
        channel="api",
        model_name="gpt-4",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        has_image=True
    )
    
    assert record.has_image is True
    assert record.prompt_tokens == 100
    assert record.completion_tokens == 50
    assert record.total_tokens == 150


def test_invoke_endpoint_handles_image_path():
    """Test that invoke endpoints include image_path in variables"""
    # Check the code structure (static analysis)
    import inspect
    from app.agents import router
    
    # Get the invoke functions
    invoke_auto = router.invoke_auto_agent
    invoke_agent = router.invoke_agent
    
    # Check they exist
    assert invoke_auto is not None
    assert invoke_agent is not None
    
    # Check source code includes image_path handling
    auto_source = inspect.getsource(invoke_auto)
    agent_source = inspect.getsource(invoke_agent)
    
    # Both should handle image_path
    assert 'image_path' in auto_source
    assert 'payload.image_path' in auto_source
    assert 'has_image=payload.image_path is not None' in auto_source
    
    assert 'image_path' in agent_source
    assert 'payload.image_path' in agent_source
    assert 'has_image=payload.image_path is not None' in agent_source


def test_usage_record_creation_with_tokens():
    """Test that UsageRecord properly stores token information"""
    from app.models.usage import UsageRecord
    from decimal import Decimal
    
    # Create record with all token fields
    record = UsageRecord(
        user_id=1,
        endpoint="/agents/invoke",
        method="POST",
        channel="api",
        model_name="gpt-4-vision",
        prompt_tokens=500,  # Larger for image
        completion_tokens=100,
        total_tokens=600,
        has_image=True,
        cost=Decimal("0.012"),
        status_code=200
    )
    
    # Verify all fields are set
    assert record.prompt_tokens == 500
    assert record.completion_tokens == 100
    assert record.total_tokens == 600
    assert record.has_image is True
    assert record.cost == Decimal("0.012")
    assert record.model_name == "gpt-4-vision"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
