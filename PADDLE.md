# Paddle Integration

## Status: ✅ Core Integration Complete

The Paddle billing integration is now functional with configuration validation, checkout flow, webhook security, and comprehensive test coverage.

## Current State
- **Configuration**: Paddle config validated on startup when billing enabled; environment toggles between sandbox/production.
- **Checkout Flow**: `/billing/subscribe` creates Paddle customer+subscription, returns checkout_url for hosted payment; fallback transaction creation when subscription lacks URL.
- **Webhook Security**: HMAC signature verification with timestamp tolerance (5min), idempotency via last_webhook_event_id and last_transaction_id tracking.
- **Data Model**: BillingAccount tracks paddle_customer_id, paddle_subscription_id, next_billing_date, cancelled_at; webhook events update local state.
- **Testing**: Comprehensive test coverage for webhook signature verification, idempotency, billing subscribe flow with Paddle client mocks.

## Implementation Completed

### 1. Configuration & Validation ✅
- Settings: `paddle_billing_enabled`, `paddle_api_key`, `paddle_webhook_secret`, `paddle_environment` (sandbox|production), `paddle_vendor_id`
- Startup validation in [app/main.py](app/main.py#L184-L194): fails fast if required Paddle config missing when billing enabled
- Config loaded in [app/core/config.py](app/core/config.py#L22-L28)

### 2. Data Model & Migrations ✅
- Migration `4a6db2f62ec5`: Added `next_billing_date`, `cancelled_at`, `last_webhook_event_id`, `last_transaction_id` to BillingAccount ([alembic/versions/...62ec5_add_paddle_sync_fields.py](alembic/versions/4a6db2f62ec5_add_paddle_sync_fields.py))
- Indexed `paddle_subscription_id` for webhook lookups
- Nullable paddle IDs support pre-Paddle accounts

### 3. Checkout & Subscribe Flow ✅
- [app/billing/router.py](app/billing/router.py#L170-L253) `/billing/subscribe`:
  - Creates Paddle customer if missing (stores `paddle_customer_id`)
  - Creates Paddle subscription (stores `paddle_subscription_id`, `next_billing_date`)
  - Returns `checkout_url` from subscription response when present
  - Fallback: creates hosted checkout transaction via [PaddleClient.create_transaction_checkout](app/core/paddle.py#L180-L196) when subscription lacks URL
  - Dependency injection via `get_paddle_client()` for test overrides
  - `_as_dict()` helper normalizes Paddle SDK objects and test fakes to uniform dict access
- Paddle client wrapper: [app/core/paddle.py](app/core/paddle.py) with customer, subscription, transaction operations

### 4. Webhook Security & Handling ✅
- [app/webhooks/router.py](app/webhooks/router.py#L13-L140) `/webhooks/paddle`:
  - HMAC-SHA256 signature verification with timestamp tolerance (5 minutes) ([lines 33-68](app/webhooks/router.py#L33-L68))
  - Idempotency: skips duplicate events via `last_webhook_event_id` check ([lines 91-97](app/webhooks/router.py#L91-L97))
  - Status sync: maps Paddle subscription statuses to local `SubscriptionStatus` enum
  - Updates `next_billing_date`, `cancelled_at`, `last_transaction_id` from webhook payload
- Tests: [tests/test_paddle_webhook.py](tests/test_paddle_webhook.py) covers signature validation, timestamp tolerance, idempotency

### 5. Testing ✅
- Webhook tests: [tests/test_paddle_webhook.py](tests/test_paddle_webhook.py)
  - Signature verification (valid/invalid/expired signatures)
  - Idempotency (duplicate event_id rejection)
  - Status updates from webhook events
- Billing subscribe tests: [tests/test_billing_paddle.py](tests/test_billing_paddle.py)
  - Successful subscription with checkout_url
  - Fallback transaction checkout when subscription lacks URL
  - Missing paddle_price_id validation
  - Subscription creation failure handling
  - Fake Paddle client with SimpleNamespace responses
- All tests passing with in-memory SQLite and dependency overrides

## Remaining Tasks (Optional Enhancements)

### Admin Panel for Paddle Management ✅ **COMPLETED**
Extended [app/admin/router.py](app/admin/router.py) and admin UI with comprehensive Paddle billing management tools:

#### Step 1: Subscription Plans Management ✅
**Backend API** ([app/admin/router.py](app/admin/router.py)):
- `POST /admin/plans/link-paddle` - Link SubscriptionPlan to Paddle Price ID
- `GET /admin/plans/missing-price-ids` - List plans without Paddle Price IDs
- `POST /admin/plans/sync-paddle` - Sync all plans with Paddle (validate prices, update metadata)
- `GET /admin/paddle/validate-config` - Validate Paddle API configuration

**Frontend UI** ([app/templates/admin.html](app/templates/admin.html)):
- Paddle Configuration section with validation status display
- Check Missing Price IDs button with table of plans needing linking
- Link Paddle Price modal for mapping plans to Paddle prices
- Sync All Plans button with progress feedback

#### Step 2: Billing Accounts Dashboard ✅
**Backend API**:
- `GET /admin/subscriptions/filter?status=...` - Filter billing accounts by status
- `GET /admin/subscriptions/{id}/details` - Detailed account view with Paddle API comparison
- `POST /admin/subscriptions/sync-paddle` - Bulk sync all accounts with Paddle
- `GET /admin/subscriptions/drift-detection` - Detect discrepancies between local DB and Paddle

**Frontend UI**:
- Billing Accounts table with filters (status, search)
- View Details modal showing local DB vs Paddle API data side-by-side
- Drift detection with highlighted discrepancies
- Sync All button for bulk reconciliation

#### Step 3: Paddle Sync & Reconciliation ✅
**Backend API**:
- `POST /admin/paddle/reconcile` - Reconcile all subscriptions with Paddle API
- `GET /admin/paddle/billing-status` - Overview of billing status (total active, with/without Paddle IDs)
- `POST /admin/paddle/auto-backfill` - Auto-fill missing paddle_subscription_id from Paddle API

**Frontend UI**:
- Reconciliation section with status overview
- Reconcile Now button with detailed results
- Check Status button for quick overview
- Auto Backfill button for missing Paddle IDs

#### Step 4: Webhook Management Log ✅
**Backend API**:
- `GET /admin/webhooks/events?event_type=...&status=...&limit=50` - List webhook events with filters
- `GET /admin/webhooks/events/{id}` - Detailed webhook event view (payload, signature, processing status)
- `GET /admin/webhooks/stats` - Webhook processing statistics (by status, by type)
- `POST /admin/webhooks/events/{id}/reprocess` - Retry failed webhook processing

**Frontend UI**:
- Webhook Events table with filters (event type, status, limit)
- View Details modal with full payload and processing info
- Retry button for failed events
- Stats dashboard with counts by status and event type

**Database Model** ([app/models/billing.py](app/models/billing.py)):
- New `PaddleWebhookEvent` model tracking all webhook events:
  - `paddle_event_id`, `event_type`, `payload`, `signature_valid`
  - `status` (RECEIVED, PROCESSED, FAILED, SKIPPED)
  - `billing_account_id` (optional FK)
  - `received_at`, `processed_at`, `error_message`
  - Indexes on `paddle_event_id`, `event_type`, `billing_account_id`

#### Step 9: Admin UI Components ✅
**Frontend Implementation** ([app/templates/admin.html](app/templates/admin.html)):
- New "Paddle" tab in admin navigation (7th tab after Plans)
- 5 main sections with comprehensive UI:
  1. **Paddle Configuration** - API key validation, environment display
  2. **Paddle Plans Sync** - missing price IDs check, link modal, sync button
  3. **Billing Accounts Dashboard** - table with filters, details modal, drift detection
  4. **Paddle Reconciliation** - reconcile button, status check, auto-backfill
  5. **Webhook Events Log** - events table with filters, details modal, stats, retry

**JavaScript Functions** (15+ functions):
- `loadPaddleTab()` - orchestrates loading all Paddle data
- `validatePaddleConfig()` - displays config status with color-coded badges
- `checkMissingPriceIds()` - shows plans needing Paddle price linkage
- `showLinkPaddlePriceModal()` / `linkPaddlePrice()` - modal form for linking
- `syncPaddlePlans()` - syncs all plans with confirmation
- `loadBillingAccounts()` - loads accounts table with status filters
- `viewBillingAccountDetails()` - modal with DB vs Paddle comparison
- `detectDrift()` - runs drift detection and displays results
- `syncAllBillingAccounts()` - bulk sync with progress
- `reconcileSubscriptions()` - full reconciliation with details
- `checkBillingStatus()` - quick status overview
- `autoBackfill()` - auto-fills missing Paddle IDs
- `loadWebhookEvents()` - loads events table with filters
- `viewWebhookDetails()` - modal with full payload and metadata
- `reprocessWebhook()` - retries failed event processing
- `loadWebhookStats()` - displays webhook statistics dashboard

**CSS Styling** ([app/static/css/admin.css](app/static/css/admin.css)):
- `.info-box`, `.success-box`, `.warning-box`, `.error-box` - color-coded status boxes
- `.badge`, `.badge-success`, `.badge-error`, `.badge-warning`, `.badge-info` - status badges
- Enhanced `.section-header` with flex layout for multiple action buttons
- `.loading` with animated dots

**Commits**:
- `97c3cc3` - Step 1: Subscription Plans Management API
- `4f29800` - Step 2: Billing Accounts Dashboard API
- `dea98ff` - Step 3: Paddle Sync & Reconciliation
- `92e7dab` - Step 4: Webhook Management Log
- `721aac6` - Step 9: Admin UI Components (frontend)
- `2d1f61b` - CSS styles for Paddle Management UI

### Remaining Tasks (Optional Enhancements)

**Step 5: Admin Actions & Overrides** (Not yet implemented)
- Manual subscription actions via Paddle API:
  - Cancel subscription (immediate or end of billing period)
  - Pause/Resume subscription
  - Update subscription plan (change paddle_price_id)
  - Issue refund for transaction
- Local overrides (emergency use):
  - Manually set subscription status (with audit log)
  - Grant free trial extension
  - Adjust balance (with reason field)
  - Reset free_requests_used counter

**Step 6: Revenue Reports & Analytics** (Not yet implemented)
- Revenue dashboard:
  - MRR (Monthly Recurring Revenue), ARR
  - Revenue by plan, currency conversion
  - Churn rate, retention metrics
- Subscription metrics:
  - Active subscriptions count by plan
  - New subscriptions (daily/weekly/monthly)
  - Cancellations and reasons (if collected)
  - Trial conversion rate
- Charts: time-series graphs for revenue, subscriptions, churn
- Export: CSV/Excel export for billing reports

**Step 7: Configuration Management** (Partially implemented via validate-config endpoint)
- Paddle settings page:
  - Display current config (environment, vendor_id, masked API key) ✅
  - Test connection button: verify Paddle API key validity ✅
  - Webhook secret rotation: generate new secret, update in Paddle dashboard instructions
  - Toggle billing features: enable/disable Paddle integration without code deployment

**Step 8: Audit & Security** (Not yet implemented)
- Audit log for all admin actions: who changed what subscription, when
- Permission checks: require superuser role for sensitive actions (refunds, manual status changes)
- Activity notifications: alert on suspicious patterns (mass cancellations, manual overrides)

### Other Future Enhancements

**Plan/Price Management (CLI Alternative)** (Not yet implemented)
- Admin/CLI script to sync Paddle products/prices into SubscriptionPlan (populate `paddle_price_id`)
- Expose read-only API endpoint for available Paddle prices

**Reconciliation & Background Jobs** (Manual endpoints available, automation not yet implemented)
- Scheduled task to poll Paddle for subscription state changes (past_due, canceled) and sync local BillingAccount
- Backfill job for accounts missing `paddle_subscription_id`

**Frontend Improvements** (Not yet implemented)
- Surface errors when Paddle config absent (disable subscribe buttons or show message in upgrade.html)
- Refine upgrade.html plan title selector for subscribeToPlan lookup

**Monitoring & Observability** (Not yet implemented)
- Structured logs for webhook events with Paddle event_id/subscription_id
- Sentry breadcrumbs for webhook failures and reconciliation
- Metrics for checkout creation success/failure rates

## Usage

### Accessing the Paddle Admin Panel

1. Log in as an admin user
2. Navigate to Admin Panel
3. Click on the "Paddle" tab (7th tab in navigation)
4. Available sections:
   - **Paddle Configuration**: Check API connection status
   - **Paddle Plans Sync**: Link plans to Paddle Price IDs
   - **Billing Accounts**: View and manage customer subscriptions
   - **Paddle Reconciliation**: Sync subscription states with Paddle
   - **Webhook Events Log**: Monitor and debug webhook processing

### Common Admin Tasks

**Linking a Plan to Paddle Price ID:**
1. Go to Paddle tab → Paddle Plans Sync section
2. Click "Check Missing Price IDs"
3. Click "Link" button next to a plan
4. Enter Paddle Price ID (format: pri_01...)
5. Submit

**Checking Subscription Status:**
1. Go to Paddle tab → Billing Accounts section
2. Use status filter or search
3. Click "View" to see detailed account info including Paddle API comparison

**Reconciling Subscriptions:**
1. Go to Paddle tab → Paddle Reconciliation section
2. Click "Reconcile Now" to sync all subscriptions with Paddle
3. View detailed results showing updated/processed/error counts

**Investigating Webhook Issues:**
1. Go to Paddle tab → Webhook Events Log section
2. Filter by event type or status (FAILED, PROCESSED, etc.)
3. Click "View" to see full webhook payload and processing details
4. Click "Retry" on failed events to reprocess

**Detecting Drift:**
1. Go to Paddle tab → Billing Accounts section
2. Click "Detect Drift"
3. Review accounts with discrepancies between local DB and Paddle

## Configuration Example

```env
# Enable Paddle billing integration
PADDLE_BILLING_ENABLED=true

# Paddle API credentials
PADDLE_API_KEY=your_paddle_api_key_here
PADDLE_WEBHOOK_SECRET=your_webhook_secret_here
PADDLE_VENDOR_ID=12345

# Environment: sandbox or production
PADDLE_ENVIRONMENT=sandbox
```

## Verifying Paddle Status

After deployment, check server logs to confirm Paddle is running:

### Expected Logs on Startup

When **Paddle enabled** (`PADDLE_BILLING_ENABLED=true`):
```
INFO - Starting application...
INFO - Paddle billing: ENABLED (environment: sandbox)
INFO - Paddle configuration validated: API key present, webhook secret configured
INFO - Starting Telegram bot...
INFO - Application startup complete.
```

When **Paddle disabled** (`PADDLE_BILLING_ENABLED=false`):
```
INFO - Starting application...
INFO - Paddle billing: DISABLED
INFO - Starting Telegram bot...
INFO - Application startup complete.
```

### Verification Methods

1. **Check Logs**: `journalctl -u bot-generic.service -n 50 | grep -i paddle`
   - Should show "Paddle billing: ENABLED" if configured correctly
   - Should show "Paddle configuration validated" if credentials present

2. **Health Check Endpoint**: `curl https://your-domain.com/health`
   - Returns app status (doesn't include Paddle status yet)

3. **Test Subscribe Endpoint**: 
   ```bash
   curl -X POST https://your-domain.com/billing/subscribe \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"plan_id": 1}'
   ```
   - Should return `checkout_url` if Paddle enabled and configured
   - Should return 502 error if Paddle enabled but credentials invalid

4. **Check Environment Variable**: `systemctl show bot-generic.service -p Environment`
   - Verify `PADDLE_BILLING_ENABLED=true` is set

### Troubleshooting

**"Paddle billing: DISABLED" when it should be enabled:**
- Check `.env` file has `PADDLE_BILLING_ENABLED=true`
- Restart service: `sudo systemctl restart bot-generic.service`
- Verify environment loaded: service file must use `EnvironmentFile=/path/to/.env`

**"Paddle billing enabled but missing settings" error:**
- Ensure `PADDLE_API_KEY` is set in `.env`
- Ensure `PADDLE_WEBHOOK_SECRET` is set in `.env`
- Both values must be non-empty strings

**No Paddle logs at all:**
- Check log level: ensure `LOG_LEVEL=INFO` (not `ERROR` or `WARNING`)
- View full startup sequence: `journalctl -u bot-generic.service --since "5 minutes ago"`

## Deployment Safety ✅

**Current state is SAFE to deploy** with the following guarantees:

### Backward Compatibility
- **Default behavior**: `PADDLE_BILLING_ENABLED=false` by default - existing users unaffected
- **Graceful degradation**: If Paddle disabled, `/billing/subscribe` still works (sets local subscription state only, no Paddle calls)
- **Database migration**: Adds nullable Paddle fields to `billing_accounts` table - existing records remain valid with NULL values
- **No breaking changes**: All existing billing endpoints maintain backward compatibility

### Safety Mechanisms
1. **Startup validation**: App fails fast if `PADDLE_BILLING_ENABLED=true` but credentials missing - prevents silent failures
2. **Webhook security**: HMAC signature verification prevents unauthorized webhook processing
3. **Idempotency**: Duplicate webhook events safely ignored via `last_webhook_event_id` tracking
4. **Error handling**: Paddle API failures return HTTP 502 with clear error messages, don't crash app
5. **Transaction safety**: All database operations in subscribe flow wrapped in transaction (commit/rollback)

### Migration Checklist
Before enabling Paddle in production:

- [ ] **Run migrations**: `alembic upgrade head` to add Paddle fields
- [ ] **Set environment variables**:
  - `PADDLE_BILLING_ENABLED=false` initially (test with disabled state first)
  - `PADDLE_API_KEY` - from Paddle dashboard
  - `PADDLE_WEBHOOK_SECRET` - from Paddle webhook settings
  - `PADDLE_ENVIRONMENT=sandbox` for staging, `production` for prod
  - `PADDLE_VENDOR_ID` (optional)
- [ ] **Test with Paddle disabled**: Verify existing billing flows work unchanged
- [ ] **Configure Paddle webhook**: Add webhook endpoint URL in Paddle dashboard: `https://your-domain.com/webhooks/paddle`
- [ ] **Populate paddle_price_id**: Link your `subscription_plans` to Paddle prices (via admin panel or SQL update)
- [ ] **Enable gradually**: Set `PADDLE_BILLING_ENABLED=true` on staging first, monitor logs
- [ ] **Test full flow**: Create test subscription in Paddle sandbox, verify webhook processing
- [ ] **Monitor**: Watch for Paddle API errors, webhook failures, subscription sync issues

### Rollback Plan
If issues occur after enabling Paddle:
1. Set `PADDLE_BILLING_ENABLED=false` in environment - immediate rollback to legacy behavior
2. No database rollback needed - Paddle fields nullable, don't affect existing queries
3. Paddle subscriptions continue billing (managed in Paddle dashboard), can sync later

### Known Limitations
- **Manual plan setup**: Must manually populate `paddle_price_id` for plans before enabling (admin panel tools pending)
- **No automatic reconciliation**: Subscription status drift requires manual sync via admin panel (background job pending)
- **Webhook replay**: Failed webhooks must be manually reprocessed via admin panel (automatic retry pending)

## Testing Locally

1. Set `PADDLE_BILLING_ENABLED=false` to disable Paddle integration during development
2. Run tests: `pytest tests/test_paddle_webhook.py tests/test_billing_paddle.py`
3. For integration testing with Paddle sandbox:
   - Set credentials for sandbox environment
   - Use webhook testing tools (Paddle webhook tester or ngrok) to forward events to local server
   - Verify signature validation and idempotency behavior

## Architecture Notes

- **Dependency Injection**: `get_paddle_client()` in billing router allows test overrides via `app.dependency_overrides`
- **Response Normalization**: `_as_dict()` helper handles both real Paddle SDK objects (with `.dict()`) and test fakes (SimpleNamespace, dict)
- **Idempotency Strategy**: Event-level via `last_webhook_event_id`; transaction-level via `last_transaction_id` for payment events
- **Security**: HMAC verification prevents replay attacks; timestamp tolerance (5min) prevents old event injection
