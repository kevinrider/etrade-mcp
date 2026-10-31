Submit one complete previewed order using the public client placement endpoint. This tool can create live orders when the server is configured for production.

Requires --enable-order-execution and inclusion in any configured allowlist. The trusted host must obtain human approval bound to the exact account, request, and preview. A flag or statement from an LLM does not establish approval.

Supply the entire data.placement_arguments object returned by any general or specialized new-order preview. Keep the client_order_id from that new-order preview unchanged, along with every preview ID, together with all intended order details. Broker aliases such as clientOrderId, Order, and PreviewIds are accepted. Use nested objects, not JSON-encoded strings, and decimal strings for prices and quantities. The broker checks preview validity and matching parameters. Material changes require a fresh preview and renewed host approval.

Calls placement once. Does not preview, reconstruct legs, fetch orders, deduplicate, or automatically retry. The preview may come from another process; the server stores no preparation or approval record. Repeating the tool call is a separate submission attempt. The host owns durable attempt history and reconciliation.

Returns the complete broker placement result, including order identifiers and messages. Acceptance is not proof of a fill. On uncertain_execution or a lost response, reconcile before resubmitting; never change IDs or automatically re-preview to bypass duplicate/expired-preview errors. Use orders_list and transactions tools for explicit reconciliation reads.

Synthetic argument example (illustrative IDs; use the actual corresponding preview's placement arguments):

```json
{
  "account_id_key": "synthetic-key",
  "request": {
    "order_type": "EQ",
    "client_order_id": "PlaceExample001",
    "preview_ids": [{"preview_id": 101}],
    "orders": [{
      "price_type": "LIMIT",
      "limit_price": "1.25",
      "order_term": "GOOD_FOR_DAY",
      "market_session": "REGULAR",
      "instruments": [{
        "product": {"symbol": "SYN", "security_type": "EQ"},
        "order_action": "BUY",
        "quantity": "1"
      }]
    }]
  }
}
```
