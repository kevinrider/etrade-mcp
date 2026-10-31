# Debug incoming tool calls

Add `--debug-tool-calls` to your existing server command to print redacted JSON
diagnostics in the terminal where the server runs:

```sh
uv run --frozen etrade-mcp serve --debug-tool-calls
```

This is off by default. You can also set `ETRADE_MCP_DEBUG_TOOL_CALLS=true`;
`--no-debug-tool-calls` overrides that setting. Both HTTP and stdio write one
JSON line per event to **stderr**, keeping stdout reserved for MCP traffic.
HTTP authentication and other startup settings still apply.

Each `tool_call.received` event includes a generated `call_id`, the tool name,
argument types, and a bounded argument preview. A matching `tool_call.completed`
event reports success/error status and safe error codes and validation paths.
Account, order, transaction, alert, and client-order identifiers are masked.
Credentials and authentication fields are withheld; unknown field names and
values are omitted, with only their count recorded. Broker response bodies and
error messages are never included. Selected trading inputs, including symbols,
prices, quantities, and order settings, are intentionally visible while enabled.
