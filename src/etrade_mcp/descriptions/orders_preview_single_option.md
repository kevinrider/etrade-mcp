Preview a new single option order using the broker preview endpoint only. Does not place, change, or cancel an order.

One option contract with explicit BUY_OPEN, SELL_OPEN, BUY_CLOSE, or SELL_CLOSE action and CALL/PUT right.

Use the obfuscated account_id_key from accounts_list. Supply actual listed option contracts; no holdings, prices, strategy, or contract availability are inferred.

Pricing: MARKET, LIMIT, STOP, or STOP_LIMIT. LIMIT and STOP_LIMIT require limit_price; STOP and STOP_LIMIT require stop_price. Unused prices must be omitted/null. Prices and quantities are positive finite decimal strings; option quantities must be whole contracts. Defaults are GOOD_FOR_DAY and REGULAR. Advanced pricing, lots, routing, disclosures, multiple entries, and unsupported structures use the general preview tools.

Returns data.broker_preview with the complete broker response and data.placement_arguments containing the exact normalized order plus every preview ID. These arguments are not approval or authorization. The host owns exact-request review, human approval, freshness, submission history, and reconciliation. No order is stored and no automatic retry occurs.

Synthetic argument example:

```json
{
  "account_id_key": "synthetic-key",
  "request": {
    "client_order_id": "DesignExample001",
    "symbol": "SYN",
    "price_type": "LIMIT",
    "limit_price": "1.25",
    "order_action": "SELL_OPEN",
    "quantity": "1",
    "call_put": "PUT",
    "expiration": "2027-01-15",
    "strike_price": "100.00"
  }
}
```
