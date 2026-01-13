# Paddle Webhook Signature Verification Fix

## Problem Statement

The Paddle webhook handler was failing with `400 Bad Request: Missing webhook signature` error when receiving real Paddle events from production. This was blocking all webhook-based subscription and transaction updates.

### Root Cause

The webhook handler was looking for signature and timestamp in **separate HTTP headers**:
- `paddle-signature` header
- `paddle-timestamp` header (separate)

But Paddle's actual API sends **both values in a single header** named `Paddle-Signature` with format:
```
Paddle-Signature: ts=<timestamp>;h1=<hash>
```

## Solution Implemented

### 1. Fixed Signature Verification Logic

**File: `app/core/paddle.py`**

Updated `verify_webhook_signature()` method to:
- Parse `Paddle-Signature` header value
- Extract `ts=` (timestamp) and `h1=` (hash) components
- Verify timestamp is within 5-minute window (replay attack prevention)
- Calculate HMAC-SHA256 signature using format: `"{timestamp}:{raw_body}"`
- Compare calculated hash with received `h1` value

```python
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
```

### 2. Recreated Webhook Handler

**File: `app/webhooks/router.py`**

Complete rewrite of webhook handler with:
- Correct signature header parsing
- Proper event type handling (`event_type` field)
- Event filtering (ignored: `product.*`, `price.*`, `customer.*`)
- Subscription status mapping
- Transaction tracking
- Idempotency via `event_id`

Key event handlers:
- `subscription.created` → Create subscription record
- `subscription.updated` → Update status and billing date
- `subscription.cancelled` → Mark as cancelled
- `subscription.paused` → Map to ACTIVE status
- `subscription.resumed` → Map to ACTIVE status
- `transaction.completed` → Record transaction
- `transaction.failed` → Log failure

### 3. Updated Test Suite

**File: `tests/test_paddle_webhook.py`**

- Updated `_sign_payload()` helper to create correct signature format: `ts=...;h1=...`
- Changed all test payloads from `type` field to `event_type` field
- Updated header name from `paddle-signature` to `Paddle-Signature` (case-sensitive)
- Removed separate `paddle-timestamp` header
- All 12 webhook tests now passing

### 4. Technical Implementation Details

#### Signature Format
```
Header: Paddle-Signature
Value: ts=1710498758;h1=558bf93944dbeb4790c7a8af6cb2ea435c8ca9c8396aafc1a4e37424ac132744
```

#### Signature Calculation
```python
timestamp = "1710498758"  # Extracted from header
body = raw_request_body
secret = PADDLE_WEBHOOK_SECRET

signature_string = f"{timestamp}:{body}"
calculated_hash = HMAC-SHA256(secret, signature_string.encode()).hexdigest()
is_valid = (calculated_hash == received_h1)
```

#### Timestamp Validation
- Timestamp must be within 300 seconds (5 minutes) of current time
- Prevents replay attacks with old signatures
- Handles clock skew gracefully

## Testing Results

### Webhook Tests
✅ All 12 paddle webhook tests passing:
- `test_paddle_webhook_subscription_created`
- `test_paddle_webhook_subscription_updated`
- `test_paddle_webhook_subscription_cancelled`
- `test_paddle_webhook_subscription_paused`
- `test_paddle_webhook_subscription_resumed`
- `test_paddle_webhook_transaction_completed`
- `test_paddle_webhook_transaction_failed`
- `test_paddle_webhook_invalid_json`
- `test_paddle_webhook_unknown_event`
- `test_paddle_webhook_signature_valid`
- `test_paddle_webhook_signature_invalid`
- `test_paddle_webhook_idempotent_event`

### Billing Tests
✅ All 4 paddle billing tests passing:
- `test_create_paddle_customer`
- `test_create_paddle_subscription`
- `test_list_paddle_prices`
- `test_get_paddle_transaction`

**Total: 16/16 Paddle tests passing ✅**

## Deployment Instructions

1. **Pull the latest code**
   ```bash
   git pull origin main
   ```

2. **Verify no new dependencies needed**
   - No new packages required
   - Uses existing: `hmac`, `hashlib`, `time` from stdlib

3. **Restart application**
   ```bash
   systemctl restart bot-generic
   ```

4. **Verify Paddle status**
   ```bash
   tail -f /var/log/bot-generic/app.log | grep "Paddle billing"
   ```

5. **Test webhook locally (optional)**
   ```bash
   curl -X POST http://localhost:8000/webhooks/paddle \
     -H "Content-Type: application/json" \
     -H "Paddle-Signature: ts=1234567890;h1=..." \
     -d '{"event_type":"subscription.created","data":{...}}'
   ```

## Backward Compatibility

✅ **Fully backward compatible**
- PADDLE_BILLING_ENABLED env var still works
- LazyPaddleClient prevents import errors
- Settings validation unchanged
- No database migrations needed
- No breaking API changes

## Database Schema

No changes needed. Existing fields in `BillingAccount` model support all webhook events:
- `paddle_subscription_id`
- `paddle_customer_id`
- `subscription_status`
- `last_webhook_event_id` (for idempotency)
- `next_billing_date`
- `cancelled_at`
- `last_transaction_id`

## Security Considerations

1. **Signature Verification**: Mandatory for all webhook requests (except when PADDLE_BILLING_ENABLED=false)
2. **Timestamp Validation**: Prevents replay attacks (5-minute window)
3. **Timing-Safe Comparison**: Uses `hmac.compare_digest()` to prevent timing attacks
4. **Webhook Secret**: Must be stored in `PADDLE_WEBHOOK_SECRET` env var
5. **HTTP-Only**: Webhooks only accepted over HTTPS in production

## Paddle Documentation References

- Paddle Billing API: https://developer.paddle.com/build/reference/api
- Webhook Events: https://developer.paddle.com/build/reference/webhook-events
- Signature Verification: https://developer.paddle.com/build/webhooks/verify-signatures

## Monitoring

### Logs to Watch
```bash
# Paddle status on startup
"Paddle billing: ENABLED (environment: sandbox)"

# Webhook events received
"Received Paddle webhook: subscription.created event_id=..."

# Signature verification failures
"Paddle signature verification failed"

# Event processing
"Updated subscription: sub_123 -> active"
```

### Metrics to Track
- Webhook success rate (200 responses)
- Signature verification failures (400 errors)
- Event processing latency
- Subscription status update frequency

## Rollback Plan

If issues occur in production:

1. **Immediate**: Revert to previous commit
   ```bash
   git revert HEAD
   systemctl restart bot-generic
   ```

2. **Disable webhooks**: Set `PADDLE_BILLING_ENABLED=false` to disable all Paddle features

3. **Check logs**: Review application logs for specific errors
   ```bash
   tail -100 /var/log/bot-generic/app.log
   ```

## Future Improvements

1. Add webhook rate limiting
2. Add webhook retry logic for failed events
3. Add webhook event logging to database for audit trail
4. Add admin dashboard for webhook event history
5. Add metrics/monitoring for webhook processing

## Commit Information

- **Commit Hash**: 4bf6cd8
- **Message**: "fix: implement correct Paddle webhook signature verification"
- **Files Changed**: 4
  - `app/core/paddle.py`
  - `app/webhooks/router.py`
  - `tests/test_paddle_webhook.py`
  - `tests/conftest.py`

---

**Status**: ✅ READY FOR PRODUCTION

All tests passing. Webhook signature verification working correctly. Ready for deployment.
