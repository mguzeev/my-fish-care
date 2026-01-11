"""Advanced analytics engine for usage patterns and forecasting."""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.models.usage import UsageRecord


router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ============================================================================
# Analytics Schemas
# ============================================================================

class UsagePoint(BaseModel):
    date: str
    requests: int
    tokens: int
    cost: Decimal


class TrendAnalysis(BaseModel):
    metric: str
    current_value: float
    previous_value: float
    change_percent: float
    trend: str  # "up", "down", "stable"


class UsageTrend(BaseModel):
    period: str
    data: list[UsagePoint]
    total_requests: int
    total_tokens: int
    total_cost: Decimal
    avg_daily_requests: float
    avg_daily_cost: Decimal


class Forecast(BaseModel):
    metric: str
    current: float
    forecast_7d: float
    forecast_30d: float
    confidence: float  # 0.0-1.0


# ============================================================================
# Trend Analysis Endpoints
# ============================================================================

@router.get("/trends/usage", response_model=UsageTrend)
async def get_usage_trends(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=90),
):
    """Get usage trends for the user over the last N days."""
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=days)
    
    # Get daily usage records
    result = await db.execute(
        select(
            func.date(UsageRecord.created_at).label("date"),
            func.count(UsageRecord.id).label("requests"),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(UsageRecord.cost), Decimal("0.0")).label("cost"),
        )
        .where(
            (UsageRecord.user_id == current_user.id)
            & (func.date(UsageRecord.created_at) >= start_date)
        )
        .group_by(func.date(UsageRecord.created_at))
        .order_by(func.date(UsageRecord.created_at))
    )
    
    rows = result.all()
    data = [
        UsagePoint(
            date=str(row[0]),
            requests=int(row[1]),
            tokens=int(row[2] or 0),
            cost=row[3] or Decimal("0.0"),
        )
        for row in rows
    ]
    
    total_requests = sum(p.requests for p in data)
    total_tokens = sum(p.tokens for p in data)
    total_cost = sum(p.cost for p in data)
    avg_daily_requests = total_requests / max(len(data), 1)
    avg_daily_cost = total_cost / max(len(data), 1)
    
    return UsageTrend(
        period=f"{days}d",
        data=data,
        total_requests=total_requests,
        total_tokens=total_tokens,
        total_cost=total_cost,
        avg_daily_requests=avg_daily_requests,
        avg_daily_cost=avg_daily_cost,
    )


@router.get("/trends/compare", response_model=list[TrendAnalysis])
async def get_trend_comparison(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare current week trends with previous week."""
    today = datetime.utcnow().date()
    
    # Current week (last 7 days)
    current_start = today - timedelta(days=7)
    current_result = await db.execute(
        select(
            func.count(UsageRecord.id),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
            func.coalesce(func.sum(UsageRecord.cost), Decimal("0.0")),
        ).where(
            (UsageRecord.user_id == current_user.id)
            & (func.date(UsageRecord.created_at) >= current_start)
        )
    )
    current_data = current_result.one()
    current_requests = int(current_data[0])
    current_tokens = int(current_data[1] or 0)
    current_cost = float(current_data[2] or Decimal("0.0"))
    
    # Previous week
    prev_start = today - timedelta(days=14)
    prev_end = today - timedelta(days=7)
    prev_result = await db.execute(
        select(
            func.count(UsageRecord.id),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
            func.coalesce(func.sum(UsageRecord.cost), Decimal("0.0")),
        ).where(
            (UsageRecord.user_id == current_user.id)
            & (func.date(UsageRecord.created_at) >= prev_start)
            & (func.date(UsageRecord.created_at) < prev_end)
        )
    )
    prev_data = prev_result.one()
    prev_requests = int(prev_data[0])
    prev_tokens = int(prev_data[1] or 0)
    prev_cost = float(prev_data[2] or Decimal("0.0"))
    
    # Calculate trends
    trends = []
    
    # Requests trend
    req_change = ((current_requests - prev_requests) / max(prev_requests, 1)) * 100
    trends.append(
        TrendAnalysis(
            metric="requests",
            current_value=float(current_requests),
            previous_value=float(prev_requests),
            change_percent=req_change,
            trend="up" if req_change > 5 else "down" if req_change < -5 else "stable",
        )
    )
    
    # Tokens trend
    token_change = ((current_tokens - prev_tokens) / max(prev_tokens, 1)) * 100
    trends.append(
        TrendAnalysis(
            metric="tokens",
            current_value=float(current_tokens),
            previous_value=float(prev_tokens),
            change_percent=token_change,
            trend="up" if token_change > 5 else "down" if token_change < -5 else "stable",
        )
    )
    
    # Cost trend
    cost_change = ((current_cost - prev_cost) / max(prev_cost, 0.01)) * 100
    trends.append(
        TrendAnalysis(
            metric="cost",
            current_value=current_cost,
            previous_value=prev_cost,
            change_percent=cost_change,
            trend="up" if cost_change > 5 else "down" if cost_change < -5 else "stable",
        )
    )
    
    return trends


# ============================================================================
# Forecasting Endpoints
# ============================================================================

@router.get("/forecast/monthly", response_model=list[Forecast])
async def forecast_monthly_usage(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Forecast monthly usage and cost for the next 30 days."""
    today = datetime.utcnow().date()
    
    # Get last 30 days of data
    start_date = today - timedelta(days=30)
    result = await db.execute(
        select(
            func.count(UsageRecord.id).label("requests"),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(UsageRecord.cost), Decimal("0.0")).label("cost"),
        ).where(
            (UsageRecord.user_id == current_user.id)
            & (func.date(UsageRecord.created_at) >= start_date)
        )
    )
    
    data = result.one()
    current_requests = int(data[0])
    current_tokens = int(data[1] or 0)
    current_cost = float(data[2] or Decimal("0.0"))
    
    # Simple linear forecast (7-day and 30-day)
    daily_requests = current_requests / 30
    daily_tokens = current_tokens / 30
    daily_cost = current_cost / 30
    
    forecasts = [
        Forecast(
            metric="requests",
            current=float(current_requests),
            forecast_7d=daily_requests * 7,
            forecast_30d=daily_requests * 30,
            confidence=0.75,
        ),
        Forecast(
            metric="tokens",
            current=float(current_tokens),
            forecast_7d=daily_tokens * 7,
            forecast_30d=daily_tokens * 30,
            confidence=0.75,
        ),
        Forecast(
            metric="cost",
            current=current_cost,
            forecast_7d=daily_cost * 7,
            forecast_30d=daily_cost * 30,
            confidence=0.75,
        ),
    ]
    
    return forecasts


# ============================================================================
# Feature Usage Analytics
# ============================================================================

class FeatureUsage(BaseModel):
    endpoint: str
    usage_count: int
    percentage: float


@router.get("/features", response_model=list[FeatureUsage])
async def get_feature_usage(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=90),
):
    """Get feature usage breakdown (by endpoint)."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Total requests
    total_result = await db.execute(
        select(func.count(UsageRecord.id)).where(
            (UsageRecord.user_id == current_user.id)
            & (UsageRecord.created_at >= start_date)
        )
    )
    total_requests = total_result.scalar() or 1
    
    # Per-endpoint breakdown
    result = await db.execute(
        select(
            UsageRecord.endpoint,
            func.count(UsageRecord.id).label("count"),
        )
        .where(
            (UsageRecord.user_id == current_user.id)
            & (UsageRecord.created_at >= start_date)
        )
        .group_by(UsageRecord.endpoint)
        .order_by(func.count(UsageRecord.id).desc())
    )
    
    features = []
    for row in result.all():
        endpoint = row[0]
        count = int(row[1])
        percentage = (count / total_requests) * 100
        features.append(
            FeatureUsage(endpoint=endpoint, usage_count=count, percentage=percentage)
        )
    
    return features


# ============================================================================
# Cost Breakdown
# ============================================================================

class CostBreakdown(BaseModel):
    endpoint: str
    total_cost: Decimal
    percentage: float
    requests: int


@router.get("/costs", response_model=list[CostBreakdown])
async def get_cost_breakdown(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=90),
):
    """Get cost breakdown by endpoint."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Total cost
    total_result = await db.execute(
        select(func.coalesce(func.sum(UsageRecord.cost), Decimal("0.0"))).where(
            (UsageRecord.user_id == current_user.id)
            & (UsageRecord.created_at >= start_date)
        )
    )
    total_cost = total_result.scalar() or Decimal("0.0")
    if total_cost == 0:
        total_cost = Decimal("0.01")  # Avoid division by zero
    
    # Per-endpoint cost breakdown
    result = await db.execute(
        select(
            UsageRecord.endpoint,
            func.coalesce(func.sum(UsageRecord.cost), Decimal("0.0")),
            func.count(UsageRecord.id),
        )
        .where(
            (UsageRecord.user_id == current_user.id)
            & (UsageRecord.created_at >= start_date)
        )
        .group_by(UsageRecord.endpoint)
        .order_by(func.sum(UsageRecord.cost).desc())
    )
    
    costs = []
    for row in result.all():
        endpoint = row[0]
        cost = row[1]
        requests = int(row[2])
        percentage = (cost / total_cost) * 100
        costs.append(
            CostBreakdown(
                endpoint=endpoint, total_cost=cost, percentage=percentage, requests=requests
            )
        )
    
    return costs
