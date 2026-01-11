"""Paddle webhook handlers for payment events."""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.models.billing import BillingAccount, SubscriptionStatus


router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = logging.getLogger(__name__)


# Map Paddle statuses to our SubscriptionStatus enum
PADDLE_STATUS_MAP = {
    "active": SubscriptionStatus.ACTIVE,
    "paused": SubscriptionStatus.ACTIVE,  # Map paused to active (or create separate handling)
    "trialing": SubscriptionStatus.TRIALING,
    "past_due": SubscriptionStatus.PAST_DUE,
    "cancelled": SubscriptionStatus.CANCELED,
    "canceled": SubscriptionStatus.CANCELED,
}


# Event types that Paddle sends
PADDLE_EVENTS = {
    "subscription_created": "New subscription created",
    "subscription_updated": "Subscription updated",
    "subscription_cancelled": "Subscription cancelled",
    "subscription_paused": "Subscription paused",
    "subscription_resumed": "Subscription resumed",
    "transaction_completed": "Transaction completed",
    "transaction_billed": "Transaction billed",
    "transaction_failed": "Transaction failed",
    "transaction_cancelled": "Transaction cancelled",
}


@router.post("/paddle")
async def paddle_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle Paddle webhook events for payment updates.
    
    Paddle sends webhooks for:
    - subscription_created: New subscription started
    - subscription_updated: Subscription details changed
    - subscription_cancelled: Subscription cancelled
    - transaction_completed: Payment successful
    - transaction_failed: Payment failed
    """
    try:
        # Get request body
        try:
            body = await request.json()
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in webhook request")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON"
            )
        
        event_type = body.get("type")
        data = body.get("data", {})
        
        logger.info(f"Received Paddle webhook: {event_type}")
        
        # Handle different event types
        if event_type == "subscription_created":
            return await handle_subscription_created(data, db)
        elif event_type == "subscription_updated":
            return await handle_subscription_updated(data, db)
        elif event_type == "subscription_cancelled":
            return await handle_subscription_cancelled(data, db)
        elif event_type == "subscription_paused":
            return await handle_subscription_paused(data, db)
        elif event_type == "subscription_resumed":
            return await handle_subscription_resumed(data, db)
        elif event_type == "transaction_completed":
            return await handle_transaction_completed(data, db)
        elif event_type == "transaction_failed":
            return await handle_transaction_failed(data, db)
        else:
            logger.warning(f"Unhandled webhook event: {event_type}")
            return {"message": "Event received"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


async def handle_subscription_created(data: dict, db: AsyncSession) -> dict:
    """Handle subscription_created event."""
    paddle_subscription_id = data.get("id")
    customer_id = data.get("customer_id")
    subscription_status = data.get("status")  # active, trialing, past_due, paused, cancelled
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
        # Map Paddle status to our status
        mapped_status = PADDLE_STATUS_MAP.get(subscription_status, SubscriptionStatus.ACTIVE)
        billing_account.subscription_status = mapped_status
        if next_billed_at:
            try:
                billing_account.next_billing_date = datetime.fromisoformat(next_billed_at.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
        await db.commit()
        logger.info(f"Updated billing account {billing_account.id} with subscription status")
    else:
        logger.warning(f"Billing account not found for paddle_id {paddle_subscription_id}")
    
    return {"message": "Subscription created processed"}


async def handle_subscription_updated(data: dict, db: AsyncSession) -> dict:
    """Handle subscription_updated event."""
    paddle_subscription_id = data.get("id")
    subscription_status = data.get("status")
    
    result = await db.execute(
        select(BillingAccount).where(
            BillingAccount.paddle_subscription_id == paddle_subscription_id
        )
    )
    billing_account = result.scalar_one_or_none()
    
    if billing_account and subscription_status:
        # Map Paddle status to our status
        mapped_status = PADDLE_STATUS_MAP.get(subscription_status, SubscriptionStatus.ACTIVE)
        billing_account.subscription_status = mapped_status
        await db.commit()
        logger.info(f"Updated subscription status for account {billing_account.id}: {subscription_status} -> {mapped_status}")
    
    return {"message": "Subscription updated processed"}


async def handle_subscription_cancelled(data: dict, db: AsyncSession) -> dict:
    """Handle subscription_cancelled event."""
    paddle_subscription_id = data.get("id")
    cancelled_at = data.get("cancelled_at")
    
    result = await db.execute(
        select(BillingAccount).where(
            BillingAccount.paddle_subscription_id == paddle_subscription_id
        )
    )
    billing_account = result.scalar_one_or_none()
    
    if billing_account:
        billing_account.subscription_status = SubscriptionStatus.CANCELED
        if cancelled_at:
            try:
                billing_account.cancelled_at = datetime.fromisoformat(cancelled_at.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
        await db.commit()
        logger.info(f"Cancelled subscription for account {billing_account.id}")
    
    return {"message": "Subscription cancelled processed"}


async def handle_subscription_paused(data: dict, db: AsyncSession) -> dict:
    """Handle subscription_paused event (maps to ACTIVE status)."""
    paddle_subscription_id = data.get("id")
    
    result = await db.execute(
        select(BillingAccount).where(
            BillingAccount.paddle_subscription_id == paddle_subscription_id
        )
    )
    billing_account = result.scalar_one_or_none()
    
    if billing_account:
        # Paused is treated as ACTIVE but with a note in logs
        billing_account.subscription_status = SubscriptionStatus.ACTIVE
        await db.commit()
        logger.info(f"Paused subscription for account {billing_account.id}")
    
    return {"message": "Subscription paused processed"}


async def handle_subscription_resumed(data: dict, db: AsyncSession) -> dict:
    """Handle subscription_resumed event (maps to ACTIVE status)."""
    paddle_subscription_id = data.get("id")
    
    result = await db.execute(
        select(BillingAccount).where(
            BillingAccount.paddle_subscription_id == paddle_subscription_id
        )
    )
    billing_account = result.scalar_one_or_none()
    
    if billing_account:
        billing_account.subscription_status = SubscriptionStatus.ACTIVE
        await db.commit()
        logger.info(f"Resumed subscription for account {billing_account.id}")
    
    return {"message": "Subscription resumed processed"}


async def handle_transaction_completed(data: dict, db: AsyncSession) -> dict:
    """Handle transaction_completed event (payment successful)."""
    subscription_id = data.get("subscription_id")
    amount = data.get("amount")
    
    if subscription_id:
        result = await db.execute(
            select(BillingAccount).where(
                BillingAccount.paddle_subscription_id == subscription_id
            )
        )
        billing_account = result.scalar_one_or_none()
        
        if billing_account and amount:
            # Update balance and spending
            from decimal import Decimal
            amount_decimal = Decimal(str(amount))
            billing_account.total_spent += amount_decimal
            # Deduct from balance if available
            if billing_account.balance > 0:
                billing_account.balance = max(billing_account.balance - amount_decimal, Decimal("0.0"))
            
            await db.commit()
            logger.info(f"Transaction completed for account {billing_account.id}: ${amount}")
    
    return {"message": "Transaction completed processed"}


async def handle_transaction_failed(data: dict, db: AsyncSession) -> dict:
    """Handle transaction_failed event (payment failure)."""
    subscription_id = data.get("subscription_id")
    error_message = data.get("error", {}).get("message", "Unknown error")
    
    logger.warning(f"Transaction failed for subscription {subscription_id}: {error_message}")
    
    return {"message": "Transaction failed processed"}
