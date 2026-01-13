# Paddle Integration Plan

## Current State
- Paddle SDK wrapper exists in app/core/paddle.py and loads keys/env but is not wired into API flows.
- Billing endpoints in app/billing/router.py only toggle local subscription state; they do not call Paddle, create customers, or return checkout URLs (front-end expects checkout_url from subscribeToPlan()).
- Webhook handler in app/webhooks/router.py processes basic events but skips signature verification, idempotency, and assumes DB fields (next_billing_date, cancelled_at) that are not in BillingAccount.
- BillingAccount and SubscriptionPlan models already have paddle_* ID fields, and tests cover a minimal happy-path webhook flow (tests/test_paddle_webhook.py).
- Upgrade page renders plans and redirects to a checkout_url if provided, but no backend path currently issues Paddle checkout links.

## Gaps / Missing Pieces
1) Checkout + subscription creation: no API that creates Paddle customers/subscriptions or ties plan->paddle_price_id, so users never reach Paddle checkout.
2) Webhook security: signatures (paddle_webhook_secret) are not verified; no timestamp tolerance or idempotency store to avoid double-processing.
3) Data model mismatch: webhook handler references next_billing_date/cancelled_at fields that do not exist; no storage for webhook event IDs or invoice/transaction IDs.
4) Status sync: paused/resumed mapped to ACTIVE without nuance; no periodic reconciliation with Paddle to fix drift (e.g., past_due, canceled on Paddle but ACTIVE locally).
5) Plan/price management: no tooling to create/read Paddle products/prices and populate paddle_price_id/paddle_product_id for plans; seeds/migrations do not set them.
6) Frontend contract: subscribe endpoint never returns checkout_url; no error surfaced when Paddle config is missing; upgrade page plan name lookup uses <h3> that does not exist (minor bug).
7) Tests: no coverage for signature verification failure, idempotency, checkout creation path, or status reconciliation.

## Implementation Plan
1) Configuration hardening
   - Require paddle_api_key, paddle_webhook_secret, paddle_environment in settings; fail fast on startup if missing when billing is enabled.
   - Env vars: paddle_billing_enabled (bool, defaults false), paddle_api_key, paddle_webhook_secret, paddle_environment (sandbox|production), paddle_vendor_id (optional for vendor features).
   - Document sandbox vs production toggles and expected host URLs for checkout links.

2) Data model + migrations
   - DONE: Added BillingAccount fields next_billing_date, cancelled_at, last_webhook_event_id, last_transaction_id with migration 4a6db2f62ec5.
   - Consider nullable paddle_customer_id uniqueness scope (unique per vendor) and index paddle_subscription_id for faster lookup.
   - Update __repr__/schema comments if needed.

3) Checkout/subscribe flow
   - Introduce backend endpoint (e.g., POST /billing/checkout or extend /billing/subscribe) that:
     a) Validates plan and its paddle_price_id.
     b) Creates/gets Paddle customer for current user/org and stores paddle_customer_id.
     c) Creates subscription via Paddle (or creates a hosted checkout link if using "Transactions" checkout) and stores paddle_subscription_id, subscription_plan_id, trial dates.
     d) Returns checkout_url (hosted link) to the frontend; handle sandbox vs production URLs.
   - Wire app/core/paddle.PaddleClient into this flow; add dependency injection for testing.

4) Webhook verification + handling
   - Verify HMAC signatures using paddle_webhook_secret (timestamp + payload) and enforce a max age window.
   - Reject if event_id already processed (use last_webhook_event_id or separate table) to ensure idempotency.
   - Align status mapping: paused -> PAUSED (new enum) or keep ACTIVE with a flag; map past_due, expired consistently.
   - Persist next_billing_date/cancelled_at when provided; update balance/total_spent with decimal safety.
   - Handle missing account gracefully but log/alert; optionally enqueue manual review.

5) Plan/price management tooling
   - Add admin/CLI script to sync Paddle products/prices into SubscriptionPlan (populate paddle_price_id/product_id).
   - Optionally expose read-only endpoints for available Paddle prices for debugging.

6) Reconciliation + background jobs
   - Scheduled task to poll Paddle for subscriptions that changed (past_due, canceled) and patch local BillingAccount.
   - Backfill job to fetch subscription state for accounts missing paddle_subscription_id.

7) Frontend contract fixes
   - Adjust upgrade.html plan title selector or DOM to match subscribeToPlan lookup.
   - Surface errors when Paddle config is absent; disable subscribe buttons or show message in upgrade.html.

8) Testing
   - Add tests for signature verification (valid/invalid), idempotency, checkout endpoint (mock Paddle client), and reconciliation job.
   - Expand webhook tests to cover amount parsing, status mappings, and missing account scenarios.

9) Monitoring & logging
   - Structured logs for webhook events and checkout creation; include Paddle event_id/subscription_id.
   - Add Sentry breadcrumbs for webhook failures and reconciliation results.
