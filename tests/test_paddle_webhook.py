"""Tests for Paddle webhook handlers."""
import pytest
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingAccount, SubscriptionStatus
from app.models.organization import Organization


@pytest.mark.asyncio
async def test_paddle_webhook_subscription_created(
    client: AsyncClient, db_session: AsyncSession
):
    """Test webhook for subscription_created event."""
    # Create org and billing account
    org = Organization(name="Test Org", slug="test-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    
    ba = BillingAccount(organization_id=org.id)
    db_session.add(ba)
    await db_session.commit()
    await db_session.refresh(ba)
    
    # Update with paddle ID
    ba.paddle_subscription_id = "sub_123"
    await db_session.commit()
    
    # Send webhook
    response = await client.post(
        "/webhooks/paddle",
        json={
            "type": "subscription_created",
            "data": {
                "id": "sub_123",
                "customer_id": "cus_456",
                "status": "active",
                "next_billed_at": "2026-02-11T18:00:00Z",
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Subscription created processed"
    
    # Verify account was updated
    await db_session.refresh(ba)
    assert ba.subscription_status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_paddle_webhook_subscription_updated(
    client: AsyncClient, db_session: AsyncSession
):
    """Test webhook for subscription_updated event."""
    org = Organization(name="Test Org", slug="test-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    
    ba = BillingAccount(
        organization_id=org.id,
        paddle_subscription_id="sub_123",
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(ba)
    await db_session.commit()
    
    # Send webhook to pause subscription
    response = await client.post(
        "/webhooks/paddle",
        json={
            "type": "subscription_updated",
            "data": {
                "id": "sub_123",
                "status": "paused",
            },
        },
    )
    assert response.status_code == 200
    
    # Verify account was updated
    await db_session.refresh(ba)
    assert ba.subscription_status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_paddle_webhook_subscription_cancelled(
    client: AsyncClient, db_session: AsyncSession
):
    """Test webhook for subscription_cancelled event."""
    org = Organization(name="Test Org", slug="test-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    
    ba = BillingAccount(
        organization_id=org.id,
        paddle_subscription_id="sub_123",
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(ba)
    await db_session.commit()
    
    # Send webhook
    response = await client.post(
        "/webhooks/paddle",
        json={
            "type": "subscription_cancelled",
            "data": {
                "id": "sub_123",
                "cancelled_at": "2026-01-11T18:00:00Z",
            },
        },
    )
    assert response.status_code == 200
    
    # Verify account was updated
    await db_session.refresh(ba)
    assert ba.subscription_status == SubscriptionStatus.CANCELED


@pytest.mark.asyncio
async def test_paddle_webhook_transaction_completed(
    client: AsyncClient, db_session: AsyncSession
):
    """Test webhook for transaction_completed event."""
    org = Organization(name="Test Org", slug="test-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    
    ba = BillingAccount(
        organization_id=org.id,
        paddle_subscription_id="sub_123",
        balance=Decimal("100.00"),
        total_spent=Decimal("0.00"),
    )
    db_session.add(ba)
    await db_session.commit()
    await db_session.refresh(ba)
    
    initial_spent = ba.total_spent
    initial_balance = ba.balance
    
    # Send webhook
    response = await client.post(
        "/webhooks/paddle",
        json={
            "type": "transaction_completed",
            "data": {
                "subscription_id": "sub_123",
                "amount": "19.99",
            },
        },
    )
    assert response.status_code == 200
    
    # Verify accounting was updated
    await db_session.refresh(ba)
    assert ba.total_spent == initial_spent + Decimal("19.99")
    assert ba.balance == initial_balance - Decimal("19.99")


@pytest.mark.asyncio
async def test_paddle_webhook_transaction_failed(client: AsyncClient):
    """Test webhook for transaction_failed event."""
    response = await client.post(
        "/webhooks/paddle",
        json={
            "type": "transaction_failed",
            "data": {
                "subscription_id": "sub_123",
                "error": {"message": "Insufficient funds"},
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Transaction failed processed"


@pytest.mark.asyncio
async def test_paddle_webhook_invalid_json(client: AsyncClient):
    """Test webhook with invalid JSON."""
    response = await client.post(
        "/webhooks/paddle",
        content="invalid json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_paddle_webhook_unknown_event(client: AsyncClient):
    """Test webhook with unknown event type."""
    response = await client.post(
        "/webhooks/paddle",
        json={
            "type": "unknown_event_type",
            "data": {},
        },
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Event received"


@pytest.mark.asyncio
async def test_paddle_webhook_subscription_paused(
    client: AsyncClient, db_session: AsyncSession
):
    """Test webhook for subscription_paused event (maps to ACTIVE)."""
    org = Organization(name="Test Org", slug="test-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    
    ba = BillingAccount(
        organization_id=org.id,
        paddle_subscription_id="sub_123",
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(ba)
    await db_session.commit()
    
    # Send webhook
    response = await client.post(
        "/webhooks/paddle",
        json={
            "type": "subscription_paused",
            "data": {"id": "sub_123"},
        },
    )
    assert response.status_code == 200
    
    # Verify account remains ACTIVE
    await db_session.refresh(ba)
    assert ba.subscription_status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_paddle_webhook_subscription_resumed(
    client: AsyncClient, db_session: AsyncSession
):
    """Test webhook for subscription_resumed event (maps to ACTIVE)."""
    org = Organization(name="Test Org", slug="test-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    
    ba = BillingAccount(
        organization_id=org.id,
        paddle_subscription_id="sub_123",
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(ba)
    await db_session.commit()
    
    # Send webhook
    response = await client.post(
        "/webhooks/paddle",
        json={
            "type": "subscription_resumed",
            "data": {"id": "sub_123"},
        },
    )
    assert response.status_code == 200
    
    # Verify account remains ACTIVE
    await db_session.refresh(ba)
    assert ba.subscription_status == SubscriptionStatus.ACTIVE
