Read a quote for one symbol with optional detail flags. Use market_lookup_product if the symbol is uncertain; use market_get_quotes for a batch. Returns one complete client-modeled quote, including available timestamps/status. Data freshness and real-time entitlement depend on the broker; this tool does not calculate an executable order price.

Synthetic argument example:

```json
{
  "symbol": "SYN",
  "request": {
    "detail_flag": "ALL"
  }
}
```
