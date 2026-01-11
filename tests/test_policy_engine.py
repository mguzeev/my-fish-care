"""Tests for policy engine."""
import pytest
import json
from sqlalchemy import select

from app.policy.engine import engine
from app.models.policy import PolicyRule
from app.models.user import User


@pytest.mark.asyncio
async def test_policy_resource_access_deny(user: User, db_session):
    """Test resource access deny rule."""
    rule = PolicyRule(
        name="Deny webhook access to user role",
        rule_type="resource_access",
        target_resource="/webhook",
        target_role="user",
        config=json.dumps({"deny": True}),
        is_active=True,
        priority=10,
    )
    db_session.add(rule)
    await db_session.commit()
    
    # Should raise 403 when accessing webhook
    with pytest.raises(Exception) as exc_info:
        await engine.check_access(db_session, user, "/webhook", "access")
    assert "Access denied" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_policy_rate_limit(user: User, db_session):
    """Test rate limiting policy."""
    rule = PolicyRule(
        name="Limit user requests to 3/minute",
        rule_type="rate_limit",
        target_resource="/api/chat",
        target_role="user",
        config=json.dumps({"limit": 3, "window_sec": 60, "key": "chat_rate"}),
        is_active=True,
        priority=10,
    )
    db_session.add(rule)
    await db_session.commit()
    
    # First 3 calls should succeed
    for i in range(3):
        await engine.check_access(db_session, user, "/api/chat", "access")
    
    # 4th call should fail
    with pytest.raises(Exception) as exc_info:
        await engine.check_access(db_session, user, "/api/chat", "access")
    assert "Rate limit exceeded" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_policy_no_rules_allows_all(user: User, db_session):
    """Test that with no active rules, all access is allowed."""
    # Should not raise any exception
    await engine.check_access(db_session, user, "/any/endpoint", "access")
