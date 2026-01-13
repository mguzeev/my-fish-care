import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from types import SimpleNamespace

from app.main import app as fastapi_app
from app.core.config import settings
from app.billing.router import get_paddle_client
from app.models.billing import SubscriptionPlan, SubscriptionInterval, BillingAccount, SubscriptionStatus


class _FakePaddle:
    def __init__(self, subscription_response=None, transaction_response=None, customer_id="cus_123"):
        self._subscription_response = subscription_response or {}
        self._transaction_response = transaction_response or {}
        self._customer_id = customer_id

    async def create_customer(self, email: str, name: str):
        return SimpleNamespace(id=self._customer_id)

    async def create_subscription(self, customer_id: str, price_id: str, quantity: int = 1):
        return SimpleNamespace(**self._subscription_response)

    async def create_transaction_checkout(self, customer_id: str, price_id: str, quantity: int = 1):
        return SimpleNamespace(**self._transaction_response)


@pytest.mark.asyncio
async def test_subscribe_paddle_success_with_checkout_url(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_header,
    monkeypatch,
):
    monkeypatch.setattr(settings, "paddle_billing_enabled", True)

    plan = SubscriptionPlan(
        name="Pro",
        interval=SubscriptionInterval.MONTHLY,
        price=9.99,
        currency="USD",
        max_requests_per_interval=1000,
        max_tokens_per_request=2000,
        paddle_price_id="price_123",
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)

    fake = _FakePaddle(
        subscription_response={
            "id": "sub_123",
            "url": "https://checkout/sub",
            "next_billed_at": "2026-02-01T00:00:00Z",
        }
    )
    fastapi_app.dependency_overrides[get_paddle_client] = lambda: fake

    try:
        response = await client.post(
            "/billing/subscribe",
            json={"plan_id": plan.id},
            headers=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["checkout_url"] == "https://checkout/sub"

        result = await db_session.execute(
            select(BillingAccount).where(BillingAccount.subscription_plan_id == plan.id)
        )
        ba = result.scalar_one_or_none()
        assert ba is not None
        assert ba.paddle_customer_id == "cus_123"
        assert ba.paddle_subscription_id == "sub_123"
        assert ba.subscription_status == SubscriptionStatus.ACTIVE
        assert ba.next_billing_date is not None
    finally:
        fastapi_app.dependency_overrides.pop(get_paddle_client, None)


@pytest.mark.asyncio
async def test_subscribe_paddle_fallback_checkout_url(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_header,
    monkeypatch,
):
    monkeypatch.setattr(settings, "paddle_billing_enabled", True)

    plan = SubscriptionPlan(
        name="Pro",
        interval=SubscriptionInterval.MONTHLY,
        price=9.99,
        currency="USD",
        max_requests_per_interval=1000,
        max_tokens_per_request=2000,
        paddle_price_id="price_123",
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)

    fake = _FakePaddle(
        subscription_response={"id": "sub_123"},
        transaction_response={"checkout_url": "https://checkout/tx"},
    )
    fastapi_app.dependency_overrides[get_paddle_client] = lambda: fake

    try:
        response = await client.post(
            "/billing/subscribe",
            json={"plan_id": plan.id},
            headers=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["checkout_url"] == "https://checkout/tx"
    finally:
        fastapi_app.dependency_overrides.pop(get_paddle_client, None)


@pytest.mark.asyncio
async def test_subscribe_paddle_missing_price_id(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_header,
    monkeypatch,
):
    monkeypatch.setattr(settings, "paddle_billing_enabled", True)

    plan = SubscriptionPlan(
        name="Pro",
        interval=SubscriptionInterval.MONTHLY,
        price=9.99,
        currency="USD",
        max_requests_per_interval=1000,
        max_tokens_per_request=2000,
        paddle_price_id=None,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)

    response = await client.post(
        "/billing/subscribe",
        json={"plan_id": plan.id},
        headers=auth_header,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_subscribe_paddle_subscription_failure(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_header,
    monkeypatch,
):
    monkeypatch.setattr(settings, "paddle_billing_enabled", True)

    plan = SubscriptionPlan(
        name="Pro",
        interval=SubscriptionInterval.MONTHLY,
        price=9.99,
        currency="USD",
        max_requests_per_interval=1000,
        max_tokens_per_request=2000,
        paddle_price_id="price_123",
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)

    fake = _FakePaddle(subscription_response={})
    fastapi_app.dependency_overrides[get_paddle_client] = lambda: fake

    try:
        response = await client.post(
            "/billing/subscribe",
            json={"plan_id": plan.id},
            headers=auth_header,
        )
        assert response.status_code == 502
    finally:
        fastapi_app.dependency_overrides.pop(get_paddle_client, None)
