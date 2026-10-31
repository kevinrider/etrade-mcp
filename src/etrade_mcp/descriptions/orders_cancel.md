Request cancellation of one explicit account/order through the public client. This can affect a live order in production.

Requires --enable-order-execution and inclusion in any configured allowlist. Use the obfuscated account_id_key from accounts_list and the positive integer order_id from orders_list. The trusted host must obtain human approval bound to this exact cancellation target. No LLM-supplied approval flag is accepted.

Cancellation does not require a preview or server preparation record. Calls the broker once; does not cancel by symbol, choose a replacement, automatically retry, or place another order. The broker determines whether cancellation is still possible; execution may race cancellation.

Returns the complete cancellation acknowledgment and messages. An acknowledgment does not prove that no fills occurred. On an error, uncertain_execution, or a lost response, the host reconciles using order/transaction reads before another attempt. Server restart neither retries the request nor resolves its outcome. Repeated explicit calls are separate attempts, with no server deduplication promise.

Synthetic argument example:

```json
{
  "account_id_key": "synthetic-key",
  "order_id": 17
}
```
