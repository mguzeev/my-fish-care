"""Tests for analytics endpoints."""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.usage import UsageRecord


@pytest.mark.asyncio
async def test_get_usage_trends(client: AsyncClient, auth_header: dict, user: User, db_session: AsyncSession):
    """Test getting usage trends."""
    # Add some sample usage records
    today = datetime.utcnow()
    for i in range(5):
        date = today - timedelta(days=i)
        record = UsageRecord(
            user_id=user.id,
            endpoint="/test",
            method="POST",
            channel="api",
            status_code=200,
            response_time_ms=100 + i * 10,
            prompt_tokens=100 + i * 10,
            completion_tokens=50 + i * 5,
            total_tokens=150 + i * 15,
            cost=Decimal("0.10") + Decimal(i) * Decimal("0.01"),
            created_at=date,
        )
        db_session.add(record)
    await db_session.commit()
    
    response = await client.get("/analytics/trends/usage?days=30", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "total_requests" in data
    assert "total_tokens" in data
    assert "total_cost" in data
    assert len(data["data"]) > 0


@pytest.mark.asyncio
async def test_get_trend_comparison(client: AsyncClient, auth_header: dict, user: User, db_session: AsyncSession):
    """Test week-over-week trend comparison."""
    today = datetime.utcnow()
    
    # Add current week records
    for i in range(7):
        date = today - timedelta(days=i)
        record = UsageRecord(
            user_id=user.id,
            endpoint="/api",
            method="GET",
            channel="api",
            status_code=200,
            response_time_ms=50,
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
            cost=Decimal("0.05"),
            created_at=date,
        )
        db_session.add(record)
    
    # Add previous week records
    for i in range(7, 14):
        date = today - timedelta(days=i)
        record = UsageRecord(
            user_id=user.id,
            endpoint="/api",
            method="GET",
            channel="api",
            status_code=200,
            response_time_ms=50,
            prompt_tokens=40,
            completion_tokens=20,
            total_tokens=60,
            cost=Decimal("0.04"),
            created_at=date,
        )
        db_session.add(record)
    
    await db_session.commit()
    
    response = await client.get("/analytics/trends/compare", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3  # requests, tokens, cost
    assert all("metric" in item for item in data)
    assert all("trend" in item for item in data)


@pytest.mark.asyncio
async def test_forecast_monthly_usage(client: AsyncClient, auth_header: dict, user: User, db_session: AsyncSession):
    """Test monthly usage forecast."""
    today = datetime.utcnow()
    
    # Add 30 days of usage data
    for i in range(30):
        date = today - timedelta(days=i)
        record = UsageRecord(
            user_id=user.id,
            endpoint="/agents/invoke",
            method="POST",
            channel="api",
            status_code=200,
            response_time_ms=200,
            prompt_tokens=100,
            completion_tokens=100,
            total_tokens=200,
            cost=Decimal("0.20"),
            created_at=date,
        )
        db_session.add(record)
    
    await db_session.commit()
    
    response = await client.get("/analytics/forecast/monthly", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3  # requests, tokens, cost
    assert all("metric" in item for item in data)
    assert all("forecast_7d" in item for item in data)
    assert all("forecast_30d" in item for item in data)
    assert all("confidence" in item for item in data)


@pytest.mark.asyncio
async def test_get_feature_usage(client: AsyncClient, auth_header: dict, user: User, db_session: AsyncSession):
    """Test feature usage breakdown by endpoint."""
    today = datetime.utcnow()
    
    # Add usage for different endpoints
    endpoints = ["/agents/invoke", "/billing/account", "/web/echo"]
    for endpoint in endpoints:
        for i in range(5):
            record = UsageRecord(
                user_id=user.id,
                endpoint=endpoint,
                method="GET" if endpoint == "/billing/account" else "POST",
                channel="api",
                status_code=200,
                response_time_ms=100,
                prompt_tokens=50,
                completion_tokens=50,
                total_tokens=100,
                cost=Decimal("0.10"),
                created_at=today - timedelta(days=i),
            )
            db_session.add(record)
    
    await db_session.commit()
    
    response = await client.get("/analytics/features?days=30", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3  # 3 different endpoints
    assert all("endpoint" in item for item in data)
    assert all("usage_count" in item for item in data)
    assert all("percentage" in item for item in data)


@pytest.mark.asyncio
async def test_get_cost_breakdown(client: AsyncClient, auth_header: dict, user: User, db_session: AsyncSession):
    """Test cost breakdown by endpoint."""
    today = datetime.utcnow()
    
    # Add usage with different costs
    costs = [
        ("/agents/invoke", Decimal("0.50")),
        ("/billing/account", Decimal("0.10")),
        ("/web/echo", Decimal("0.05")),
    ]
    
    for endpoint, cost in costs:
        for i in range(3):
            record = UsageRecord(
                user_id=user.id,
                endpoint=endpoint,
                method="POST",
                channel="api",
                status_code=200,
                response_time_ms=100,
                prompt_tokens=100,
                completion_tokens=100,
                total_tokens=200,
                cost=cost,
                created_at=today - timedelta(days=i),
            )
            db_session.add(record)
    
    await db_session.commit()
    
    response = await client.get("/analytics/costs?days=30", headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3  # 3 endpoints
    assert all("endpoint" in item for item in data)
    assert all("total_cost" in item for item in data)
    assert all("percentage" in item for item in data)
    assert all("requests" in item for item in data)
    # Verify percentages sum to 100
    total_percentage = sum(item["percentage"] for item in data)
    assert 99 < total_percentage < 101  # Allow small rounding error
