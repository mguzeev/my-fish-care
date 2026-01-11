"""Billing API: account info, usage, subscribe/cancel."""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.models.billing import BillingAccount, SubscriptionPlan, SubscriptionStatus
from app.models.usage import UsageRecord


router = APIRouter(prefix="/billing", tags=["Billing"])


class SubscribeRequest(BaseModel):
	plan_id: int


class BillingAccountResponse(BaseModel):
	organization_id: int
	plan_id: Optional[int]
	plan_name: Optional[str]
	status: str
	balance: Decimal
	total_spent: Decimal


class UsageSummaryResponse(BaseModel):
	from_date: datetime
	to_date: datetime
	requests: int
	tokens: int
	cost: Decimal


@router.get("/account", response_model=BillingAccountResponse)
async def get_billing_account(
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db),
):
	if not current_user.organization_id:
		raise HTTPException(status_code=404, detail="User has no organization")

	org_stmt = select(Organization).where(Organization.id == current_user.organization_id)
	org = (await db.execute(org_stmt)).scalar_one_or_none()
	if not org:
		raise HTTPException(status_code=404, detail="Organization not found")

	ba_stmt = select(BillingAccount).where(BillingAccount.organization_id == org.id)
	ba = (await db.execute(ba_stmt)).scalar_one_or_none()
	if not ba:
		# Auto-provision an empty billing account
		ba = BillingAccount(organization_id=org.id)
		db.add(ba)
		await db.commit()
		await db.refresh(ba)

	plan = None
	if ba.subscription_plan_id:
		plan = (await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == ba.subscription_plan_id))).scalar_one_or_none()

	return BillingAccountResponse(
		organization_id=org.id,
		plan_id=ba.subscription_plan_id,
		plan_name=plan.name if plan else None,
		status=ba.subscription_status.value,
		balance=ba.balance,
		total_spent=ba.total_spent,
	)


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage_summary(
	days: int = 30,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db),
):
	end = datetime.utcnow()
	start = end - timedelta(days=max(1, min(days, 90)))
	q = (
		select(
			func.count(UsageRecord.id),
			func.coalesce(func.sum(UsageRecord.total_tokens), 0),
			func.coalesce(func.sum(UsageRecord.cost), Decimal("0.0")),
		)
		.where(
			(UsageRecord.user_id == current_user.id)
			& (UsageRecord.created_at >= start)
			& (UsageRecord.created_at <= end)
		)
	)
	res = (await db.execute(q)).one()
	requests = int(res[0])
	tokens = int(res[1]) if res[1] is not None else 0
	cost = Decimal(res[2]) if res[2] is not None else Decimal("0.0")
	return UsageSummaryResponse(from_date=start, to_date=end, requests=requests, tokens=tokens, cost=cost)


@router.post("/subscribe", response_model=BillingAccountResponse)
async def subscribe(
	payload: SubscribeRequest,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db),
):
	if not current_user.organization_id:
		raise HTTPException(status_code=400, detail="Organization required")

	plan = (await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == payload.plan_id))).scalar_one_or_none()
	if not plan:
		raise HTTPException(status_code=404, detail="Plan not found")

	ba = (
		await db.execute(
			select(BillingAccount).where(BillingAccount.organization_id == current_user.organization_id)
		)
	).scalar_one_or_none()
	if not ba:
		ba = BillingAccount(organization_id=current_user.organization_id)
		db.add(ba)

	ba.subscription_plan_id = plan.id
	ba.subscription_status = SubscriptionStatus.ACTIVE
	ba.subscription_start_date = datetime.utcnow()
	await db.commit()
	await db.refresh(ba)

	return await get_billing_account(current_user, db)


@router.post("/cancel", response_model=BillingAccountResponse)
async def cancel_subscription(
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db),
):
	ba = (
		await db.execute(
			select(BillingAccount).where(BillingAccount.organization_id == current_user.organization_id)
		)
	).scalar_one_or_none()
	if not ba:
		raise HTTPException(status_code=404, detail="Billing account not found")

	ba.subscription_status = SubscriptionStatus.CANCELED
	ba.subscription_end_date = datetime.utcnow()
	await db.commit()
	await db.refresh(ba)

	return await get_billing_account(current_user, db)

