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
        """Create a Paddle customer."""
        response = self.client.create_customer(email=email, name=name or email)
        return self._response_to_dict(response)
    
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
        """Create a subscription for a customer."""
        response = self.client.create_subscription(
            customer_id=customer_id,
            items=[{"price_id": price_id, "quantity": quantity}],
        )
        return self._response_to_dict(response)
    
    async def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Get subscription details."""
        response = self.client.get_subscription(subscription_id)
        return self._response_to_dict(response)
    
    async def update_subscription(
        self,
        subscription_id: str,
        price_id: Optional[str] = None,
        quantity: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Update a subscription."""
        items = None
        if price_id:
            items = [{"price_id": price_id, "quantity": quantity or 1}]
        
        response = self.client.update_subscription(subscription_id, items=items)
        return self._response_to_dict(response)
    
    async def cancel_subscription(
        self,
        subscription_id: str,
        effective_from: str = "next_billing_period",
    ) -> Dict[str, Any]:
        """Cancel a subscription."""
        response = self.client.cancel_subscription(subscription_id)
        return self._response_to_dict(response)
    
    async def pause_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Pause a subscription."""
        response = self.client.pause_subscription(subscription_id)
        return self._response_to_dict(response)
    
    async def resume_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Resume a paused subscription."""
        response = self.client.resume_subscription(subscription_id)
        return self._response_to_dict(response)
    
    async def get_prices(self, product_id: Optional[str] = None) -> list:
        """Get available prices."""
        response = self.client.list_prices()
        
        if isinstance(response, list):
            return [self._response_to_dict(p) for p in response]
        return [self._response_to_dict(response)]
    
    async def get_products(self) -> list:
        """Get available products."""
        response = self.client.list_products()
        
        if isinstance(response, list):
            return [self._response_to_dict(p) for p in response]
        return [self._response_to_dict(response)]
    
    async def create_price(
        self,
        product_id: str,
        amount: str,
        currency: str,
        billing_cycle_interval: str,
        billing_cycle_frequency: int = 1,
    ) -> Dict[str, Any]:
        """Create a price for a product."""
        response = self.client.create_price(
            product_id=product_id,
            unit_price={"amount": amount, "currency_code": currency},
            billing_cycle={
                "interval": billing_cycle_interval,
                "frequency": billing_cycle_frequency,
            },
        )
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
        response = self.client.create_transaction(
            customer_id=customer_id,
            items=[{"price_id": price_id, "quantity": quantity}],
        )
        return self._response_to_dict(response)

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
