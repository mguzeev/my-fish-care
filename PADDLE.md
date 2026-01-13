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

### Admin Panel for Paddle Management
Extend [app/admin/router.py](app/admin/router.py) and admin UI to provide comprehensive Paddle billing management tools:

**Subscription Plans Management**
- CRUD interface for SubscriptionPlan: create/edit plans with name, price, limits, currency
- Paddle integration: sync available Paddle products/prices via API, link plan to `paddle_price_id` via dropdown
- Bulk operations: import multiple plans from Paddle, archive unused plans
- Validation: warn if paddle_price_id missing for plans, show Paddle price details (billing cycle, currency)

**Billing Accounts Dashboard**
- List all BillingAccounts with filters: status (active/canceled/trialing), plan, organization
- Account details view:
  - User/organization info, current plan, subscription status
  - Paddle IDs: customer_id, subscription_id, transaction history
  - Dates: subscription_start, next_billing_date, cancelled_at, trial_started_at
  - Usage stats: free_requests_used, total_spent, balance
- Search by email, organization name, Paddle customer_id/subscription_id

**Paddle Sync & Reconciliation**
- Manual sync button: pull current subscription state from Paddle API for selected account(s)
- Bulk reconciliation: scan all accounts with paddle_subscription_id, detect drift (local ACTIVE but Paddle canceled)
- Sync Products/Prices: fetch all Paddle products and prices, show mapping status, auto-create missing SubscriptionPlans
- Status indicators: last_sync_time, sync_status (success/failed/pending)

**Webhook Management**
- Webhook events log: display recent webhooks with event_id, type, subscription_id, timestamp, processing status
- Event details modal: full payload, signature verification result, changes applied to BillingAccount
- Re-process failed events: button to retry webhook processing for specific event_id
- Idempotency check: show duplicate events that were skipped

**Actions & Overrides**
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

**Reporting & Analytics**
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

**Configuration Management**
- Paddle settings page:
  - Display current config (environment, vendor_id, masked API key)
  - Test connection button: verify Paddle API key validity
  - Webhook secret rotation: generate new secret, update in Paddle dashboard instructions
  - Toggle billing features: enable/disable Paddle integration without code deployment

**Audit & Security**
- Audit log for all admin actions: who changed what subscription, when
- Permission checks: require superuser role for sensitive actions (refunds, manual status changes)
- Activity notifications: alert on suspicious patterns (mass cancellations, manual overrides)

**UI/UX Considerations**
- Extend existing admin panel HTML/CSS ([app/templates/admin.html](app/templates/admin.html), [app/static/css/admin.css](app/static/css/admin.css))
- Use DataTables or similar for sortable/filterable lists
- Add tabbed interface: Plans | Accounts | Webhooks | Reports | Settings
- Status badges: color-coded for subscription statuses (green=active, red=canceled, yellow=trialing)
- Real-time updates: WebSocket or polling for webhook events dashboard

**Technical Implementation**
- New API endpoints in [app/admin/router.py](app/admin/router.py):
  - `GET /admin/billing/plans` - list subscription plans with Paddle sync status
  - `POST /admin/billing/plans/{id}/sync-paddle` - link plan to Paddle price
  - `GET /admin/billing/accounts` - list accounts with filters
  - `GET /admin/billing/accounts/{id}` - detailed account view
  - `POST /admin/billing/accounts/{id}/sync` - fetch current state from Paddle
  - `POST /admin/billing/accounts/{id}/cancel` - cancel subscription via Paddle
  - `GET /admin/billing/webhooks` - webhook events log
  - `POST /admin/billing/webhooks/{id}/reprocess` - retry failed webhook
  - `GET /admin/billing/products/sync` - sync Paddle products/prices
  - `GET /admin/billing/reports/revenue` - revenue analytics
- Background jobs (optional): periodic reconciliation cron, webhook cleanup (archive old events)
- Permissions: extend [app/auth/dependencies.py](app/auth/dependencies.py) with `get_admin_user` dependency for all admin endpoints

### Plan/Price Management (CLI Alternative)
- Admin/CLI script to sync Paddle products/prices into SubscriptionPlan (populate `paddle_price_id`)
- Expose read-only API endpoint for available Paddle prices

### Reconciliation & Background Jobs
- Scheduled task to poll Paddle for subscription state changes (past_due, canceled) and sync local BillingAccount
- Backfill job for accounts missing `paddle_subscription_id`

### Frontend Improvements
- Surface errors when Paddle config absent (disable subscribe buttons or show message in upgrade.html)
- Refine upgrade.html plan title selector for subscribeToPlan lookup

### Monitoring & Observability
- Structured logs for webhook events with Paddle event_id/subscription_id
- Sentry breadcrumbs for webhook failures and reconciliation
- Metrics for checkout creation success/failure rates

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
