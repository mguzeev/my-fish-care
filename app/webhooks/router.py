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
from app.models.billing import BillingAccount, SubscriptionStatus


router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = logging.getLogger(__name__)


# Map Paddle statuses to our SubscriptionStatus enum
PADDLE_STATUS_MAP = {
    "active": SubscriptionStatus.ACTIVE,
    "paused": SubscriptionStatus.ACTIVE,
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

            # Verify signature using Paddle SDK method
            if not paddle_client.verify_webhook_signature(raw_body, signature_header, settings.paddle_webhook_secret):
                logger.warning("Paddle signature verification failed")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

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
        
        logger.info(f"Received Paddle webhook: {event_type} event_id={event_id}")
        logger.debug(f"Webhook data: {json.dumps(data, default=str)[:200]}...")
        
        # Ignore events that don't require action
        if event_type in PADDLE_IGNORED_EVENTS:
            logger.info(f"Ignoring Paddle event: {event_type} (no action needed)")
            return {"message": "Event acknowledged"}
        
        # Handle subscription events (normalize event names)
        event_normalized = event_type.replace(".", "_") if event_type else ""
        
        if event_normalized in ("subscription_created", "subscription_activated"):
            return await handle_subscription_created(data, db, event_id)
        elif event_normalized == "subscription_updated":
            return await handle_subscription_updated(data, db, event_id)
        elif event_normalized in ("subscription_cancelled", "subscription_canceled"):
            return await handle_subscription_cancelled(data, db, event_id)
        elif event_normalized == "subscription_paused":
            return await handle_subscription_paused(data, db, event_id)
        elif event_normalized == "subscription_resumed":
            return await handle_subscription_resumed(data, db, event_id)
        elif event_normalized in ("transaction_completed", "transaction_paid"):
            return await handle_transaction_completed(data, db, event_id)
        elif event_normalized == "transaction_failed":
            return await handle_transaction_failed(data, db, event_id)
        else:
            logger.warning(f"Unhandled webhook event: {event_type}")
            return {"message": "Event received"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


async def handle_subscription_created(data: dict, db: AsyncSession, event_id: Optional[str] = None) -> dict:
    """Handle subscription.created event."""
    paddle_subscription_id = data.get("id")
    customer_id = data.get("customer_id")
    subscription_status = data.get("status")
    next_billed_at = data.get("next_billed_at")
    
    logger.info(
        f"Subscription created: paddle_id={paddle_subscription_id}, "
        f"customer_id={customer_id}, status={subscription_status}"
    )
    
    # Find billing account by paddle subscription ID
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
        
        # Map Paddle status to our status
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
        await db.commit()
        logger.info(f"Updated subscription: {paddle_subscription_id} -> {mapped_status}")
    
    return {"message": "Subscription created"}


async def handle_subscription_updated(data: dict, db: AsyncSession, event_id: Optional[str] = None) -> dict:
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
        await db.commit()
        logger.info(f"Updated subscription: {paddle_subscription_id} -> {mapped_status}")
    
    return {"message": "Subscription updated"}


async def handle_subscription_cancelled(data: dict, db: AsyncSession, event_id: Optional[str] = None) -> dict:
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
        await db.commit()
        logger.info(f"Cancelled subscription: {paddle_subscription_id}")
    
    return {"message": "Subscription cancelled"}


async def handle_subscription_paused(data: dict, db: AsyncSession, event_id: Optional[str] = None) -> dict:
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
        
        billing_account.subscription_status = SubscriptionStatus.ACTIVE  # Map paused to ACTIVE
        billing_account.last_webhook_event_id = event_id
        await db.commit()
        logger.info(f"Paused subscription: {paddle_subscription_id}")
    
    return {"message": "Subscription paused"}


async def handle_subscription_resumed(data: dict, db: AsyncSession, event_id: Optional[str] = None) -> dict:
    """Handle subscription.resumed event."""
    paddle_subscription_id = data.get("id")
    
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
        billing_account.last_webhook_event_id = event_id
        await db.commit()
        logger.info(f"Resumed subscription: {paddle_subscription_id}")
    
    return {"message": "Subscription resumed"}


async def handle_transaction_completed(data: dict, db: AsyncSession, event_id: Optional[str] = None) -> dict:
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
            await db.commit()
    
    return {"message": "Transaction completed"}


async def handle_transaction_failed(data: dict, db: AsyncSession, event_id: Optional[str] = None) -> dict:
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
            await db.commit()
    
    return {"message": "Transaction failed"}
