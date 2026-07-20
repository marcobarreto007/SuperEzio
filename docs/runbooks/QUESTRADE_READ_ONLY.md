# Questrade Read-Only Readiness

This integration is intentionally unable to place, replace, or cancel orders.
It is for account visibility, portfolio reconciliation, order/execution history,
and market-symbol lookup before any separate execution authorization exists.

## Setup

1. In Questrade API Centre, register and manually authorize a personal app.
2. Store the generated refresh token locally, never in source control:

   ```dotenv
   QUESTRADE_REFRESH_TOKEN=your-refresh-token
   QUESTRADE_PRACTICE=1
   ```

3. Verify connectivity:

   ```powershell
   python scripts/questrade_readiness_probe.py
   ```

The probe returns only provider state, mode, account count, and API server. It
does not print tokens, account passwords, or account numbers. Use `--live` only
to read metadata from the live OAuth endpoint; it still cannot send an order.

## Expected states

- `credentials_missing`: add `QUESTRADE_REFRESH_TOKEN` to the local `.env`.
- `connected: true`: OAuth and account listing succeeded; `can_submit_orders`
  remains `false` by design.
- `connected: false` with an HTTP error: regenerate/refresh the OAuth token or
  check Questrade API access without changing the application code.

## Boundary

`src/adapters/broker/questrade_readonly.py` uses only HTTP `GET` operations and
has no execution methods. Any future order capability requires a separate,
explicitly approved integration and Questrade authorization for the trade scope.
