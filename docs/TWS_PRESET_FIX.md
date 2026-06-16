# TWS Preset Cancel Fix

## Problem
TWS paper trading account has a preset that auto-cancels LMT (limit) orders. This causes 4/5 paper orders to be canceled immediately.

## Solution: Disable TWS Order Preset

1. Open TWS Paper Trading account
2. Go to **Configuration** → **Order Presets**
3. Find the preset that cancels LMT orders
4. Delete or disable the preset

## Code Fix (already applied)

The `_ibkr_order.py` script now sets:
- `order.tif = 'DAY'` — explicit Time-In-Force
- `order.displaySize = qty` — show full size
- `order.outsideRth = False` — regular hours only

This should prevent most auto-cancellations, but the TWS preset still needs to be disabled for 100% reliability.

## Verification

After disabling the preset:
1. Submit a test LMT order via the script
2. Check TWS Order Book
3. Verify order stays active (not Cancelled)

## Alternative: Use Market Orders

If LMT orders continue to be cancelled, use MARKET orders for paper trading:
- Set `limit_price = 0.0` in the order request
- This bypasses the LMT preset entirely
