"""Paddle webhook handlers for payment events."""
import json
import logging
from datetime import datetime, timezone
from typing import Optional
import hmac
import hashlib

from fastapi import APIRouter, HTTPException, Request, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.core.config import settings
from app.core.paddle import paddle_client
from app.models.billing import BillingAccount, SubscriptionStatus, PaddleWebhookEvent, WebhookEventStatus


router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = logging.getLogger(__name__)


# Map Paddle statuses to our SubscriptionStatus enum
PADDLE_STATUS_MAP = {
    "active": SubscriptionStatus.ACTIVE,
    "paused": SubscriptionStatus.PAUSED,
    "trialing": SubscriptionStatus.TRIALING,
    "past_due": SubscriptionStatus.PAST_DUE,
    "cancelled": SubscriptionStatus.CANCELED,
    "canceled": SubscriptionStatus.CANCELED,
}

# Events to ignore (informational, no action needed)
PADDLE_IGNORED_EVENTS = {
    "product.created",
    "product.updated",
    "product.imported",
    "price.created",
    "price.updated",
    "price.imported",
    "customer.created",
    "customer.updated",
    "customer.imported",
}


@router.post("/paddle")
async def paddle_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle Paddle webhook events for payment updates.
    
    Paddle sends webhooks with signature verification:
    - Header: Paddle-Signature
    - Format: ts=<timestamp>;h1=<hmac_hash>
    - Body: JSON payload
    """
    webhook_event = None
    signature_valid = False
    signature_timestamp = None
    
    try:
        raw_body = await request.body()

        # Signature verification (per Paddle SDK documentation)
        if settings.paddle_webhook_secret:
            # Get Paddle-Signature header (case-insensitive lookup)
            signature_header = None
            for header_name, header_value in request.headers.items():
                if header_name.lower() == "paddle-signature":
                    signature_header = header_value
                    break
            
            if not signature_header:
                logger.warning(f"Missing Paddle-Signature header. Available headers: {list(request.headers.keys())}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing webhook signature")

            # Extract timestamp from signature header (format: ts=<timestamp>;h1=<hash>)
            try:
                for part in signature_header.split(";"):
                    if part.startswith("ts="):
                        ts_value = part[3:]
                        signature_timestamp = datetime.fromtimestamp(int(ts_value), tz=timezone.utc)
                        break
            except (ValueError, TypeError):
                pass

            # Verify signature using Paddle SDK method
            signature_valid = paddle_client.verify_webhook_signature(raw_body, signature_header, settings.paddle_webhook_secret)
            if not signature_valid:
                logger.warning("Paddle signature verification failed")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")
        else:
            signature_valid = True  # No secret configured, accept all

        # Parse request body
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in webhook request")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON"
            )
        
        # Extract event details (Paddle uses event_type)
        event_type = body.get("event_type")
        data = body.get("data", {})
        event_id = body.get("event_id")
        
        # Extract IDs from data for logging
        paddle_subscription_id = data.get("id") if "subscription" in (event_type or "") else data.get("subscription_id")
        paddle_customer_id = data.get("customer_id")
        paddle_transaction_id = data.get("id") if "transaction" in (event_type or "") else data.get("transaction_id")
        
        # Check for duplicate event (idempotency) - before creating webhook record
        if event_id:
            existing_event = await db.execute(
                select(PaddleWebhookEvent).where(
                    PaddleWebhookEvent.paddle_event_id == event_id
                )
            )
            if existing_event.scalar_one_or_none():
                logger.info(f"Duplicate webhook event ignored: {event_id}")
                return {"message": "Event already processed"}
        
        # Create webhook event record
        webhook_event = PaddleWebhookEvent(
            paddle_event_id=event_id or f"unknown_{datetime.utcnow().timestamp()}",
            event_type=event_type or "unknown",
            paddle_subscription_id=paddle_subscription_id,
            paddle_customer_id=paddle_customer_id,
            paddle_transaction_id=paddle_transaction_id,
            status=WebhookEventStatus.RECEIVED,
            signature_valid=signature_valid,
            signature_timestamp=signature_timestamp,
            payload_json=json.dumps(body, default=str)[:10000],  # Limit payload size
            received_at=datetime.utcnow(),
        )
        db.add(webhook_event)
        await db.flush()  # Get the ID
        
        logger.info(f"Received Paddle webhook: {event_type} event_id={event_id}")
        logger.debug(f"Webhook data: {json.dumps(data, default=str)[:200]}...")
        
        # Ignore events that don't require action
        if event_type in PADDLE_IGNORED_EVENTS:
            logger.info(f"Ignoring Paddle event: {event_type} (no action needed)")
            webhook_event.status = WebhookEventStatus.PROCESSED
            webhook_event.processed_at = datetime.utcnow()
            await db.commit()
            return {"message": "Event acknowledged"}
        
        # Handle subscription events (normalize event names)
        event_normalized = event_type.replace(".", "_") if event_type else ""
        
        result = None
        if event_normalized in ("subscription_created", "subscription_activated"):
            result = await handle_subscription_created(data, db, event_id, webhook_event)
        elif event_normalized == "subscription_updated":
            result = await handle_subscription_updated(data, db, event_id, webhook_event)
        elif event_normalized in ("subscription_cancelled", "subscription_canceled"):
            result = await handle_subscription_cancelled(data, db, event_id, webhook_event)
        elif event_normalized == "subscription_paused":
            result = await handle_subscription_paused(data, db, event_id, webhook_event)
        elif event_normalized == "subscription_resumed":
            result = await handle_subscription_resumed(data, db, event_id, webhook_event)
        elif event_normalized in ("transaction_completed", "transaction_paid"):
            result = await handle_transaction_completed(data, db, event_id, webhook_event)
        elif event_normalized == "transaction_failed":
            result = await handle_transaction_failed(data, db, event_id, webhook_event)
        else:
            logger.warning(f"Unhandled webhook event: {event_type}")
            webhook_event.status = WebhookEventStatus.PROCESSED
            webhook_event.processed_at = datetime.utcnow()
            await db.commit()
            return {"message": "Event received"}
        
        # Mark as processed
        webhook_event.status = WebhookEventStatus.PROCESSED
        webhook_event.processed_at = datetime.utcnow()
        await db.commit()
        return result
    
    except HTTPException:
        # Mark webhook as failed if it was created
        if webhook_event:
            webhook_event.status = WebhookEventStatus.FAILED
            webhook_event.error_message = "HTTP error during processing"
            webhook_event.processed_at = datetime.utcnow()
            await db.commit()
        raise
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}", exc_info=True)
        # Mark webhook as failed
        if webhook_event:
            webhook_event.status = WebhookEventStatus.FAILED
            webhook_event.error_message = str(e)[:500]
            webhook_event.processed_at = datetime.utcnow()
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


async def handle_subscription_created(data: dict, db: AsyncSession, event_id: Optional[str] = None, webhook_event: Optional[PaddleWebhookEvent] = None) -> dict:
    """Handle subscription.created event."""
    paddle_subscription_id = data.get("id")
    customer_id = data.get("customer_id")
    subscription_status = data.get("status")
    next_billed_at = data.get("next_billed_at")
    
    logger.info(
        f"Subscription created: paddle_id={paddle_subscription_id}, "
        f"customer_id={customer_id}, status={subscription_status}"
    )
    
    # First, try to find by paddle_subscription_id (in case it was already set)
    result = await db.execute(
        select(BillingAccount).where(
            BillingAccount.paddle_subscription_id == paddle_subscription_id
        )
    )
    billing_account = result.scalar_one_or_none()
    
    # If not found by subscription_id, try to find by customer_id
    # This is the normal case when subscription is first created
    if not billing_account and customer_id:
        result = await db.execute(
            select(BillingAccount).where(
                BillingAccount.paddle_customer_id == customer_id
            )
        )
        billing_account = result.scalar_one_or_none()
    
    if billing_account:
        if event_id and billing_account.last_webhook_event_id == event_id:
            logger.info(f"Duplicate event: {event_id}")
            return {"message": "Event already processed"}
        
        # Set the paddle_subscription_id if not already set
        if paddle_subscription_id and not billing_account.paddle_subscription_id:
            billing_account.paddle_subscription_id = paddle_subscription_id
            logger.info(f"Set paddle_subscription_id={paddle_subscription_id} for customer={customer_id}")
        
        # Map Paddle status to our status
        if subscription_status:
            mapped_status = PADDLE_STATUS_MAP.get(subscription_status, SubscriptionStatus.ACTIVE)
            billing_account.subscription_status = mapped_status
        
        # Update next billing date
        if next_billed_at:
            try:
                billing_account.next_billing_date = datetime.fromisoformat(
                    str(next_billed_at).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        
        billing_account.last_webhook_event_id = event_id
        
        # Link webhook event to billing account
        if webhook_event:
            webhook_event.billing_account_id = billing_account.id
        
        await db.commit()
        logger.info(f"Updated subscription: {paddle_subscription_id} -> {billing_account.subscription_status}")
    else:
        logger.warning(f"No billing account found for subscription={paddle_subscription_id}, customer={customer_id}")
    
    return {"message": "Subscription created"}


async def handle_subscription_updated(data: dict, db: AsyncSession, event_id: Optional[str] = None, webhook_event: Optional[PaddleWebhookEvent] = None) -> dict:
    """Handle subscription.updated event."""
    paddle_subscription_id = data.get("id")
    subscription_status = data.get("status")
    next_billed_at = data.get("next_billed_at")
    
    logger.info(f"Subscription updated: paddle_id={paddle_subscription_id}, status={subscription_status}")
    
    result = await db.execute(
        select(BillingAccount).where(
            BillingAccount.paddle_subscription_id == paddle_subscription_id
        )
    )
    billing_account = result.scalar_one_or_none()
    
    if billing_account and subscription_status:
        if event_id and billing_account.last_webhook_event_id == event_id:
            logger.info(f"Duplicate event: {event_id}")
            return {"message": "Event already processed"}
        
        mapped_status = PADDLE_STATUS_MAP.get(subscription_status, SubscriptionStatus.ACTIVE)
        billing_account.subscription_status = mapped_status
        
        if next_billed_at:
            try:
                billing_account.next_billing_date = datetime.fromisoformat(
                    str(next_billed_at).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        
        billing_account.last_webhook_event_id = event_id
        
        if webhook_event:
            webhook_event.billing_account_id = billing_account.id
        
        await db.commit()
        logger.info(f"Updated subscription: {paddle_subscription_id} -> {mapped_status}")
    
    return {"message": "Subscription updated"}


async def handle_subscription_cancelled(data: dict, db: AsyncSession, event_id: Optional[str] = None, webhook_event: Optional[PaddleWebhookEvent] = None) -> dict:
    """Handle subscription.cancelled event."""
    paddle_subscription_id = data.get("id")
    cancelled_at = data.get("cancelled_at")
    
    logger.info(f"Subscription cancelled: paddle_id={paddle_subscription_id}")
    
    result = await db.execute(
        select(BillingAccount).where(
            BillingAccount.paddle_subscription_id == paddle_subscription_id
        )
    )
    billing_account = result.scalar_one_or_none()
    
    if billing_account:
        if event_id and billing_account.last_webhook_event_id == event_id:
            logger.info(f"Duplicate event: {event_id}")
            return {"message": "Event already processed"}
        
        billing_account.subscription_status = SubscriptionStatus.CANCELED
        
        if cancelled_at:
            try:
                billing_account.cancelled_at = datetime.fromisoformat(
                    str(cancelled_at).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        
        billing_account.last_webhook_event_id = event_id
        
        if webhook_event:
            webhook_event.billing_account_id = billing_account.id
        
        await db.commit()
        logger.info(f"Cancelled subscription: {paddle_subscription_id}")
    
    return {"message": "Subscription cancelled"}


async def handle_subscription_paused(data: dict, db: AsyncSession, event_id: Optional[str] = None, webhook_event: Optional[PaddleWebhookEvent] = None) -> dict:
    """Handle subscription.paused event."""
    paddle_subscription_id = data.get("id")
    paused_at = data.get("paused_at")
    
    logger.info(f"Subscription paused: paddle_id={paddle_subscription_id}")
    
    result = await db.execute(
        select(BillingAccount).where(
            BillingAccount.paddle_subscription_id == paddle_subscription_id
        )
    )
    billing_account = result.scalar_one_or_none()
    
    if billing_account:
        if event_id and billing_account.last_webhook_event_id == event_id:
            logger.info(f"Duplicate event: {event_id}")
            return {"message": "Event already processed"}
        
        billing_account.subscription_status = SubscriptionStatus.PAUSED
        
        # Store paused_at timestamp
        if paused_at:
            try:
                billing_account.paused_at = datetime.fromisoformat(
                    str(paused_at).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                billing_account.paused_at = datetime.utcnow()
        else:
            billing_account.paused_at = datetime.utcnow()
        
        billing_account.last_webhook_event_id = event_id
        
        if webhook_event:
            webhook_event.billing_account_id = billing_account.id
        
        await db.commit()
        logger.info(f"Paused subscription: {paddle_subscription_id}")
    
    return {"message": "Subscription paused"}


async def handle_subscription_resumed(data: dict, db: AsyncSession, event_id: Optional[str] = None, webhook_event: Optional[PaddleWebhookEvent] = None) -> dict:
    """Handle subscription.resumed event."""
    paddle_subscription_id = data.get("id")
    next_billed_at = data.get("next_billed_at")
    
    logger.info(f"Subscription resumed: paddle_id={paddle_subscription_id}")
    
    result = await db.execute(
        select(BillingAccount).where(
            BillingAccount.paddle_subscription_id == paddle_subscription_id
        )
    )
    billing_account = result.scalar_one_or_none()
    
    if billing_account:
        if event_id and billing_account.last_webhook_event_id == event_id:
            logger.info(f"Duplicate event: {event_id}")
            return {"message": "Event already processed"}
        
        billing_account.subscription_status = SubscriptionStatus.ACTIVE
        billing_account.paused_at = None  # Clear paused timestamp
        billing_account.last_webhook_event_id = event_id
        
        # Update next billing date if provided
        if next_billed_at:
            try:
                billing_account.next_billing_date = datetime.fromisoformat(
                    str(next_billed_at).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        
        if webhook_event:
            webhook_event.billing_account_id = billing_account.id
        
        await db.commit()
        logger.info(f"Resumed subscription: {paddle_subscription_id}")
    
    return {"message": "Subscription resumed"}


async def handle_transaction_completed(data: dict, db: AsyncSession, event_id: Optional[str] = None, webhook_event: Optional[PaddleWebhookEvent] = None) -> dict:
    """Handle transaction.completed event."""
    transaction_id = data.get("id")
    subscription_id = data.get("subscription_id")
    
    logger.info(f"Transaction completed: id={transaction_id}, subscription_id={subscription_id}")
    
    if subscription_id:
        result = await db.execute(
            select(BillingAccount).where(
                BillingAccount.paddle_subscription_id == subscription_id
            )
        )
        billing_account = result.scalar_one_or_none()
        
        if billing_account:
            if event_id and billing_account.last_webhook_event_id == event_id:
                logger.info(f"Duplicate event: {event_id}")
                return {"message": "Event already processed"}
            
            billing_account.last_transaction_id = transaction_id
            billing_account.last_webhook_event_id = event_id
            
            if webhook_event:
                webhook_event.billing_account_id = billing_account.id
            
            await db.commit()
    
    return {"message": "Transaction completed"}


async def handle_transaction_failed(data: dict, db: AsyncSession, event_id: Optional[str] = None, webhook_event: Optional[PaddleWebhookEvent] = None) -> dict:
    """Handle transaction.failed event."""
    transaction_id = data.get("id")
    subscription_id = data.get("subscription_id")
    
    logger.warning(f"Transaction failed: id={transaction_id}, subscription_id={subscription_id}")
    logger.debug(f"Failed transaction data: {json.dumps(data, default=str)[:500]}")
    
    if subscription_id:
        result = await db.execute(
            select(BillingAccount).where(
                BillingAccount.paddle_subscription_id == subscription_id
            )
        )
        billing_account = result.scalar_one_or_none()
        
        if billing_account:
            if event_id and billing_account.last_webhook_event_id == event_id:
                logger.info(f"Duplicate event: {event_id}")
                return {"message": "Event already processed"}
            
            billing_account.last_webhook_event_id = event_id
            
            if webhook_event:
                webhook_event.billing_account_id = billing_account.id
            
            await db.commit()
    
    return {"message": "Transaction failed"}
