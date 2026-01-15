# Paddle Subscription Management Guide

This document describes how to work with Paddle subscriptions following the official API documentation:
https://developer.paddle.com/build/subscriptions/add-remove-products-prices-addons

## Overview

The implementation in [app/core/paddle.py](app/core/paddle.py) provides methods for managing subscription items (prices, products, addons) with proper support for:
- Adding/removing items
- Proration modes
- Scheduled changes
- Immediate vs next billing period updates

## Core Methods

### Update Subscription (Low-level)

```python
await paddle_client.update_subscription(
    subscription_id="sub_01...",
    items=[
        {"price_id": "pri_01...", "quantity": 1},  # Base plan
        {"price_id": "pri_02...", "quantity": 2},  # Addon (2x)
    ],
    proration_billing_mode="prorated_immediately"
)
```

**Parameters:**
- `items`: Full list of items subscription should have (replaces all existing items)
- `proration_billing_mode`:
  - `"prorated_immediately"` (default) - Bill prorated amount now
  - `"prorated_next_billing_period"` - Add prorated amount to next bill
  - `"full_immediately"` - Bill full amount now
  - `"full_next_billing_period"` - Add full amount to next bill
  - `"do_not_bill"` - Don't bill for changes
- `scheduled_change`: Schedule for later (e.g., `{"action": "pause", "effective_at": "2026-02-01T00:00:00Z"}`)

### Add Items (Helper Method)

```python
# Add addon to existing subscription
await paddle_client.add_subscription_items(
    subscription_id="sub_01...",
    new_items=[
        {"price_id": "pri_addon_01...", "quantity": 1}
    ],
    proration_billing_mode="prorated_immediately"
)
```

This method:
1. Fetches current subscription items
2. Merges with new items
3. Calls `update_subscription()` with full list

**Use Case:** Adding addons, upgrading with additional features

### Remove Items (Helper Method)

```python
# Remove addon from subscription
await paddle_client.remove_subscription_items(
    subscription_id="sub_01...",
    price_ids_to_remove=["pri_addon_01..."],
    proration_billing_mode="prorated_immediately"
)
```

This method:
1. Fetches current subscription items
2. Filters out specified price IDs
3. Calls `update_subscription()` with remaining items

**Use Case:** Downgrading, removing addons

**Note:** Cannot remove all items - at least one must remain. Use `cancel_subscription()` instead.

## Subscription Lifecycle

### Cancel Subscription

```python
# Cancel at end of billing period (default)
await paddle_client.cancel_subscription(
    subscription_id="sub_01...",
    effective_from="next_billing_period"
)

# Cancel immediately
await paddle_client.cancel_subscription(
    subscription_id="sub_01...",
    effective_from="immediately"
)
```

**Options:**
- `"next_billing_period"` - Access continues until period ends
- `"immediately"` - Access stops now

### Pause Subscription

```python
# Pause at end of current period
await paddle_client.pause_subscription(
    subscription_id="sub_01...",
    effective_from="next_billing_period"
)

# Pause immediately with auto-resume
await paddle_client.pause_subscription(
    subscription_id="sub_01...",
    effective_from="immediately",
    resume_at="2026-03-01T00:00:00Z"
)
```

**Parameters:**
- `effective_from`: `"next_billing_period"` (default) or `"immediately"`
- `resume_at`: Optional ISO timestamp for automatic resume

### Resume Subscription

```python
# Resume immediately (default)
await paddle_client.resume_subscription(
    subscription_id="sub_01...",
    effective_from="immediately"
)

# Resume at next billing period
await paddle_client.resume_subscription(
    subscription_id="sub_01...",
    effective_from="next_billing_period"
)
```

## Common Use Cases

### Upgrade Plan

Replace base plan price with higher tier:

```python
# Get current subscription
current = await paddle_client.get_subscription("sub_01...")
current_items = current.get("items", [])

# Replace base plan, keep addons
new_items = []
for item in current_items:
    price_id = item.get("price", {}).get("id")
    if price_id == "pri_basic_01...":
        # Replace with pro plan
        new_items.append({"price_id": "pri_pro_01...", "quantity": 1})
    else:
        # Keep addon
        new_items.append({"price_id": price_id, "quantity": item.get("quantity", 1)})

await paddle_client.update_subscription(
    subscription_id="sub_01...",
    items=new_items,
    proration_billing_mode="prorated_immediately"
)
```

### Downgrade Plan

Replace with lower tier, optionally remove addons:

```python
await paddle_client.update_subscription(
    subscription_id="sub_01...",
    items=[
        {"price_id": "pri_basic_01...", "quantity": 1}
        # Removed addons by not including them
    ],
    proration_billing_mode="prorated_next_billing_period"  # Credit on next bill
)
```

### Add Addon

```python
await paddle_client.add_subscription_items(
    subscription_id="sub_01...",
    new_items=[
        {"price_id": "pri_extra_storage_01...", "quantity": 1}
    ]
)
```

### Remove Addon

```python
await paddle_client.remove_subscription_items(
    subscription_id="sub_01...",
    price_ids_to_remove=["pri_extra_storage_01..."]
)
```

### Increase Quantity

For usage-based or quantity pricing:

```python
# Get current items
current = await paddle_client.get_subscription("sub_01...")
items = []
for item in current.get("items", []):
    price_id = item.get("price", {}).get("id")
    if price_id == "pri_seats_01...":
        # Increase seats from 5 to 10
        items.append({"price_id": price_id, "quantity": 10})
    else:
        items.append({"price_id": price_id, "quantity": item.get("quantity", 1)})

await paddle_client.update_subscription(
    subscription_id="sub_01...",
    items=items,
    proration_billing_mode="prorated_immediately"
)
```

## Proration Modes Explained

### `prorated_immediately`
Customer is charged/credited the prorated amount immediately.

**Example:** Upgrade mid-month from $10/mo to $20/mo on day 15:
- Credit: $5 (unused 15 days of $10 plan)
- Charge: $10 (15 days of $20 plan)
- Net charge: $5 immediately

### `prorated_next_billing_period`
Prorated amount is added to next billing period invoice.

**Example:** Same upgrade but charge deferred to next month's invoice.

### `full_immediately`
Full amount of new items charged immediately, no proration.

**Example:** Adding $5/mo addon charges $5 immediately regardless of billing cycle position.

### `full_next_billing_period`
Full amount added to next billing period, no proration.

**Example:** Adding $5/mo addon adds $5 to next month's invoice.

### `do_not_bill`
No billing for the change. Useful for complimentary upgrades.

## Scheduled Changes

Schedule a change for future date:

```python
await paddle_client.update_subscription(
    subscription_id="sub_01...",
    scheduled_change={
        "action": "pause",
        "effective_at": "2026-02-01T00:00:00Z"
    }
)
```

**Actions:**
- `"pause"` - Schedule pause
- `"cancel"` - Schedule cancellation
- `"resume"` - Schedule resume

## Best Practices

1. **Always pass full items list** to `update_subscription()` - Paddle replaces all items
2. **Use helper methods** (`add_subscription_items`, `remove_subscription_items`) for simpler operations
3. **Choose appropriate proration mode**:
   - Upgrades: `prorated_immediately` (charge now)
   - Downgrades: `prorated_next_billing_period` (credit on next bill)
   - Addons: `prorated_immediately` (charge proportionally)
4. **Handle errors gracefully** - Paddle may reject invalid item combinations
5. **Validate price IDs** before updating - ensure they exist and are active
6. **Keep at least one item** - subscriptions need at least one price

## Error Handling

```python
from fastapi import HTTPException

try:
    await paddle_client.update_subscription(
        subscription_id="sub_01...",
        items=[{"price_id": "pri_01...", "quantity": 1}]
    )
except ValueError as e:
    # Business logic error (e.g., removing all items)
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    # Paddle API error
    raise HTTPException(status_code=502, detail=f"Paddle API error: {str(e)}")
```

## Testing

See [tests/test_billing_paddle.py](tests/test_billing_paddle.py) for examples of:
- Mocking Paddle API responses
- Testing subscription updates
- Handling edge cases

## References

- [Paddle API: Update Subscription](https://developer.paddle.com/api-reference/subscriptions/update-subscription)
- [Paddle Guide: Add/Remove Products](https://developer.paddle.com/build/subscriptions/add-remove-products-prices-addons)
- [Paddle Guide: Proration](https://developer.paddle.com/build/subscriptions/proration)
- [Paddle API: Cancel Subscription](https://developer.paddle.com/api-reference/subscriptions/cancel-subscription)
- [Paddle API: Pause Subscription](https://developer.paddle.com/api-reference/subscriptions/pause-subscription)
- [Paddle API: Resume Subscription](https://developer.paddle.com/api-reference/subscriptions/resume-subscription)
