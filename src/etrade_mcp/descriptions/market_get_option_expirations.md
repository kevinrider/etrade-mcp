Read listed option expiration dates for an underlying symbol, optionally filtered by expiration type. Use this before selecting expiry_year/month/day for market_get_option_chain. Returns broker-listed dates and classifications; do not infer contract availability from a valid calendar date alone. This is market discovery, not an order preview.

Synthetic argument example:

```json
{
  "symbol": "SYN",
  "request": {
    "expiry_type": "ALL"
  }
}
```
