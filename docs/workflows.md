# Choose a workflow

Use an exact-name allowlist to limit the tools presented to a model. These are
configuration recipes, not new presets or strategy implementations. All examples
keep execution and alert deletion disabled; select sandbox or production and the
matching profile explicitly. For example:

```sh
etrade-mcp serve --environment sandbox --profile default \
  --no-enable-order-execution --no-enable-alert-deletion \
  --tool-allowlist server_status,accounts_list,market_get_quote,orders_list,orders_preview_equity,orders_preview_change_equity
```

HTTP also requires its configured bearer token. For stdio, remove HTTP-only
settings and add `--transport stdio`; see [client connection guide](connections.md).

| Workflow | Suggested allowlist |
| --- | --- |
| Equity | `server_status,accounts_list,market_get_quote,orders_list,orders_preview_equity,orders_preview_change_equity` |
| Single option | `server_status,accounts_list,market_get_quote,market_get_option_expirations,market_get_option_chain,orders_list,orders_preview_single_option,orders_preview_change_single_option` |
| Selected spreads (vertical and iron condor) | `server_status,accounts_list,market_get_quote,market_get_option_expirations,market_get_option_chain,orders_list,orders_preview_vertical,orders_preview_change_vertical,orders_preview_iron_condor,orders_preview_change_iron_condor` |
| Market research only | `server_status,market_get_quote,market_get_quotes,market_lookup_product,market_get_option_expirations,market_get_option_chain` |
| Account/portfolio research | `server_status,accounts_list,accounts_get_balance,portfolio_get_positions,transactions_list,transactions_get,orders_list,alerts_list,alerts_get` |
| Complete read/preview catalog | Omit the allowlist with both execution switches disabled: 34 tools. |
| Complete catalog including execution | Omit the allowlist and explicitly enable both capabilities: 38 tools. This grants execution access to every authorized caller. |

Add `portfolio_get_positions` when the workflow needs existing holdings. Add the
general `orders_preview`/`orders_preview_change` tools explicitly when advanced
fields, unsupported structures, or mixed opening/closing requests need a fallback.
Only the host/user selects intent; the server does not infer a strategy, holdings,
listed contracts, or permission to trade. Each order tool's packaged example and
field guidance is visible through MCP discovery.

A deterministic controller can use a separate process scoped to
`server_status,orders_list,transactions_list,orders_place,orders_place_change,orders_cancel`,
with order execution enabled. Keep the model-facing process in preview mode. The
controller must obtain the returned exact placement arguments and human approval,
check account/order targeting and freshness, durably record a submission attempt,
then invoke the corresponding mutation once. Record the acknowledgment and
reconcile with explicit reads after any uncertain outcome. A material edit needs
a new preview and approval; a new modification needs a new client order ID. This
is the host's workflow, not a controller or journal implemented by this package.
Alert deletion requires its separate switch and exact-target approval.
