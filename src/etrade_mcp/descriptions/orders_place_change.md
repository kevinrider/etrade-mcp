Submit a complete replacement for an explicitly targeted account/order using the public client changed-order placement endpoint. This tool can modify live orders in production.

Requires --enable-order-execution and inclusion in any configured allowlist. The trusted host must obtain human approval for the exact target and replacement, bound to its change preview. LLM approval flags do not establish authorization.

Supply the entire data.placement_arguments object from the corresponding general or specialized change-preview tool, including account_id_key, order_id, the client_order_id from that change preview unchanged (the new ID assigned to this modification, not the original placed order's ID), every preview ID, and the full replacement request. This is not a patch: the server does not fetch or merge existing order fields. New-order previews are not substitutes for change previews. Broker aliases are accepted; prices and quantities use decimal strings. Material changes require another preview and renewed approval. The broker determines whether the target is still changeable.

Calls changed-order placement once, with no implicit preview, automatic retry, deduplication, or execution database. Shared execution supports every client-supported structure; there are no family-specific placement tools. Rolls or mixed opening/closing requests use complete requests supported by the general client, not automatic multi-order workflows.

Returns the complete broker placement result. Acceptance is not proof of a fill. Lost responses and uncertain_execution require host reconciliation before another submission. Preserve attempt history across server restarts and never generate new IDs or previews automatically to bypass an error.

Synthetic argument example (illustrative IDs; use the actual corresponding preview's placement arguments):

```json
{
  "account_id_key": "synthetic-key",
  "order_id": 17,
  "request": {
    "order_type": "EQ",
    "client_order_id": "ChangeExample001",
    "preview_ids": [{"preview_id": 102}],
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
