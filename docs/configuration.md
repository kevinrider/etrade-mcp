# Configuration and execution boundary

CLI options override environment variables. Configuration is startup-only; there
is no adapter configuration file or automatic dotenv loading.

| Environment variable | Default | CLI option |
| --- | --- | --- |
| `ETRADE_ENVIRONMENT` | `sandbox` | `--environment` (`sandbox` / `production`) |
| `ETRADE_CONSUMER_KEY`, `ETRADE_CONSUMER_SECRET` | required | environment only |
| `ETRADE_MCP_TRANSPORT` | `streamable-http` | `--transport` |
| `ETRADE_MCP_PROFILE` | `default` | `--profile` |
| `ETRADE_MCP_HOST` | `127.0.0.1` for HTTP | `--host` |
| `ETRADE_MCP_PORT` | `8000` for HTTP | `--port` |
| `ETRADE_MCP_HTTP_BEARER_TOKEN` | required for HTTP | environment only |
| `ETRADE_MCP_ENABLE_ORDER_EXECUTION` | `false` | `--enable-order-execution` / `--no-enable-order-execution` |
| `ETRADE_MCP_ENABLE_ALERT_DELETION` | `false` | `--enable-alert-deletion` / `--no-enable-alert-deletion` |
| `ETRADE_MCP_TOOL_ALLOWLIST` | omitted: all capability-permitted tools | `--tool-allowlist` |
| `ETRADE_MCP_DEBUG_TOOL_CALLS` | `false` | `--debug-tool-calls` / `--no-debug-tool-calls` |

Broker settings also accept `ETRADE_REQUEST_TIMEOUT_SECONDS` (30) and
`ETRADE_INACTIVITY_BUFFER_SECONDS` (300), managed by the client. Stdio rejects
explicit HTTP host, port, or bearer settings, including inherited environment
variables. Invalid settings and unknown tool names fail startup with sanitized
errors.

The allowlist is comma-separated exact names, for example
`--tool-allowlist server_status`. An omitted allowlist permits all tools allowed
by capability switches; `--tool-allowlist ""` exposes none. Disabled or excluded
tools are hidden from discovery and denied on direct invocation. The allowlist
cannot override disabled execution capabilities. Order execution and alert
deletion are independent switches; both default off.

Read and preview capabilities are enabled by default. All general and specialized
previews work without `--enable-order-execution` and can be excluded by the tool
allowlist. Preview annotations are non-destructive,
with `readOnlyHint: false` and `idempotentHint: false`, because broker previews
generate identifiers and should not be treated as automatically repeatable reads.

Execution switches authorize a process capability. An HTTP bearer token identifies
access to that process. Neither proves human approval of an individual trade.
The consuming host must obtain approval for every opening, closing, cancellation,
modification, and roll; bind it to the exact account, request and preview; and
obtain new approval after material changes. An LLM-supplied approval flag has no
such authority. All HTTP callers sharing the token share one profile and access
scope; this is a trusted local deployment, not multi-user account isolation.

Preview and placement remain separate operations. The adapter adds no
mutation retries, execution database, approval records, deduplication, or background
monitoring. Hosts own submission history and reconciliation. After a lost response
or uncertain outcome, reconcile with the broker before resubmitting. A restart
will not recover execution state. Strategy and scheduling stay outside the adapter.
