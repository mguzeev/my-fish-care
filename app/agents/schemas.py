"""Pydantic schemas for agent invocation."""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class AgentInvokeRequest(BaseModel):
    """Request payload to invoke an agent."""

    input: str = Field(..., description="User input text")
    image_path: Optional[str] = Field(None, description="Path to uploaded image file in media directory")
    variables: Dict[str, Any] = Field(
        default_factory=dict, description="Additional variables for the prompt"
    )
    stream: bool = Field(False, description="Return streaming response if True")


class UsageInfo(BaseModel):
    """Usage limits information."""
    free_remaining: int
    paid_remaining: int
    should_upgrade: bool


class AgentResponse(BaseModel):
    """Non-streaming agent response."""

    agent_id: int
    agent_name: str
    output: str
    model: str
    processed_image: bool = False
    usage: Optional[UsageInfo] = None
    usage_tokens: Optional[int] = None