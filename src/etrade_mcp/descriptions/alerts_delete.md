Delete exactly the supplied broker alert IDs in one request. This permanently changes alert state; it does not cancel brokerage orders.

Requires the independent --enable-alert-deletion switch and inclusion in any configured allowlist. The order-execution switch does not authorize alert deletion. Obtain alert IDs from alerts_list or alerts_get. Supply a nonempty array of positive integer IDs, including a one-element array for a single alert. No account key or preview is required.

Uses the public client once without automatic retries, splitting, deduplication, or preparation records. The host controls deletion authorization and records attempts. Repeating a tool call is another broker request.

On explicit SUCCESS without failed IDs, data contains the complete DeleteAlertsResponse. If the broker reports ERROR or any failed IDs, isError is true, data is null, error.code is broker_rejection, and error.alert_deletion_result preserves the complete broker result, including failedAlerts. The batch may have partially succeeded: never automatically retry all IDs. An inconclusive result or transport loss is uncertain_execution and requires reconciliation; an available broker result is retained under error.alert_deletion_result. Other tools leave that field null.

Inspect alerts through explicit read tools to reconcile. A lost response or restart does not establish whether deletion happened, and the server stores no recovery state.

Synthetic argument example:

```json
{
  "alert_ids": [101, 102]
}
```
