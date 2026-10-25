Preview a complete replacement for a working order without modifying or placing it. Obtain account_id_key and the positive integer order_id from orders_list; use the order ID, not a preview ID. Inspect current broker status first.

Provide the complete intended replacement under request, including unchanged settings to retain; this is not a price-only patch. Use the same full request schema as orders_preview, including explicit option opening/closing actions and decimal-string prices/quantities. Omit unused disclosure/mf_quantity objects or use null; explicit empty/all-null objects are preserved.

Returns a fresh full broker preview directly in data, including PreviewIds and warnings. The broker decides what is changeable; for example its documented spread/buy-write restrictions prohibit changing quantity. Complete-request support does not promise arbitrary changes are accepted.

The host retains the exact account/order/request and preview for human review, freshness, approval binding, and later submission. Material changes need another preview and approval. No mutation, stored preparation record, or automatic retry occurs. Use orders_preview for a new order.

Synthetic argument example:

```json
{
  "account_id_key": "synthetic-key",
  "request": {
    "order_type": "EQ",
    "client_order_id": "ExampleChange001",
    "orders": [
      {
        "price_type": "LIMIT",
        "limit_price": "6.00",
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
  },
  "order_id": 17
}
```
