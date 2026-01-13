"""Paddle payment integration using official SDK."""
from typing import Optional, Dict, Any
from paddle_billing import Client, Environment, Options
from paddle_billing.Entities.Shared import Money
from paddle_billing.Resources.Customers import Operations as CustomerOperations
from paddle_billing.Resources.Subscriptions import Operations as SubscriptionOperations
from paddle_billing.Resources.Prices import Operations as PriceOperations
from paddle_billing.Resources.Products import Operations as ProductOperations
from paddle_billing.Resources.Transactions import Operations as TransactionOperations
from app.core.config import settings
import hmac
import hashlib


class PaddleClient:
    """Paddle API client using official SDK."""
    
    def __init__(self):
        self.api_key = settings.paddle_api_key
        self.vendor_id = settings.paddle_vendor_id
        
        # Set environment
        environment = (
            Environment.SANDBOX 
            if settings.paddle_environment == "sandbox" 
            else Environment.PRODUCTION
        )
        
        # Initialize Paddle client
        self.client = Client(
            api_key=self.api_key,
            options=Options(environment=environment)
        )
    
    async def create_customer(
        self,
        email: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a Paddle customer."""
        operation = CustomerOperations.CreateCustomer(
            email=email,
            name=name,
        )
        
        customer = self.client.customers.create(operation)
        return customer.dict() if hasattr(customer, 'dict') else customer.__dict__
    
    async def get_customer(self, customer_id: str) -> Dict[str, Any]:
        """Get customer details."""
        customer = self.client.customers.get(customer_id)
        return customer.dict() if hasattr(customer, 'dict') else customer.__dict__
    
    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """Create a subscription for a customer."""
        operation = SubscriptionOperations.CreateSubscription(
            customer_id=customer_id,
            items=[
                {
                    "price_id": price_id,
                    "quantity": quantity,
                }
            ],
        )
        
        subscription = self.client.subscriptions.create(operation)
        return subscription.dict() if hasattr(subscription, 'dict') else subscription.__dict__
    
    async def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Get subscription details."""
        subscription = self.client.subscriptions.get(subscription_id)
        return subscription.dict() if hasattr(subscription, 'dict') else subscription.__dict__
    
    async def update_subscription(
        self,
        subscription_id: str,
        price_id: Optional[str] = None,
        quantity: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Update a subscription."""
        items = None
        if price_id:
            items = [
                {
                    "price_id": price_id,
                    "quantity": quantity or 1,
                }
            ]
        
        operation = SubscriptionOperations.UpdateSubscription(
            subscription_id=subscription_id,
            items=items,
        )
        
        subscription = self.client.subscriptions.update(subscription_id, operation)
        return subscription.dict() if hasattr(subscription, 'dict') else subscription.__dict__
    
    async def cancel_subscription(
        self,
        subscription_id: str,
        effective_from: str = "next_billing_period",
    ) -> Dict[str, Any]:
        """Cancel a subscription."""
        operation = SubscriptionOperations.CancelSubscription(
            effective_from=effective_from,
        )
        
        subscription = self.client.subscriptions.cancel(subscription_id, operation)
        return subscription.dict() if hasattr(subscription, 'dict') else subscription.__dict__
    
    async def pause_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Pause a subscription."""
        operation = SubscriptionOperations.PauseSubscription()
        subscription = self.client.subscriptions.pause(subscription_id, operation)
        return subscription.dict() if hasattr(subscription, 'dict') else subscription.__dict__
    
    async def resume_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Resume a paused subscription."""
        operation = SubscriptionOperations.ResumeSubscription()
        subscription = self.client.subscriptions.resume(subscription_id, operation)
        return subscription.dict() if hasattr(subscription, 'dict') else subscription.__dict__
    
    async def get_prices(self, product_id: Optional[str] = None) -> Dict[str, Any]:
        """Get available prices."""
        query = PriceOperations.ListPrices()
        if product_id:
            query.product_id = product_id
        
        prices = self.client.prices.list(query)
        return [p.dict() if hasattr(p, 'dict') else p.__dict__ for p in prices]
    
    async def get_products(self) -> Dict[str, Any]:
        """Get available products."""
        query = ProductOperations.ListProducts()
        products = self.client.products.list(query)
        return [p.dict() if hasattr(p, 'dict') else p.__dict__ for p in products]
    
    async def create_price(
        self,
        product_id: str,
        amount: str,
        currency: str,
        billing_cycle_interval: str,
        billing_cycle_frequency: int = 1,
    ) -> Dict[str, Any]:
        """Create a price for a product."""
        operation = PriceOperations.CreatePrice(
            product_id=product_id,
            unit_price=Money(amount=amount, currency_code=currency),
            billing_cycle={
                "interval": billing_cycle_interval,  # day, week, month, year
                "frequency": billing_cycle_frequency,
            },
        )
        
        price = self.client.prices.create(operation)
        return price.dict() if hasattr(price, 'dict') else price.__dict__
    
    async def get_transaction(self, transaction_id: str) -> Dict[str, Any]:
        """Get transaction details."""
        transaction = self.client.transactions.get(transaction_id)
        return transaction.dict() if hasattr(transaction, 'dict') else transaction.__dict__

    async def create_transaction_checkout(
        self,
        customer_id: str,
        price_id: str,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """Create a hosted checkout transaction as a fallback to surface checkout_url."""
        operation = TransactionOperations.CreateTransaction(
            customer_id=customer_id,
            items=[
                {
                    "price_id": price_id,
                    "quantity": quantity,
                }
            ],
        )
        transaction = self.client.transactions.create(operation)
        return transaction.dict() if hasattr(transaction, 'dict') else transaction.__dict__
    
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        timestamp: str,
    ) -> bool:
        """Verify Paddle webhook signature."""
        secret = settings.paddle_webhook_secret.encode()
        message = f"{timestamp}:{payload.decode()}".encode()
        
        expected_signature = hmac.new(
            secret,
            message,
            hashlib.sha256,
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)


# Global Paddle client instance
paddle_client = PaddleClient()
