"""Paddle payment integration using paddle-billing-client SDK."""
from typing import Optional, Dict, Any
from app.core.config import settings
import hmac
import hashlib


class PaddleClient:
    """Paddle API client using paddle-billing-client REST SDK."""
    
    def __init__(self):
        # Lazy import: only load Paddle SDK when actually used
        try:
            from paddle_billing_client.client import PaddleApiClient
            from apiclient.authentication_methods import HeaderAuthentication
        except ImportError as e:
            raise ImportError(
                f"paddle-billing-client SDK not installed or import error: {e}. "
                "Install it with: pip install paddle-billing-client"
            )
        
        self.api_key = settings.paddle_api_key
        self.vendor_id = settings.paddle_vendor_id
        
        # Determine base URL based on environment
        base_url = (
            "https://sandbox-api.paddle.com"
            if settings.paddle_environment == "sandbox"
            else "https://api.paddle.com"
        )
        
        # Initialize Paddle API client
        self.client = PaddleApiClient(base_url=base_url)
        
        # Set Bearer token authentication
        auth = HeaderAuthentication(token=self.api_key)
        self.client.set_authentication_method(auth)
    
    def _response_to_dict(self, response: Any) -> Dict[str, Any]:
        """Convert API response object to dict."""
        if response is None:
            return {}
        if isinstance(response, dict):
            return response
        # Try Pydantic model
        if hasattr(response, 'model_dump'):
            return response.model_dump()
        # Try dict() method
        if hasattr(response, 'dict'):
            try:
                return response.dict()
            except Exception:
                pass
        # Try __dict__
        if hasattr(response, '__dict__'):
            result = {}
            for key, val in response.__dict__.items():
                if not key.startswith('_'):
                    result[key] = val
            return result
        return {}
    
    async def create_customer(
        self,
        email: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a Paddle customer, or return existing customer if email already exists."""
        from paddle_billing_client.models.customer import CustomerRequest, CustomerQueryParams
        from apiclient.exceptions import ClientError
        
        customer_data = CustomerRequest(email=email, name=name or email)
        try:
            response = self.client.create_customer(data=customer_data)
            response_dict = self._response_to_dict(response)
            # Response is {meta: {...}, data: {...}} - extract the data
            if 'data' in response_dict:
                return response_dict['data']
            return response_dict
        except ClientError as e:
            # 409 Conflict means customer with this email already exists
            if "409" in str(e):
                # Search for existing customer by email
                existing = await self.get_customer_by_email(email)
                if existing:
                    return existing
            raise
    
    async def get_customer_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find a customer by email address."""
        from paddle_billing_client.models.customer import CustomerQueryParams
        
        query_params = CustomerQueryParams(email=email)
        response = self.client.list_customers(query_params=query_params)
        response_dict = self._response_to_dict(response)
        
        # Response contains {data: [...], meta: {...}}
        customers = response_dict.get('data', [])
        if customers and len(customers) > 0:
            return customers[0]
        return None
    
    async def get_customer(self, customer_id: str) -> Dict[str, Any]:
        """Get customer details."""
        response = self.client.get_customer(customer_id)
        return self._response_to_dict(response)
    
    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """
        Create a subscription for a customer.
        
        Note: In Paddle Billing API, subscriptions are created via transactions.
        This method creates a transaction with the subscription items, which
        generates a checkout_url. The actual subscription is created when the
        customer completes payment.
        
        Returns transaction data with checkout url for payment.
        """
        from paddle_billing_client.models.transaction import TransactionRequest
        transaction_data = TransactionRequest(
            customer_id=customer_id,
            items=[{"price_id": price_id, "quantity": quantity}],
        )
        response = self.client.create_transaction(data=transaction_data)
        response_dict = self._response_to_dict(response)
        
        # Response is {meta: {...}, data: {...}} - extract the data
        if 'data' in response_dict:
            return response_dict['data']
        return response_dict
    
    async def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Get subscription details."""
        response = self.client.get_subscription(subscription_id)
        return self._response_to_dict(response)
    
    async def update_subscription(
        self,
        subscription_id: str,
        items: Optional[list] = None,
        proration_billing_mode: str = "prorated_immediately",
        scheduled_change: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update a subscription with new items/prices.
        
        Args:
            subscription_id: Paddle subscription ID
            items: List of subscription items with price_id and quantity.
                   Pass full list of items you want subscription to have.
                   To remove an item, don't include it in the list.
                   Example: [{"price_id": "pri_01...", "quantity": 1}]
            proration_billing_mode: How to bill for proration:
                - "prorated_immediately" (default): Bill prorated amount immediately
                - "prorated_next_billing_period": Add prorated amount to next bill
                - "full_immediately": Bill full amount immediately
                - "full_next_billing_period": Add full amount to next bill
                - "do_not_bill": Don't bill for changes
            scheduled_change: Schedule change for later. Dict with:
                - "action": "pause", "cancel", or "resume"
                - "effective_at": ISO timestamp when to apply
            **kwargs: Additional parameters supported by Paddle API
        
        Returns:
            Updated subscription data
        
        Reference: https://developer.paddle.com/api-reference/subscriptions/update-subscription
        """
        update_params = {}
        
        if items is not None:
            update_params["items"] = items
        
        if proration_billing_mode:
            update_params["proration_billing_mode"] = proration_billing_mode
        
        if scheduled_change:
            update_params["scheduled_change"] = scheduled_change
        
        # Merge any additional kwargs
        update_params.update(kwargs)
        
        from paddle_billing_client.models.subscription import SubscriptionRequest, Item
        
        # Convert items list to Item objects if needed
        if 'items' in update_params:
            update_params['items'] = [
                Item(price_id=item.get('price_id'), quantity=item.get('quantity', 1))
                for item in update_params['items']
            ]
        
        subscription_data = SubscriptionRequest(**update_params)
        response = self.client.update_subscription(subscription_id, data=subscription_data)
        return self._response_to_dict(response)
    
    async def add_subscription_items(
        self,
        subscription_id: str,
        new_items: list,
        proration_billing_mode: str = "prorated_immediately"
    ) -> Dict[str, Any]:
        """
        Add items (prices/addons) to an existing subscription.
        
        Args:
            subscription_id: Paddle subscription ID
            new_items: List of items to add: [{"price_id": "pri_01...", "quantity": 1}]
            proration_billing_mode: How to bill for added items
        
        Returns:
            Updated subscription data
        
        Note: This fetches current items, merges with new items, and updates.
        For better performance, call update_subscription() directly with full items list.
        """
        # Get current subscription to retrieve existing items
        current_sub = await self.get_subscription(subscription_id)
        existing_items = current_sub.get("items", [])
        
        # Build map of existing items by price_id
        items_map = {}
        for item in existing_items:
            price_id = item.get("price", {}).get("id") if isinstance(item.get("price"), dict) else item.get("price_id")
            if price_id:
                items_map[price_id] = {
                    "price_id": price_id,
                    "quantity": item.get("quantity", 1)
                }
        
        # Add or update with new items
        for new_item in new_items:
            price_id = new_item.get("price_id")
            if price_id:
                if price_id in items_map:
                    # Update quantity (add to existing)
                    items_map[price_id]["quantity"] += new_item.get("quantity", 1)
                else:
                    # Add new item
                    items_map[price_id] = new_item
        
        # Convert back to list
        all_items = list(items_map.values())
        
        return await self.update_subscription(
            subscription_id=subscription_id,
            items=all_items,
            proration_billing_mode=proration_billing_mode
        )
    
    async def remove_subscription_items(
        self,
        subscription_id: str,
        price_ids_to_remove: list,
        proration_billing_mode: str = "prorated_immediately"
    ) -> Dict[str, Any]:
        """
        Remove items (prices/addons) from an existing subscription.
        
        Args:
            subscription_id: Paddle subscription ID
            price_ids_to_remove: List of price IDs to remove: ["pri_01...", "pri_02..."]
            proration_billing_mode: How to bill for removed items
        
        Returns:
            Updated subscription data
        """
        # Get current subscription
        current_sub = await self.get_subscription(subscription_id)
        existing_items = current_sub.get("items", [])
        
        # Filter out items to remove
        remaining_items = []
        for item in existing_items:
            price_id = item.get("price", {}).get("id") if isinstance(item.get("price"), dict) else item.get("price_id")
            if price_id and price_id not in price_ids_to_remove:
                remaining_items.append({
                    "price_id": price_id,
                    "quantity": item.get("quantity", 1)
                })
        
        if not remaining_items:
            raise ValueError("Cannot remove all items from subscription. Consider canceling instead.")
        
        return await self.update_subscription(
            subscription_id=subscription_id,
            items=remaining_items,
            proration_billing_mode=proration_billing_mode
        )
    
    async def cancel_subscription(
        self,
        subscription_id: str,
        effective_from: str = "next_billing_period",
    ) -> Dict[str, Any]:
        """
        Cancel a subscription.
        
        Args:
            subscription_id: Paddle subscription ID
            effective_from: When to cancel:
                - "next_billing_period" (default): Cancel at end of current billing period
                - "immediately": Cancel immediately and stop billing
        
        Returns:
            Canceled subscription data
        
        Reference: https://developer.paddle.com/api-reference/subscriptions/cancel-subscription
        """
        from paddle_billing_client.models.subscription import SubscriptionRequest
        subscription_data = SubscriptionRequest(effective_from=effective_from)
        response = self.client.cancel_subscription(subscription_id, data=subscription_data)
        return self._response_to_dict(response)
    
    async def pause_subscription(
        self,
        subscription_id: str,
        effective_from: str = "next_billing_period",
        resume_at: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Pause a subscription.
        
        Args:
            subscription_id: Paddle subscription ID
            effective_from: When to pause:
                - "next_billing_period" (default): Pause at end of current period
                - "immediately": Pause immediately
            resume_at: ISO timestamp when to automatically resume (optional)
        
        Returns:
            Paused subscription data
        
        Reference: https://developer.paddle.com/api-reference/subscriptions/pause-subscription
        """
        from paddle_billing_client.models.subscription import SubscriptionRequest
        params = {"effective_from": effective_from}
        if resume_at:
            params["resume_at"] = resume_at
        
        subscription_data = SubscriptionRequest(**params)
        response = self.client.pause_subscription(subscription_id, data=subscription_data)
        return self._response_to_dict(response)
    
    async def resume_subscription(
        self,
        subscription_id: str,
        effective_from: str = "immediately"
    ) -> Dict[str, Any]:
        """
        Resume a paused subscription.
        
        Args:
            subscription_id: Paddle subscription ID
            effective_from: When to resume:
                - "immediately" (default): Resume immediately
                - "next_billing_period": Resume at next billing period
        
        Returns:
            Resumed subscription data
        
        Reference: https://developer.paddle.com/api-reference/subscriptions/resume-subscription
        """
        from paddle_billing_client.models.subscription import SubscriptionRequest
        subscription_data = SubscriptionRequest(effective_from=effective_from)
        response = self.client.resume_subscription(subscription_id, data=subscription_data)
        return self._response_to_dict(response)
    
    async def get_prices(self, product_id: Optional[str] = None) -> list:
        """Get available prices."""
        response = self.client.list_prices()
        response_dict = self._response_to_dict(response)
        
        # Paddle API returns {meta: {...}, data: [...]}
        if isinstance(response_dict, dict) and 'data' in response_dict:
            return response_dict['data']
        
        if isinstance(response, list):
            return [self._response_to_dict(p) for p in response]
        return [response_dict] if response_dict else []
    
    def list_prices(self, product_id: Optional[str] = None) -> list:
        """Get available prices (synchronous version)."""
        response = self.client.list_prices()
        response_dict = self._response_to_dict(response)
        
        # Paddle API returns {meta: {...}, data: [...]}
        # We need to extract the data array
        if isinstance(response_dict, dict) and 'data' in response_dict:
            return response_dict['data']
        
        if isinstance(response, list):
            return [self._response_to_dict(p) for p in response]
        return [response_dict] if response_dict else []
    
    async def get_products(self) -> list:
        """Get available products."""
        response = self.client.list_products()
        response_dict = self._response_to_dict(response)
        
        # Paddle API returns {meta: {...}, data: [...]}
        if isinstance(response_dict, dict) and 'data' in response_dict:
            return response_dict['data']
        
        if isinstance(response, list):
            return [self._response_to_dict(p) for p in response]
        return [response_dict] if response_dict else []
    
    async def create_price(
        self,
        product_id: str,
        amount: str,
        currency: str,
        billing_cycle_interval: str,
        billing_cycle_frequency: int = 1,
    ) -> Dict[str, Any]:
        """Create a price for a product."""
        from paddle_billing_client.models.price import PriceRequest, UnitPrice, BillingCycle
        price_data = PriceRequest(
            product_id=product_id,
            unit_price=UnitPrice(amount=amount, currency_code=currency),
            billing_cycle=BillingCycle(
                interval=billing_cycle_interval,
                frequency=billing_cycle_frequency,
            ),
        )
        response = self.client.create_price(data=price_data)
        return self._response_to_dict(response)
    
    async def get_transaction(self, transaction_id: str) -> Dict[str, Any]:
        """Get transaction details."""
        response = self.client.get_transaction(transaction_id)
        return self._response_to_dict(response)

    async def create_transaction_checkout(
        self,
        customer_id: str,
        price_id: str,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """Create a hosted checkout transaction as a fallback to surface checkout_url."""
        from paddle_billing_client.models.transaction import TransactionRequest
        transaction_data = TransactionRequest(
            customer_id=customer_id,
            items=[{"price_id": price_id, "quantity": quantity}],
        )
        response = self.client.create_transaction(data=transaction_data)
        response_dict = self._response_to_dict(response)
        # Response is {meta: {...}, data: {...}} - extract the data
        if 'data' in response_dict:
            return response_dict['data']
        return response_dict

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature_header: str,
        webhook_secret: str,
    ) -> bool:
        """
        Verify Paddle webhook signature.
        
        Paddle sends signature in format: ts=<timestamp>;h1=<hash>
        Signature is calculated as: HMAC-SHA256(secret, "{ts}:{body}")
        """
        import time
        
        # Parse signature header: ts=1234567890;h1=abcdef123456
        parts = {}
        for part in signature_header.split(";"):
            if "=" in part:
                key, value = part.split("=", 1)
                parts[key.strip()] = value.strip()
        
        timestamp = parts.get("ts")
        received_h1 = parts.get("h1")
        
        if not timestamp or not received_h1:
            return False
        
        # Verify timestamp is within 5 minutes (prevent replay attacks)
        try:
            timestamp_int = int(timestamp)
            current_time = int(time.time())
            time_diff = abs(current_time - timestamp_int)
            if time_diff > 300:  # 5 minutes
                return False
        except (ValueError, TypeError):
            return False
        
        # Calculate signature: HMAC-SHA256(secret, "{ts}:{body}")
        secret = webhook_secret.encode()
        message = f"{timestamp}:{payload.decode()}".encode()
        
        calculated_h1 = hmac.new(
            secret,
            message,
            hashlib.sha256,
        ).hexdigest()
        
        # Compare signatures using timing-safe comparison
        return hmac.compare_digest(calculated_h1, received_h1)


# Global Paddle client instance (lazy-initialized)
_paddle_client = None

def get_paddle_client_instance():
    """Get or create Paddle client instance."""
    global _paddle_client
    if _paddle_client is None:
        _paddle_client = PaddleClient()
    return _paddle_client

# For backwards compatibility, expose as lazy property
class LazyPaddleClient:
    def __getattr__(self, name):
        return getattr(get_paddle_client_instance(), name)

paddle_client = LazyPaddleClient()
