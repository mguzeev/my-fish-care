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
    def __init__(self, transaction_response=None, customer_id="cus_123"):
        self._transaction_response = transaction_response or {}
        self._customer_id = customer_id

    async def create_customer(self, email: str, name: str):
        return {"id": self._customer_id}

    async def create_subscription(self, customer_id: str, price_id: str, quantity: int = 1):
        # In Paddle Billing, create_subscription actually creates a transaction
        return self._transaction_response

    async def create_transaction_checkout(self, customer_id: str, price_id: str, quantity: int = 1):
        return self._transaction_response


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
        transaction_response={
            "id": "txn_123",
            "subscription_id": "sub_123",
            "checkout": {"url": "https://checkout/sub"},
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
        # checkout_url now includes success_url parameter
        assert "https://checkout/sub" in data["checkout_url"]
        assert "success_url=" in data["checkout_url"]

        # In Paddle mode, subscription is activated by webhook after payment; account exists but plan is not applied yet
        ba = (
            await db_session.execute(
                select(BillingAccount).where(BillingAccount.organization_id == 1)
            )
        ).scalar_one()
        assert ba.paddle_customer_id == "cus_123"
        assert ba.paddle_subscription_id == "sub_123"
        # Plan will be set by webhook; should remain unset until confirmation
        assert ba.subscription_plan_id is None
        assert ba.subscription_status == SubscriptionStatus.TRIALING
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
        transaction_response={
            "id": "txn_123",
            "checkout": {"url": "https://checkout/tx"},
        },
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
        # checkout_url now includes success_url parameter
        assert "https://checkout/tx" in data["checkout_url"]
        assert "success_url=" in data["checkout_url"]
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

    fake = _FakePaddle(transaction_response={})
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
