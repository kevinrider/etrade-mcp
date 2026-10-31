# Execution tools

Execution is opt-in at process startup. `--enable-order-execution` permits
`orders_place`, `orders_place_change`, and `orders_cancel`;
`--enable-alert-deletion` separately permits `alerts_delete`. An allowlist can
restrict these further. All mutations advertise destructive, non-read-only,
non-idempotent behavior. The same permissions apply over HTTP and stdio.

A trusted execution controller can use a narrowly scoped process, for example:

```sh
uv run --frozen etrade-mcp serve --enable-order-execution \
  --tool-allowlist server_status,orders_list,transactions_list,orders_place,orders_place_change,orders_cancel
```

Existing HTTP credentials, environment, and profile configuration still apply.
A preview-only LLM process can use the default permissions and its own allowlist.
Every caller sharing an execution-enabled process shares that execution access;
MCP annotations, bearer credentials, and startup switches do not attest approval.
The consuming host must obtain human approval and preserve its exact request and
preview association before invoking these tools.

Pass the entire `data.placement_arguments` from a new-order preview directly to
`orders_place`. Pass the corresponding change-preview arguments, including
`order_id`, to `orders_place_change`. Both accept the complete public client
placement request with every preview ID, client order ID, leg, and supported
advanced field. Broker aliases are accepted; modeled prices and quantities remain
decimal strings. Neither tool implicitly previews or merges existing orders.
Material changes require another preview and renewed approval. The broker checks
preview validity; the adapter cannot certify association or freshness. The preview
may originate in another process, with no server preparation record to retrieve.

Generate a new account-unique `client_order_id` for each new order or modification,
using 1–20 ASCII letters/digits. A change preview needs a new ID; do not reuse the
original placed order's ID. Keep that ID unchanged through the corresponding
preview and placement:

| Workflow | Preview client ID | Placement client ID |
| --- | --- | --- |
| New order | `ExampleNew001` | `ExampleNew001` |
| First modification | `ExampleChange001` | `ExampleChange001` |
| Subsequent modification | `ExampleChange002` | `ExampleChange002` |

These IDs are illustrative; generate fresh values for actual workflows. The
caller owns account-wide uniqueness. After an uncertain submission, reconcile
before deciding whether to resubmit; a new ID must not bypass duplicate controls.

`orders_cancel` accepts an explicit `account_id_key` and positive integer
`order_id`; it does not require a preview. Obtain approval for that exact target.
Placement or cancellation acknowledgments do not establish fills or absence of
fills; execution can race a cancellation request.

Each mutation invocation dispatches at most once, preserving the client's
non-retryable endpoint policy. Explicit repeated calls are separate attempts;
there is no server deduplication or exactly-once promise. The host retains durable
attempt history across restarts. After `uncertain_execution`, a duplicate error,
or a lost response, reconcile with explicit broker reads before deciding whether
to resubmit the exact approved request. Never automatically generate fresh IDs,
refresh previews, or alter requests to bypass an error. A restart does not recover
execution state or redispatch a mutation.

`alerts_delete` accepts a nonempty `alert_ids` array of positive integers. A
single ID uses a one-element array. Explicit broker `SUCCESS` with no failed IDs
returns the complete result under `data`. Broker `ERROR` or any failed IDs return
`isError: true`, `data: null`, and `error.code: broker_rejection`, preserving the
complete typed result in nullable `error.alert_deletion_result`. Text within that
error detail follows broker-diagnostic redaction and the 1,000-character string
limit; all failed IDs remain available. A batch may have
partially succeeded: inspect `failedAlerts` and reconcile before another attempt,
without retrying the entire batch automatically. Unknown/inconclusive results use
`uncertain_execution` with the available result retained in the same field.
Transport failures can have no result to retain. Other failures leave this field
null. The envelope still contains exactly one non-null `data` or `error`, and
JSON text matches MCP structured content.

Automated mutation validation uses fake credentials and mocked broker HTTP.
No authenticated mutation or live order is part of development or package smoke
testing. Broker duplicate controls do not remove the host's recovery obligations.
