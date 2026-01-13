"""Tests for Paddle webhook handlers."""
import json
import hmac
import hashlib
from datetime import datetime, timezone

import pytest
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.billing import BillingAccount, SubscriptionStatus
from app.models.organization import Organization


@pytest.mark.asyncio
async def test_paddle_webhook_subscription_created(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """Test webhook for subscription_created event."""
    # Setup
    secret = "test-paddle-webhook-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)
    
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
    
    # Create signed webhook
    body = {
        "event_type": "subscription.created",
        "event_id": "evt_test_123",
        "occurred_at": "2026-02-11T18:00:00Z",
        "data": {
            "id": "sub_123",
            "customer_id": "cus_456",
            "status": "active",
            "next_billed_at": "2026-02-11T18:00:00Z",
        },
    }
    raw = json.dumps(body)
    sig = _sign_payload(raw, secret)
    
    response = await client.post(
        "/webhooks/paddle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sig,
        },
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Subscription created"
    
    # Verify account was updated
    await db_session.refresh(ba)
    assert ba.subscription_status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_paddle_webhook_subscription_updated(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """Test webhook for subscription_updated event."""
    secret = "test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)
    
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
    body = {
        "event_type": "subscription.updated",
        "event_id": "evt_123",
        "data": {
            "id": "sub_123",
            "status": "paused",
        },
    }
    raw = json.dumps(body)
    sig = _sign_payload(raw, secret)
    
    response = await client.post(
        "/webhooks/paddle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sig,
        },
    )
    assert response.status_code == 200
    
    # Verify account was updated
    await db_session.refresh(ba)
    assert ba.subscription_status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_paddle_webhook_subscription_cancelled(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """Test webhook for subscription_cancelled event."""
    secret = "test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)
    
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
    body = {
        "event_type": "subscription.cancelled",
        "event_id": "evt_123",
        "data": {
            "id": "sub_123",
            "cancelled_at": "2026-01-11T18:00:00Z",
        },
    }
    raw = json.dumps(body)
    sig = _sign_payload(raw, secret)
    
    response = await client.post(
        "/webhooks/paddle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sig,
        },
    )
    assert response.status_code == 200
    
    # Verify account was updated
    await db_session.refresh(ba)
    assert ba.subscription_status == SubscriptionStatus.CANCELED


@pytest.mark.asyncio
async def test_paddle_webhook_transaction_completed(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """Test webhook for transaction_completed event."""
    secret = "test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)
    
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
    body = {
        "event_type": "transaction.completed",
        "event_id": "evt_123",
        "data": {
            "id": "txn_123",
            "subscription_id": "sub_123",
            "amount": "19.99",
        },
    }
    raw = json.dumps(body)
    sig = _sign_payload(raw, secret)
    
    response = await client.post(
        "/webhooks/paddle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sig,
        },
    )
    assert response.status_code == 200
    
    # Verify transaction was recorded
    await db_session.refresh(ba)
    assert ba.last_transaction_id == "txn_123"


@pytest.mark.asyncio
async def test_paddle_webhook_transaction_failed(client: AsyncClient, monkeypatch):
    """Test webhook for transaction_failed event."""
    secret = "test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)
    
    body = {
        "event_type": "transaction.failed",
        "event_id": "evt_123",
        "data": {
            "id": "txn_123",
            "subscription_id": "sub_123",
            "error": {"message": "Insufficient funds"},
        },
    }
    raw = json.dumps(body)
    sig = _sign_payload(raw, secret)
    
    response = await client.post(
        "/webhooks/paddle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sig,
        },
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Transaction failed"


@pytest.mark.asyncio
async def test_paddle_webhook_invalid_json(client: AsyncClient, monkeypatch):
    """Test webhook with invalid JSON."""
    secret = "test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)
    
    import time
    timestamp = str(int(time.time()))
    content = "invalid json"
    message = f"{timestamp}:{content}".encode()
    h1 = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    sig = f"ts={timestamp};h1={h1}"
    
    response = await client.post(
        "/webhooks/paddle",
        content=content,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sig,
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_paddle_webhook_unknown_event(client: AsyncClient, monkeypatch):
    """Test webhook with unknown event type."""
    secret = "test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)
    
    body = {
        "event_type": "unknown_event_type",
        "data": {},
    }
    raw = json.dumps(body)
    sig = _sign_payload(raw, secret)
    
    response = await client.post(
        "/webhooks/paddle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sig,
        },
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Event received"


@pytest.mark.asyncio
async def test_paddle_webhook_subscription_paused(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """Test webhook for subscription_paused event (maps to ACTIVE)."""
    secret = "test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)
    
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
    body = {
        "event_type": "subscription.paused",
        "event_id": "evt_123",
        "data": {"id": "sub_123"},
    }
    raw = json.dumps(body)
    sig = _sign_payload(raw, secret)
    
    response = await client.post(
        "/webhooks/paddle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sig,
        },
    )
    assert response.status_code == 200
    
    # Verify account remains ACTIVE
    await db_session.refresh(ba)
    assert ba.subscription_status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_paddle_webhook_subscription_resumed(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """Test webhook for subscription_resumed event (maps to ACTIVE)."""
    secret = "test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)
    
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
    body = {
        "event_type": "subscription.resumed",
        "event_id": "evt_123",
        "data": {"id": "sub_123"},
    }
    raw = json.dumps(body)
    sig = _sign_payload(raw, secret)
    
    response = await client.post(
        "/webhooks/paddle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sig,
        },
    )
    assert response.status_code == 200
    
    # Verify account remains ACTIVE
    await db_session.refresh(ba)
    assert ba.subscription_status == SubscriptionStatus.ACTIVE


def _sign_payload(raw_body: str, secret: str) -> str:
    """
    Create Paddle webhook signature header.
    
    Format: Paddle-Signature: ts=<timestamp>;h1=<hmac>
    Signature calculated as: HMAC-SHA256(secret, "{timestamp}:{body}")
    """
    import time
    timestamp = str(int(time.time()))
    message = f"{timestamp}:{raw_body}".encode()
    h1 = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return f"ts={timestamp};h1={h1}"


@pytest.mark.asyncio
async def test_paddle_webhook_signature_valid(client: AsyncClient, monkeypatch):
    secret = "test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)

    body = {"event_type": "subscription.updated", "data": {"id": "sub_x", "status": "active"}}
    raw = json.dumps(body)
    sig = _sign_payload(raw, secret)

    response = await client.post(
        "/webhooks/paddle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sig,
        },
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_paddle_webhook_signature_invalid(client: AsyncClient, monkeypatch):
    secret = "test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)

    body = {"event_type": "subscription.updated", "data": {"id": "sub_x", "status": "active"}}
    raw = json.dumps(body)

    response = await client.post(
        "/webhooks/paddle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": "ts=1234567890;h1=bad-signature",
        },
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_paddle_webhook_idempotent_event(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    secret = "test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)

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
    await db_session.refresh(ba)

    body = {
        "event_type": "subscription.updated",
        "event_id": "evt_1",
        "data": {"id": "sub_123", "status": "paused"},
    }
    raw = json.dumps(body)
    sig = _sign_payload(raw, secret)

    # First delivery
    response = await client.post(
        "/webhooks/paddle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sig,
        },
    )
    assert response.status_code == 200

    await db_session.refresh(ba)
    # paused maps to ACTIVE; event id stored
    assert ba.subscription_status == SubscriptionStatus.ACTIVE
    assert ba.last_webhook_event_id == "evt_1"

    # Second delivery with same event id should be ignored
    response2 = await client.post(
        "/webhooks/paddle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sig,
        },
    )
    assert response2.status_code == 200

    await db_session.refresh(ba)
    assert ba.last_webhook_event_id == "evt_1"
    assert ba.subscription_status == SubscriptionStatus.ACTIVE
