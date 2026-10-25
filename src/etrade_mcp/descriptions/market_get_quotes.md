Read quotes for a nonempty array of symbols in one broker request. The client allows up to 25 symbols, or 50 with request.override_symbol_count true; this tool does not split larger batches. Returns the full modeled quote collection, whose quote status and timestamps describe broker data freshness. Use market_get_quote for a single quote when a collection is unnecessary.

Synthetic argument example:

```json
{
  "symbols": [
    "SYN",
    "SYNB"
  ],
  "request": {
    "detail_flag": "ALL"
  }
}
```
