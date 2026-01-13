"""Billing API: account info, usage, subscribe/cancel."""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.core.config import settings
from app.core.database import get_db
from app.core.paddle import paddle_client
from app.models.user import User
from app.models.organization import Organization
from app.models.billing import BillingAccount, SubscriptionPlan, SubscriptionStatus
from app.models.usage import UsageRecord
from app.i18n.loader import i18n

from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="app/templates")


router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/upgrade", response_class=HTMLResponse)
async def upgrade_page(request: Request):
	"""Render upgrade page."""
	lang = request.query_params.get("lang", "en")
	t = lambda key, **params: i18n.t(key, locale=lang, **params)
	return templates.TemplateResponse(
		"upgrade.html",
		{"request": request, "language": lang, "t": t}
	)


class SubscribeRequest(BaseModel):
	plan_id: int


class UsageRecordResponse(BaseModel):
	id: int
	endpoint: str
	method: str
	channel: str
	model_name: Optional[str]
	prompt_tokens: int
	completion_tokens: int
	total_tokens: int
	response_time_ms: int
	status_code: int
	cost: Decimal
	error_message: Optional[str]
	created_at: datetime


class BillingAccountResponse(BaseModel):
	organization_id: int
	plan_id: Optional[int]
	plan_name: Optional[str]
	status: str
	balance: Decimal
	total_spent: Decimal
	free_requests_limit: int
	free_requests_used: int
	free_trial_days: int
	trial_started_at: Optional[str]
	checkout_url: Optional[str] = None


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
		free_requests_limit=plan.free_requests_limit if plan else 0,
		free_requests_used=ba.free_requests_used,
		free_trial_days=plan.free_trial_days if plan else 0,
		trial_started_at=ba.trial_started_at.isoformat() if ba.trial_started_at else None,
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

	checkout_url: Optional[str] = None

	if settings.paddle_billing_enabled:
		if not plan.paddle_price_id:
			raise HTTPException(status_code=400, detail="Plan is missing paddle_price_id")

		# Create Paddle customer if missing
		if not ba.paddle_customer_id:
			customer = await paddle_client.create_customer(
				email=current_user.email,
				name=current_user.full_name or current_user.email,
			)
			ba.paddle_customer_id = customer.get("id")
			if not ba.paddle_customer_id:
				raise HTTPException(status_code=502, detail="Failed to create Paddle customer")

		# Create Paddle subscription
		subscription = await paddle_client.create_subscription(
			customer_id=ba.paddle_customer_id,
			price_id=plan.paddle_price_id,
		)
		subscription_id = subscription.get("id") if isinstance(subscription, dict) else None
		if not subscription_id:
			raise HTTPException(status_code=502, detail="Failed to create Paddle subscription")

		ba.paddle_subscription_id = subscription_id
		# Capture next billing date if provided
		next_bill = None
		for key in ("next_billed_at", "next_billing_date"):
			next_bill = subscription.get(key) if isinstance(subscription, dict) else None
			if next_bill:
				break
		if next_bill:
			try:
				ba.next_billing_date = datetime.fromisoformat(str(next_bill).replace("Z", "+00:00"))
			except ValueError:
				pass

		# Some Paddle responses include hosted url; surface if present
		for key in ("url", "checkout_url", "hosted_page_url"):
			if isinstance(subscription, dict) and subscription.get(key):
				checkout_url = subscription.get(key)
				break

	# Update local subscription state
	ba.subscription_plan_id = plan.id
	ba.subscription_status = SubscriptionStatus.ACTIVE
	ba.subscription_start_date = datetime.utcnow()
	await db.commit()
	await db.refresh(ba)

	account = await get_billing_account(current_user, db)
	return account.model_copy(update={"checkout_url": checkout_url})


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


@router.get("/usage-records", response_model=list[UsageRecordResponse])
async def get_usage_records(
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db),
	limit: int = Query(10, ge=1, le=100),
	days: int = Query(30, ge=1, le=90),
):
	"""Get user's usage records (activity log)."""
	start_date = datetime.utcnow() - timedelta(days=days)
	
	result = await db.execute(
		select(UsageRecord)
		.where(
			(UsageRecord.user_id == current_user.id)
			& (UsageRecord.created_at >= start_date)
		)
		.order_by(desc(UsageRecord.created_at))
		.limit(limit)
	)
	
	records = result.scalars().all()
	return records


@router.get("/usage")
async def get_usage_info(
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Get current usage information and limits."""
	if not current_user.organization_id:
		raise HTTPException(status_code=403, detail="No organization assigned")
	
	# Get billing account and plan
	billing_result = await db.execute(
		select(BillingAccount, SubscriptionPlan)
		.join(SubscriptionPlan, BillingAccount.subscription_plan_id == SubscriptionPlan.id)
		.where(BillingAccount.organization_id == current_user.organization_id)
	)
	row = billing_result.one_or_none()
	
	if not row:
		raise HTTPException(status_code=404, detail="No billing account found")
	
	billing_account, plan = row
	
	# Calculate remaining
	free_remaining = max(0, plan.free_requests_limit - billing_account.free_requests_used)
	paid_remaining = max(0, plan.max_requests_per_interval - billing_account.requests_used_current_period)
	
	return {
		"plan_name": plan.name,
		"plan_interval": plan.interval.value,
		"subscription_status": billing_account.subscription_status.value,
		"free_requests_limit": plan.free_requests_limit,
		"free_requests_used": billing_account.free_requests_used,
		"free_remaining": free_remaining,
		"paid_requests_limit": plan.max_requests_per_interval,
		"paid_requests_used": billing_account.requests_used_current_period,
		"paid_remaining": paid_remaining,
		"period_started_at": billing_account.period_started_at.isoformat() if billing_account.period_started_at else None,
		"trial_started_at": billing_account.trial_started_at.isoformat() if billing_account.trial_started_at else None,
	}


@router.get("/plans")
async def get_available_plans(db: AsyncSession = Depends(get_db)):
	"""Get all available subscription plans."""
	result = await db.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.price))
	plans = result.scalars().all()
	
	return [
		{
			"id": plan.id,
			"name": plan.name,
			"interval": plan.interval.value,
			"price": float(plan.price),
			"currency": plan.currency,
			"max_requests_per_interval": plan.max_requests_per_interval,
			"max_tokens_per_request": plan.max_tokens_per_request,
			"free_requests_limit": plan.free_requests_limit,
			"free_trial_days": plan.free_trial_days,
			"has_api_access": plan.has_api_access,
			"has_priority_support": plan.has_priority_support,
			"has_advanced_analytics": plan.has_advanced_analytics,
		}
		for plan in plans
	]


@router.get("/upgrade", response_class=HTMLResponse)
async def upgrade_page(request: Request):
	"""Render upgrade page."""
	return templates.TemplateResponse("upgrade.html", {
		"request": request,
		"language": "en",
		"t": lambda key: key
	})
