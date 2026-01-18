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
from app.core.paddle import paddle_client, PaddleClient
from app.models.user import User
from app.models.organization import Organization
from app.models.billing import BillingAccount, SubscriptionPlan, SubscriptionStatus, PlanType
from app.models.usage import UsageRecord
from app.i18n.loader import i18n

from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="app/templates")


router = APIRouter(prefix="/billing", tags=["Billing"])


def get_paddle_client() -> PaddleClient:
	"""Dependency wrapper to allow overriding Paddle client in tests."""
	return paddle_client


def _as_dict(obj: object) -> dict:
	"""Normalize Paddle SDK objects or fakes to a dict for uniform access."""
	if obj is None:
		return {}
	if isinstance(obj, dict):
		return obj
	if hasattr(obj, "dict"):
		try:
			return obj.dict()
		except Exception:
			pass
	if hasattr(obj, "__dict__"):
		return dict(obj.__dict__)
	return {}


@router.get("/upgrade", response_class=HTMLResponse)
async def upgrade_page(request: Request):
	"""Render upgrade page."""
	lang = request.query_params.get("lang", "en")
	t = lambda key, **params: i18n.t(key, locale=lang, **params)
	return templates.TemplateResponse(
		"upgrade.html",
		{
			"request": request,
			"language": lang,
			"t": t,
			"paddle_client_token": settings.paddle_client_token or "",
			"paddle_environment": settings.paddle_environment or "sandbox",
		}
	)


@router.get("/success", response_class=HTMLResponse)
async def payment_success_page(request: Request):
	"""
	Payment success page - shown after Paddle checkout completes.
	Paddle redirects here with ?_ptxn=<transaction_id> parameter.
	"""
	lang = request.query_params.get("lang", "en")
	transaction_id = request.query_params.get("_ptxn", "")
	t = lambda key, **params: i18n.t(key, locale=lang, **params)
	return templates.TemplateResponse(
		"payment_success.html",
		{
			"request": request,
			"language": lang,
			"t": t,
			"transaction_id": transaction_id,
		}
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


class ActivityEventResponse(BaseModel):
	"""Unified activity event for dashboard display."""
	id: str  # Unique identifier (could be "usage_123" or "billing_456")
	type: str  # "usage", "subscription", "payment", "cancellation"
	title: str  # Human-readable title
	description: str  # Detailed description
	endpoint: Optional[str] = None  # For usage events
	method: Optional[str] = None  # For usage events
	status_code: Optional[int] = None  # For usage events
	response_time_ms: Optional[int] = None  # For usage events  
	total_tokens: Optional[int] = None  # For usage events
	cost: Optional[Decimal] = None  # For usage/payment events
	error_message: Optional[str] = None  # For error events
	created_at: datetime  # When event occurred


class BillingAccountResponse(BaseModel):
	organization_id: int
	plan_id: Optional[int]
	plan_name: Optional[str]
	plan_type: Optional[str]  # "subscription" or "one_time"
	plan_type_display: Optional[str]  # Локализованное отображение типа плана
	plan_interval: Optional[str]  # "monthly", "yearly" etc
	status: str
	status_display: str  # Понятное описание статуса
	balance: Decimal
	total_spent: Decimal
	
	# Бесплатные запросы (если есть)
	free_requests_limit: int
	free_requests_used: int
	free_requests_remaining: int  # Вычисляемое поле
	free_trial_days: int
	trial_started_at: Optional[str]
	trial_end_date: Optional[str]
	
	# Для SUBSCRIPTION планов
	subscription_start_date: Optional[str]
	subscription_end_date: Optional[str]
	max_requests_per_period: Optional[int] = None  # Лимит за период
	requests_used_current_period: Optional[int] = None  # Использовано за период
	requests_remaining_current_period: Optional[int] = None  # Осталось за период
	period_started_at: Optional[str] = None  # Когда начался текущий период
	
	# Для ONE_TIME планов (пакеты кредитов)
	credits_purchased: Optional[int] = None  # Всего куплено кредитов
	credits_used: Optional[int] = None  # Использовано кредитов
	credits_remaining: Optional[int] = None  # Осталось кредитов
	
	# Детали платежей
	checkout_url: Optional[str] = None
	transaction_id: Optional[str] = None
	paddle_subscription_id: Optional[str] = None
	next_billing_date: Optional[str] = None
	paused_at: Optional[str] = None
	cancelled_at: Optional[str] = None
	
	# Рекомендации для UI
	can_use_service: bool = True  # Может ли использовать сервис
	should_upgrade: bool = False  # Нужно ли апгрейдиться
	upgrade_reason: Optional[str] = None  # Причина апгрейда


class UsageSummaryResponse(BaseModel):
	from_date: datetime
	to_date: datetime
	requests: int
	tokens: int
	cost: Decimal


async def _get_billing_account_response(
	current_user: User,
	db: AsyncSession,
) -> BillingAccountResponse:
	"""Helper function to get billing account response (without FastAPI dependencies)."""
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

	# Определяем тип плана и статус для понятного отображения
	plan_type_val = plan.plan_type.value if plan else None
	is_one_time = plan_type_val == "one_time"
	is_subscription = plan_type_val == "subscription"
	
	# Человекопонятное название типа плана
	plan_type_display = None
	if is_subscription:
		plan_type_display = "Подписка"
	elif is_one_time:
		plan_type_display = "Пакет запросов"
	
	# Человекопонятный статус
	status_map = {
		"active": "Активна",
		"trialing": "Пробный период",
		"paused": "Приостановлена",
		"canceled": "Отменена",
		"cancelled": "Отменена",
		"past_due": "Просрочен платеж",
		"expired": "Истекла",
	}
	status_display = status_map.get(ba.subscription_status.value, ba.subscription_status.value)
	
	# Бесплатные запросы
	free_limit = plan.free_requests_limit if plan else 0
	free_used = ba.free_requests_used
	free_remaining = max(0, free_limit - free_used)
	
	# Для SUBSCRIPTION: лимиты за период
	max_per_period = None
	used_period = None
	remaining_period = None
	if is_subscription and plan:
		max_per_period = plan.max_requests_per_interval
		used_period = ba.requests_used_current_period
		remaining_period = max(0, max_per_period - used_period) if max_per_period > 0 else 0
	
	# Для ONE_TIME: кредиты
	credits_purchased = None
	credits_used = None
	credits_remaining = None
	if is_one_time:
		credits_purchased = ba.one_time_purchases_count
		credits_used = ba.one_time_requests_used
		credits_remaining = max(0, credits_purchased - credits_used)
	
	# Определяем можно ли использовать сервис
	can_use = False
	should_upgrade = False
	upgrade_reason = None
	
	if ba.subscription_status in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]:
		if is_one_time:
			# Для ONE_TIME проверяем наличие кредитов
			if credits_remaining and credits_remaining > 0:
				can_use = True
			else:
				should_upgrade = True
				upgrade_reason = "Кредиты исчерпаны. Купите новый пакет запросов."
		elif is_subscription:
			# Для SUBSCRIPTION проверяем лимиты
			if free_remaining > 0:
				can_use = True
			elif remaining_period and remaining_period > 0:
				can_use = True
			else:
				should_upgrade = True
				upgrade_reason = f"Лимит запросов исчерпан. Ждите начала нового периода или перейдите на более высокий тариф."
			if free_remaining <= 0 and (not remaining_period or remaining_period <= 5):
				should_upgrade = True
				upgrade_reason = "Запросы заканчиваются. Рекомендуем обновить план."
		else:
			# Неизвестный тип - даем доступ
			can_use = True
	else:
		should_upgrade = True
		upgrade_reason = f"Статус подписки: {status_display}. Активируйте подписку для продолжения."
	
	return BillingAccountResponse(
		organization_id=org.id,
		plan_id=ba.subscription_plan_id,
		plan_name=plan.name if plan else "Без плана",
		plan_type=plan_type_val,
		plan_type_display=plan_type_display,
		plan_interval=plan.interval.value if plan else None,
		status=ba.subscription_status.value,
		status_display=status_display,
		balance=ba.balance,
		total_spent=ba.total_spent,
		
		# Бесплатные запросы
		free_requests_limit=free_limit,
		free_requests_used=free_used,
		free_requests_remaining=free_remaining,
		free_trial_days=plan.free_trial_days if plan else 0,
		trial_started_at=ba.trial_started_at.isoformat() if ba.trial_started_at else None,
		trial_end_date=ba.trial_end_date.isoformat() if ba.trial_end_date else None,
		
		# SUBSCRIPTION поля
		subscription_start_date=ba.subscription_start_date.isoformat() if ba.subscription_start_date else None,
		subscription_end_date=ba.subscription_end_date.isoformat() if ba.subscription_end_date else None,
		max_requests_per_period=max_per_period,
		requests_used_current_period=used_period,
		requests_remaining_current_period=remaining_period,
		period_started_at=ba.period_started_at.isoformat() if ba.period_started_at else None,
		
		# ONE_TIME поля
		credits_purchased=credits_purchased,
		credits_used=credits_used,
		credits_remaining=credits_remaining,
		
		# Платежи
		paddle_subscription_id=ba.paddle_subscription_id,
		next_billing_date=ba.next_billing_date.isoformat() if ba.next_billing_date else None,
		paused_at=ba.paused_at.isoformat() if ba.paused_at else None,
		cancelled_at=ba.cancelled_at.isoformat() if ba.cancelled_at else None,
		
		# Рекомендации
		can_use_service=can_use,
		should_upgrade=should_upgrade,
		upgrade_reason=upgrade_reason,
	)


@router.get("/account", response_model=BillingAccountResponse)
async def get_billing_account(
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db),
):
	"""Get billing account (FastAPI endpoint)."""
	return await _get_billing_account_response(current_user, db)


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
	paddle: PaddleClient = Depends(get_paddle_client),
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

	# Check if user is not trying to subscribe to same plan
	if (ba.subscription_plan_id == plan.id 
		and ba.subscription_status in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]):
		raise HTTPException(
			status_code=400, 
			detail="You are already subscribed to this plan."
		)

	# For SUBSCRIPTION plans: prevent creating new subscription if active one exists
	from app.models.billing import SubscriptionStatus, PlanType
	if plan.plan_type == PlanType.SUBSCRIPTION:
		if ba.paddle_subscription_id and ba.subscription_status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
			raise HTTPException(
				status_code=400, 
				detail="Active subscription already exists. Cancel current subscription before subscribing to a new plan."
			)

	# For ONE_TIME plans: ALLOW purchase while subscription is active (комбинированная модель)
	# Кредиты будут использоваться приоритетно перед лимитами подписки

	# STAGE 3: Additional validations (after Stage 1 critical checks)
	# Check if plan has agents (skip for test plans)
	if len(plan.agents) == 0 and not ("Test" in plan.name or "Credits" in plan.name):
		raise HTTPException(
			status_code=400, 
			detail="Plan has no agents assigned. Contact administrator."
		)

	# Check if plan has valid Paddle configuration (when billing enabled)
	if settings.paddle_billing_enabled and not plan.paddle_price_id:
		raise HTTPException(
			status_code=400, 
			detail="Plan is missing payment configuration. Contact administrator."
		)

	checkout_url: Optional[str] = None
	transaction_id: Optional[str] = None

	if settings.paddle_billing_enabled:
		# Create Paddle customer if missing
		if not ba.paddle_customer_id:
			customer = _as_dict(
				await paddle.create_customer(
					email=current_user.email,
					name=current_user.full_name or current_user.email,
				)
			)
			ba.paddle_customer_id = customer.get("id")
			if not ba.paddle_customer_id:
				raise HTTPException(status_code=502, detail="Failed to create Paddle customer")

		# Create Paddle transaction based on plan type
		if plan.plan_type == PlanType.SUBSCRIPTION:
			# For recurring subscriptions
			transaction = _as_dict(
				await paddle.create_subscription(
					customer_id=ba.paddle_customer_id,
					price_id=plan.paddle_price_id,
				)
			)
		else:  # PlanType.ONE_TIME
			# For one-time purchases
			transaction = _as_dict(
			await paddle.create_transaction_checkout(
		
		# Capture next billing date if provided
		next_bill = None
		for key in ("next_billed_at", "next_billing_date"):
			next_bill = transaction.get(key)
			if next_bill:
				break
		if next_bill:
			try:
				ba.next_billing_date = datetime.fromisoformat(str(next_bill).replace("Z", "+00:00"))
			except ValueError:
				pass

		# Get checkout URL from transaction.checkout.url
		checkout = transaction.get("checkout")
		if isinstance(checkout, dict) and checkout.get("url"):
			checkout_url = checkout.get("url")
		else:
			# Fallback: look for other possible keys
			for key in ("url", "checkout_url", "hosted_page_url"):
				if transaction.get(key):
					checkout_url = transaction.get(key)
					break
		
		# Append success_url parameter to redirect after payment
		if checkout_url:
			separator = "&" if "?" in checkout_url else "?"
			success_redirect = f"{settings.api_base_url}/billing/success"
			checkout_url = f"{checkout_url}{separator}success_url={success_redirect}"

	# If Paddle is disabled, activate the plan immediately (manual/local mode)
	if not settings.paddle_billing_enabled:
		now = datetime.utcnow()
		ba.subscription_plan_id = plan.id
		ba.subscription_status = SubscriptionStatus.ACTIVE
		ba.subscription_start_date = now
		ba.period_started_at = now
		# For one-time plans, grant the purchased quota immediately
		if plan.plan_type == PlanType.ONE_TIME and plan.one_time_limit:
			ba.one_time_purchases_count += plan.one_time_limit

	# DO NOT update subscription state here when Paddle is enabled - it will be updated by webhook after payment
	await db.commit()
	await db.refresh(ba)

	account = await _get_billing_account_response(current_user, db)
	return account.model_copy(update={"checkout_url": checkout_url, "transaction_id": transaction_id})


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


@router.get("/activity", response_model=list[ActivityEventResponse])
async def get_activity_events(
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db),
	limit: int = Query(10, ge=1, le=100),
	days: int = Query(30, ge=1, le=90),
):
	"""Get comprehensive user activity including usage and billing events."""
	start_date = datetime.utcnow() - timedelta(days=days)
	events = []
	
	# 1. Get significant usage records (agent invocations, telegram usage)
	significant_endpoints = [
		'/agents/%/invoke',
		'/channels/telegram/webhook',
	]
	
	from sqlalchemy import or_
	endpoint_filters = []
	for pattern in significant_endpoints:
		if '%' in pattern:
			endpoint_filters.append(UsageRecord.endpoint.like(pattern))
		else:
			endpoint_filters.append(UsageRecord.endpoint == pattern)
	
	usage_result = await db.execute(
		select(UsageRecord)
		.where(
			(UsageRecord.user_id == current_user.id)
			& (UsageRecord.created_at >= start_date)
			& or_(*endpoint_filters)
		)
		.order_by(desc(UsageRecord.created_at))
		.limit(limit // 2)  # Reserve half for billing events
	)
	
	for record in usage_result.scalars().all():
		if '/agents/' in record.endpoint and '/invoke' in record.endpoint:
			title = "🤖 AI Agent Query"
			description = f"Used AI agent"
			if record.total_tokens > 0:
				description += f" • {record.total_tokens:,} tokens"
			if record.cost > 0:
				description += f" • ${record.cost}"
		elif '/telegram/' in record.endpoint:
			title = "📱 Telegram Query"  
			description = "Used agent via Telegram"
			if record.total_tokens > 0:
				description += f" • {record.total_tokens:,} tokens"
		else:
			title = "📊 Activity"
			description = record.endpoint
			
		events.append(ActivityEventResponse(
			id=f"usage_{record.id}",
			type="usage",
			title=title,
			description=description,
			endpoint=record.endpoint,
			method=record.method,
			status_code=record.status_code,
			response_time_ms=record.response_time_ms,
			total_tokens=record.total_tokens if record.total_tokens > 0 else None,
			cost=record.cost if record.cost > 0 else None,
			error_message=record.error_message,
			created_at=record.created_at
		))
	
	# 2. Get billing account to check for billing events
	if current_user.organization_id:
		billing_result = await db.execute(
			select(BillingAccount)
			.where(BillingAccount.organization_id == current_user.organization_id)
		)
		billing_account = billing_result.scalar_one_or_none()
		
		if billing_account:
			# Add subscription started event
			if billing_account.subscription_start_date and billing_account.subscription_start_date >= start_date:
				plan_result = await db.execute(
					select(SubscriptionPlan).where(SubscriptionPlan.id == billing_account.subscription_plan_id)
				)
				plan = plan_result.scalar_one_or_none()
				plan_name = plan.name if plan else "Unknown Plan"
				
				events.append(ActivityEventResponse(
					id=f"subscription_{billing_account.id}",
					type="subscription",
					title="💳 New Subscription",
					description=f"Subscribed to {plan_name}",
					cost=plan.price if plan else None,
					created_at=billing_account.subscription_start_date
				))
			
			# Add cancellation event  
			if billing_account.cancelled_at and billing_account.cancelled_at >= start_date:
				events.append(ActivityEventResponse(
					id=f"cancellation_{billing_account.id}",
					type="cancellation", 
					title="❌ Subscription Cancelled",
					description="Cancelled subscription",
					created_at=billing_account.cancelled_at
				))
	
	# 3. Sort all events by date and limit
	events.sort(key=lambda x: x.created_at, reverse=True)
	return events[:limit]


@router.get("/usage-records", response_model=list[UsageRecordResponse])
async def get_usage_records(
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db),
	limit: int = Query(10, ge=1, le=100),
	days: int = Query(30, ge=1, le=90),
):
	"""Get user's significant usage records (activity log) - only important events."""
	start_date = datetime.utcnow() - timedelta(days=days)
	
	# Only show significant events: agent invocations and billing events
	significant_endpoints = [
		'/agents/%/invoke',  # Agent usage
		'/channels/telegram/webhook',  # Telegram usage
		'/billing/subscribe',  # Subscription events
		'/billing/cancel',  # Cancellation events
	]
	
	# Build query with endpoint filters
	from sqlalchemy import or_
	endpoint_filters = []
	for pattern in significant_endpoints:
		if '%' in pattern:
			endpoint_filters.append(UsageRecord.endpoint.like(pattern))
		else:
			endpoint_filters.append(UsageRecord.endpoint == pattern)
	
	result = await db.execute(
		select(UsageRecord)
		.where(
			(UsageRecord.user_id == current_user.id)
			& (UsageRecord.created_at >= start_date)
			& or_(*endpoint_filters)  # Only significant endpoints
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
	from app.models.billing import PlanType
	
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
	
	# Calculate remaining based on plan type
	if plan.plan_type == PlanType.ONE_TIME:
		# For one-time purchases: show total purchased and remaining
		one_time_remaining = max(0, billing_account.one_time_purchases_count - billing_account.one_time_requests_used)
		return {
			"plan_name": plan.name,
			"plan_type": plan.plan_type.value,
			"subscription_status": billing_account.subscription_status.value,
			"one_time_limit": plan.one_time_limit,
			"one_time_total_purchased": billing_account.one_time_purchases_count,
			"one_time_used": billing_account.one_time_requests_used,
			"one_time_remaining": one_time_remaining,
		}
	else:
		# For subscriptions: show time-based limits
		free_remaining = max(0, plan.free_requests_limit - billing_account.free_requests_used)
		paid_remaining = max(0, plan.max_requests_per_interval - billing_account.requests_used_current_period)
		
		return {
			"plan_name": plan.name,
			"plan_type": plan.plan_type.value,
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
			"plan_type": plan.plan_type.value,
			"interval": plan.interval.value,
			"price": float(plan.price),
			"currency": plan.currency,
			"max_requests_per_interval": plan.max_requests_per_interval,
			"max_tokens_per_request": plan.max_tokens_per_request,
			"free_requests_limit": plan.free_requests_limit,
			"free_trial_days": plan.free_trial_days,
			"one_time_limit": plan.one_time_limit,
			"has_api_access": plan.has_api_access,
			"has_priority_support": plan.has_priority_support,
			"has_advanced_analytics": plan.has_advanced_analytics,
		}
		for plan in plans
	]

@router.get("/plans/available")
async def get_available_plans_for_user(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get plans available for purchase by current user based on their subscription state."""
    
    # Get user's billing account
    ba = await db.execute(
        select(BillingAccount).where(BillingAccount.organization_id == current_user.organization_id)
    )
    billing_account = ba.scalar_one_or_none()
    
    has_active_subscription = (
        billing_account 
        and billing_account.subscription_plan_id 
        and billing_account.subscription_status in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
    )
    
    query = select(SubscriptionPlan).order_by(SubscriptionPlan.price)
    
    if has_active_subscription:
        # Only show SUBSCRIPTION plans for upgrade/downgrade
        query = query.where(SubscriptionPlan.plan_type == PlanType.SUBSCRIPTION)
        # Exclude current plan
        query = query.where(SubscriptionPlan.id != billing_account.subscription_plan_id)
    else:
        # Show all valid plans
        pass
    
    result = await db.execute(query)
    plans = result.scalars().all()
    
    # Filter only valid plans
    valid_plans = []
    for plan in plans:
        # Check if plan has agents
        if len(plan.agents) == 0:
            continue
        # Check if has paddle_price_id (if billing enabled)
        if settings.paddle_billing_enabled and not plan.paddle_price_id:
            continue
        valid_plans.append(plan)
    
    return [
        {
            "id": plan.id,
            "name": plan.name,
            "plan_type": plan.plan_type.value,
            "interval": plan.interval.value,
            "price": float(plan.price),
            "currency": plan.currency,
            "max_requests_per_interval": plan.max_requests_per_interval,
            "max_tokens_per_request": plan.max_tokens_per_request,
            "free_requests_limit": plan.free_requests_limit,
            "free_trial_days": plan.free_trial_days,
            "one_time_limit": plan.one_time_limit,
            "agent_count": len(plan.agents),
            "has_api_access": plan.has_api_access,
            "has_priority_support": plan.has_priority_support,
            "has_advanced_analytics": plan.has_advanced_analytics,
        }
        for plan in valid_plans
    ]