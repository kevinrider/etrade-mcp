Read one broker page of account orders with optional status, date, symbol, and session filters. Obtain account_id_key from accounts_list. Continue using the returned marker unchanged with the same filters; no pages are aggregated. Use returned order IDs for orders_preview_change and inspect current broker status when reconciling execution. An empty result alone does not prove an earlier submission failed. Does not preview, modify, cancel, or place orders.

Synthetic argument example:

```json
{
  "account_id_key": "synthetic-key",
  "request": {
    "status": "OPEN",
    "count": 25
  }
}
```
