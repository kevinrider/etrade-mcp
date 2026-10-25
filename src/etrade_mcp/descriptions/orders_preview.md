Preview a complete new order without placing it. Obtain account_id_key from accounts_list and use actual symbols/contracts from market tools. Supports equities, single/multi-leg options, buy-writes, multiple entries, and all public client request capabilities.

Provide order_type, a caller-assigned 1–20 alphanumeric client_order_id, and complete orders/instruments. Equity uses BUY/SELL/SELL_SHORT/BUY_TO_COVER; option legs use BUY_OPEN/SELL_OPEN/BUY_CLOSE/SELL_CLOSE and require CALL/PUT, expiration year/month/day, and strike_price. Prices and quantities are decimal strings. LIMIT needs limit_price; STOP needs stop_price; STOP_LIMIT needs stop_price and a limit. NET_DEBIT/NET_CREDIT use a positive net limit_price; do not assign separate leg prices.

Omit unused optional objects (especially disclosure and mf_quantity) or use null. Explicit objects are preserved even when all children are null; do not fill the schema with placeholder objects. Detail/instrument extensions are supported; unknown fields elsewhere are rejected.

Returns data.broker_preview with the complete broker preview, including PreviewIds and warnings. data.placement_arguments contains the exact normalized request plus all preview IDs and account targeting for future placement; it is not approval or authorization. Retain the exact request, preview IDs, and observation time for review. Preview is not approval; the host owns request binding, freshness, human approval, and submission history. No pending order is stored, no order is placed, and no automatic retry occurs. Use orders_preview_change for an existing order.

Synthetic argument example:

```json
{
  "account_id_key": "synthetic-key",
  "request": {
    "order_type": "EQ",
    "client_order_id": "ExampleEquity001",
    "orders": [
      {
        "price_type": "LIMIT",
        "limit_price": "5.00",
        "order_term": "GOOD_FOR_DAY",
        "market_session": "REGULAR",
        "instruments": [
          {
            "product": {
              "symbol": "SYN",
              "security_type": "EQ"
            },
            "order_action": "BUY",
            "quantity_type": "QUANTITY",
            "quantity": "1"
          }
        ]
      }
    ]
  }
}
```

Synthetic two-leg call spread example (contracts and price are illustrative):

```json
{
  "account_id_key": "synthetic-key",
  "request": {
    "order_type": "SPREADS",
    "client_order_id": "ExampleSpread001",
    "orders": [
      {
        "price_type": "NET_DEBIT",
        "limit_price": "1.25",
        "order_term": "GOOD_FOR_DAY",
        "instruments": [
          {
            "product": {
              "symbol": "SYN",
              "security_type": "OPTN",
              "call_put": "CALL",
              "expiry_year": 2027,
              "expiry_month": 1,
              "expiry_day": 15,
              "strike_price": "100.00"
            },
            "order_action": "BUY_OPEN",
            "quantity": "1"
          },
          {
            "product": {
              "symbol": "SYN",
              "security_type": "OPTN",
              "call_put": "CALL",
              "expiry_year": 2027,
              "expiry_month": 1,
              "expiry_day": 15,
              "strike_price": "105.00"
            },
            "order_action": "SELL_OPEN",
            "quantity": "1"
          }
        ]
      }
    ]
  }
}
```
