# Paddle Sandbox Testing Guide - Admin Panel

## Overview

The Admin Panel now includes a **Paddle Subscription Management (Sandbox)** section for testing Paddle API operations directly from the web interface.

**Location:** Admin Panel → Paddle Tab → Bottom section "🧪 Paddle Subscription Management (Sandbox)"

## Features

### Supported Operations

1. **View Current Items** - See all items (prices/products) in a subscription
2. **Add Items** - Add addons or additional prices to subscription
3. **Remove Items** - Remove specific prices from subscription
4. **Replace Items** - Replace all subscription items at once (upgrade/downgrade)
5. **Pause Subscription** - Pause billing with optional auto-resume
6. **Resume Subscription** - Resume a paused subscription
7. **Cancel Subscription** - Cancel subscription (immediate or at period end)

### Proration Modes

All item operations support Paddle's proration billing modes:

- **Prorated Immediately** (default) - Calculate prorated amount and charge/credit immediately
- **Prorated Next Period** - Add prorated amount to next billing period
- **Full Immediately** - Charge full amount immediately
- **Full Next Period** - Add full amount to next billing period
- **Do Not Bill** - Don't bill for changes (complimentary upgrades)

## How to Use

### 1. Access the Panel

1. Log in as admin
2. Navigate to **Paddle** tab
3. Scroll to **"🧪 Paddle Subscription Management (Sandbox)"** section
4. The section will auto-load accounts with Paddle subscriptions

### 2. Select a Billing Account

- Use the dropdown to select a billing account
- Only accounts with `paddle_subscription_id` are shown
- Format: `Organization Name (status) - sub_01abc...`

### 3. View Current Subscription Items

- Current items load automatically when account is selected
- Shows:
  - Price ID
  - Product name
  - Quantity
  - Status
  - Subscription status
  - Next billing date

### 4. Perform Operations

Click the operation button you want to test:

#### ➕ Add Items

**Use Case:** Add addon to existing subscription (e.g., extra storage, premium support)

**Example:**
```
Price IDs: pri_01abc123,pri_02def456
Proration: Prorated Immediately
```

**What happens:**
- Fetches current items from Paddle
- Adds new items to the list
- Updates subscription via Paddle API
- Customer is charged prorated amount for remaining billing period

#### ➖ Remove Items

**Use Case:** Remove addon or downgrade by removing features

**Example:**
```
Price IDs to Remove: pri_01abc123
Proration: Prorated Next Period
```

**What happens:**
- Fetches current items
- Removes specified price IDs
- Updates subscription
- Credit applied to next billing period
- ⚠️ At least one item must remain (cannot remove all items)

#### 🔄 Replace Items

**Use Case:** Complete plan change (upgrade from Basic to Pro)

**Example:**
```
New Price IDs: pri_pro_monthly_123
Proration: Prorated Immediately
```

**What happens:**
- **Replaces ALL current items** with new items
- Good for plan upgrades/downgrades
- Charges difference immediately

#### ⏸️ Pause Subscription

**Use Case:** Temporarily stop billing (e.g., customer vacation)

**Options:**
- **Effective From:** 
  - Next Billing Period (default) - Pause after current period ends
  - Immediately - Pause now
- **Auto Resume At:** Optional ISO timestamp for automatic resume

**Example:**
```
Effective From: Next Billing Period
Auto Resume At: 2026-03-01T00:00:00 (optional)
```

#### ▶️ Resume Subscription

**Use Case:** Resume a paused subscription

**Options:**
- **Effective From:**
  - Immediately (default) - Resume now
  - Next Billing Period - Resume at next period start

#### ❌ Cancel Subscription

**Use Case:** Cancel customer subscription

**Options:**
- **Effective From:**
  - Next Billing Period - Access continues until period ends
  - Immediately - Access stops now, subscription canceled

**⚠️ Warning:** This action cannot be undone!

## Testing Scenarios

### Scenario 1: Add Premium Support Addon

1. Select subscription with base plan
2. Click **➕ Add Items**
3. Enter: `pri_support_addon_01abc`
4. Select: **Prorated Immediately**
5. Click **Add Items**
6. Result: Customer charged ~$2.50 for 15 days of $5/month addon

### Scenario 2: Upgrade from Basic to Pro

1. Select subscription with Basic plan (`pri_basic_01abc`)
2. Click **🔄 Replace Items**
3. Enter: `pri_pro_01xyz`
4. Select: **Prorated Immediately**
5. Click **Replace Items**
6. Result: All items replaced, customer charged upgrade difference

### Scenario 3: Temporary Pause with Auto-Resume

1. Select active subscription
2. Click **⏸️ Pause**
3. Select: **Next Billing Period**
4. Set Resume At: `2026-02-15T00:00:00`
5. Click **Pause Subscription**
6. Result: Subscription pauses after current period, auto-resumes on Feb 15

### Scenario 4: Downgrade at Period End

1. Select subscription with Pro plan
2. Click **🔄 Replace Items**
3. Enter: `pri_basic_01abc` (basic plan)
4. Select: **Prorated Next Billing Period**
5. Click **Replace Items**
6. Result: Change scheduled for next billing, credit applied

## API Endpoints Used

The UI calls these admin API endpoints:

- `GET /admin/subscriptions` - List billing accounts
- `GET /admin/subscriptions/{id}/paddle/items` - Get current items
- `POST /admin/subscriptions/{id}/paddle/add-items` - Add items
- `POST /admin/subscriptions/{id}/paddle/remove-items` - Remove items
- `POST /admin/subscriptions/{id}/paddle/update-items` - Replace items
- `POST /admin/subscriptions/{id}/paddle/pause` - Pause subscription
- `POST /admin/subscriptions/{id}/paddle/resume` - Resume subscription
- `POST /admin/subscriptions/{id}/paddle/cancel` - Cancel subscription

## Backend Implementation

See:
- [app/admin/router.py](app/admin/router.py) - API endpoints (lines 1630-2070)
- [app/core/paddle.py](app/core/paddle.py) - PaddleClient methods
- [PADDLE_SUBSCRIPTION_MANAGEMENT.md](PADDLE_SUBSCRIPTION_MANAGEMENT.md) - Detailed API guide

## Troubleshooting

### "No accounts with Paddle subscriptions found"

**Solution:** 
1. Create a subscription via `/billing/subscribe` endpoint
2. Or manually set `paddle_subscription_id` on a BillingAccount
3. Click **🔄 Refresh List**

### "Failed to add items: Invalid price ID"

**Solution:**
- Verify price ID exists in Paddle dashboard
- Check it's active and not archived
- Ensure format is correct: `pri_01abc...`

### "Cannot remove all items from subscription"

**Solution:**
- Subscriptions must have at least one item
- To remove last item, use **Cancel** instead

### "Failed to update subscription in Paddle: 401"

**Solution:**
- Check Paddle API key is configured correctly
- Verify it has required permissions
- Test with **Validate Config** button

### Items not updating after operation

**Solution:**
- Click **🔄 Refresh Items** button
- Webhook may not have fired yet
- Check Paddle dashboard for subscription state

## Sandbox vs Production

**Current Environment:** Check at top of Paddle tab (Sandbox/Production)

**Sandbox Testing:**
- Use test price IDs from Paddle sandbox
- No real charges
- Test webhooks with ngrok/test URLs

**Production:**
- ⚠️ All operations affect real subscriptions
- Real billing changes
- Use with extreme caution

## Related Documentation

- [PADDLE_SUBSCRIPTION_MANAGEMENT.md](PADDLE_SUBSCRIPTION_MANAGEMENT.md) - Comprehensive API guide
- [PADDLE_API_COMPLIANCE.md](PADDLE_API_COMPLIANCE.md) - API compliance report
- [PADDLE.md](PADDLE.md) - Overall Paddle integration docs

## Support

For issues or questions:
1. Check server logs for detailed error messages
2. Verify Paddle dashboard shows expected state
3. Review [Paddle API docs](https://developer.paddle.com/api-reference/subscriptions/update-subscription)
4. Check webhook events log in admin panel

---

**Last Updated:** January 15, 2026
