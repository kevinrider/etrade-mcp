Read option-chain contracts for an underlying using optional expiration, strike, CALL/PUT, weekly, and adjusted-contract filters. Obtain listed expirations with market_get_option_expirations; strike_price_near must be a decimal string. Responses can be large: narrow expiry, no_of_strikes, and chain_type when appropriate. Returns the complete modeled broker response without adapter truncation, aggregation, or reference handles. Use actual returned contracts to construct option requests.

Synthetic argument example:

```json
{
  "symbol": "SYN",
  "request": {
    "expiry_year": 2027,
    "expiry_month": 1,
    "expiry_day": 15,
    "strike_price_near": "100.00",
    "no_of_strikes": 5,
    "chain_type": "CALLPUT",
    "skip_adjusted": true
  }
}
```
