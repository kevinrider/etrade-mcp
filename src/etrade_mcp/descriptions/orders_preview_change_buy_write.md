Preview a complete replacement of an existing buy write order using the broker preview endpoint only. Does not place, change, or cancel an order.

Opening buy-write only: equity BUY followed by call SELL_OPEN. Provide independent stock and option quantities; no 100-share multiplier or covered-status assumption is made. Paired closing/unwind requests use orders_preview or orders_preview_change.

Use the obfuscated account_id_key from accounts_list and the account-scoped order_id from orders_list. This is a complete replacement, not a patch. Broker rules limit editable fields, including spread/buy-write quantities. Supply actual listed option contracts; no holdings, prices, strategy, or contract availability are inferred.

Pricing: NET_DEBIT or NET_CREDIT requires a positive limit_price magnitude on the broker pricing basis; NET_EVEN requires no price. Never infer debit/credit from leg direction. Unused prices must be omitted/null. Prices and quantities are positive finite decimal strings; option quantities must be whole contracts. Defaults are GOOD_FOR_DAY and REGULAR. Advanced pricing, lots, routing, disclosures, multiple entries, and unsupported structures use the general preview tools.

Returns data.broker_preview with the complete broker response and data.placement_arguments containing the exact normalized order plus every preview ID and order_id. These arguments are not approval or authorization. The host owns exact-request review, human approval, freshness, submission history, and reconciliation. No order is stored and no automatic retry occurs.

Synthetic argument example:

```json
{
  "account_id_key": "synthetic-key",
  "request": {
    "client_order_id": "DesignExample001",
    "symbol": "SYN",
    "price_type": "NET_DEBIT",
    "limit_price": "1.25",
    "stock_quantity": "100",
    "option_quantity": "1",
    "expiration": "2027-01-15",
    "strike_price": "105.00"
  },
  "order_id": 17
}
```
