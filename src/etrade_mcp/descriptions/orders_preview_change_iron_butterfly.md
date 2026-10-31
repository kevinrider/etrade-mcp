Preview a complete replacement of an existing iron butterfly order using the broker preview endpoint only. Does not place, change, or cancel an order.

Generate a new account-unique client_order_id for this modification; do not reuse the original placed order's ID or an ID used for another order/modification. Use 1–20 ASCII letters/digits and preserve this ID unchanged from this preview through its corresponding placement. After an uncertain submission, reconcile before resubmitting; never generate a fresh ID to bypass a duplicate error.

Four equal-quantity options: lower put, middle put, middle call, upper call. Three strictly increasing equally spaced strikes. Opening sides are wing/body/body/wing; body is opposite wing_action.

position_effect OPEN maps opening BUY/SELL roles to BUY_OPEN/SELL_OPEN. CLOSE reverses them to SELL_CLOSE/BUY_CLOSE. Supply the complete defined structure; partial adjustments and mixed opening/closing legs use the general preview tools.

Use the obfuscated account_id_key from accounts_list and the account-scoped order_id from orders_list. This is a complete replacement, not a patch. Broker rules limit editable fields, including spread/buy-write quantities. Supply actual listed option contracts; no holdings, prices, strategy, or contract availability are inferred.

Pricing: NET_DEBIT or NET_CREDIT requires a positive limit_price magnitude on the broker pricing basis; NET_EVEN requires no price. Never infer debit/credit from leg direction. Unused prices must be omitted/null. Prices and quantities are positive finite decimal strings; option quantities must be whole contracts. Defaults are GOOD_FOR_DAY and REGULAR. Advanced pricing, lots, routing, disclosures, multiple entries, and unsupported structures use the general preview tools.

Returns data.broker_preview with the complete broker response and data.placement_arguments containing the exact normalized order plus every preview ID and order_id. These arguments are not approval or authorization. The host owns exact-request review, human approval, freshness, submission history, and reconciliation. No order is stored and no automatic retry occurs.

Synthetic argument example (illustrative client_order_id; generate a fresh value for an actual workflow):

```json
{
  "account_id_key": "synthetic-key",
  "request": {
    "client_order_id": "DesignExample001",
    "symbol": "SYN",
    "price_type": "NET_CREDIT",
    "limit_price": "1.25",
    "quantity": "1",
    "expiration": "2027-01-15",
    "lower_put_strike": "95.00",
    "middle_strike": "100.00",
    "upper_call_strike": "105.00",
    "wing_action": "BUY",
    "position_effect": "OPEN"
  },
  "order_id": 17
}
```
