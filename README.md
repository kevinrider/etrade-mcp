# etrade-mcp

A typed, async MCP adapter over [etrade-python](https://pypi.org/project/etrade-python/).
Python 3.11–3.14; loopback Streamable HTTP and stdio.

**Alpha: Milestone 3.** All 13 client-supported brokerage reads and
`server_status` are available over both transports. Previews and mutations
remain planned. Enabling execution flags does not add unimplemented tools.
The [tool coverage table](#tool-coverage) tracks implemented tools and their
tests, planned client operations, request models, and intentional omissions.

## Install and authenticate

Until a release is published, install from a local checkout of this repository.
With Python 3.11+ and uv installed, run from the repository root:

```sh
uv tool install --with-executables-from etrade-python .
etrade-mcp --version
etrade --version
```

uv builds the package and exposes both `etrade-mcp` and the client's `etrade`
authentication CLI from the same isolated tool environment; no prebuilt wheel or
`dist/` directory is needed. If you already have a compatible `etrade` CLI
installed (`etrade-python>=1.1,<2`), use `uv tool install .` to keep that executable
and avoid a conflict. For development, use the setup commands in
[CONTRIBUTING.md](CONTRIBUTING.md) and launch with `uv run etrade-mcp` instead.

Provide `ETRADE_CONSUMER_KEY` and `ETRADE_CONSUMER_SECRET` through your protected
process environment. They are required even when no access token is stored.
The adapter does not load `.env` automatically. Use the client CLI for
interactive OAuth setup, with the same environment and profile as the server:

```sh
export ETRADE_ENVIRONMENT=sandbox
etrade auth login --profile default
```

For checkout-based development, run `uv run etrade auth login --profile default`
instead, with the same environment and profile as `uv run etrade-mcp`.

The client manages OAuth signing, renewal, expiration, and OS-keyring storage.
`etrade-python>=1.1,<2` supplies credential coordination across cooperating local
processes. All processes sharing a profile must use that coordinated client;
older processes are not protected. Configure separate processes for separate
profiles/environments. Consumer keys must match the selected broker environment.
OAuth verifier exchange, explicit renewal, and revocation remain in `etrade auth`;
they are not exposed as model-callable tools.

## Run and connect

Streamable HTTP is the default, at `http://127.0.0.1:8000/mcp`. Generate a bearer
credential once and provide the same value to the server and authorized clients
through protected environment/configuration. For example, in a private shell:

```sh
export ETRADE_MCP_HTTP_BEARER_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
etrade-mcp serve --transport streamable-http --environment sandbox --profile default
```

Every HTTP request requires `Authorization: Bearer <configured token>`. This is
static access control, separate from broker OAuth; the server does not provide an
OAuth authorization server or interactive MCP login. Only loopback IP literals
are accepted for binding. SDK Host/Origin checks restrict requests to the bound
address and localhost at the configured port. Non-browser clients may omit Origin;
wildcard CORS and reverse-proxy deployment are not supported. Disable client debug
logging that would record authorization headers.

A host that launches its server can use stdio instead:

```sh
# Remove inherited HTTP-only configuration before selecting stdio.
unset ETRADE_MCP_HTTP_BEARER_TOKEN ETRADE_MCP_HOST ETRADE_MCP_PORT
etrade-mcp serve --transport stdio --environment sandbox --profile default
```

Configure an MCP client's stdio command as `etrade-mcp` with arguments
`serve --transport stdio --environment sandbox --profile default`, forwarding
broker credentials through its protected subprocess environment. For a local
agent harness or another HTTP-capable MCP client, configure the URL above and a
bearer credential sourced from protected configuration. No secrets belong in
model prompts or command-line arguments. The server uses the same tools and
permissions for either transport. Stdio reserves stdout for protocol traffic;
diagnostics go to stderr. HTTP disables request access logging.

The official `mcp>=2.3,<3` SDK supplies async tools, structured schemas, both
transports, and compatibility with earlier protocol revisions without an extra
framework. The lockfile resolves SDK 2.3.0 and client 1.1.0. Tests exercise modern
SDK mode (protocol `2026-07-28`) and legacy mode (`2025-11-25`);
installed-artifact checks exercise both transports.
This is protocol validation, not a claim of manual validation in every MCP host.

## Configuration and execution boundary

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

Execution switches authorize a process capability. An HTTP bearer token identifies
access to that process. Neither proves human approval of an individual trade.
The consuming host must obtain approval for every opening, closing, cancellation,
modification, and roll; bind it to the exact account, request and preview; and
obtain new approval after material changes. An LLM-supplied approval flag has no
such authority. All HTTP callers sharing the token share one profile and access
scope; this is a trusted local deployment, not multi-user account isolation.

Future tools will keep preview and placement separate. The adapter adds no
mutation retries, execution database, approval records, deduplication, or background
monitoring. Hosts own submission history and reconciliation. After a lost response
or uncertain outcome, reconcile with the broker before resubmitting. A restart
will not recover execution state. Strategy and scheduling stay outside the adapter.

## Tool and result contract

`server_status` takes `{}` and reports versions, environment/profile, transport,
enabled tools/capabilities and a local credential estimate.
It loads the configured keyring entry through public session APIs without making
a broker request. Missing access credentials are allowed at startup and reported
as `missing`; a keyring/backend failure produces a sanitized error. An `active`
estimate does not prove broker authorization. Use the client CLI to troubleshoot
OAuth/keyring setup.

Tool results contain matching JSON text and MCP `structuredContent`:

```json
{
  "data": null,
  "error": {
    "code": "authentication_required",
    "message": "Run etrade auth login for the configured environment/profile.",
    "status_code": null,
    "broker_code": null,
    "request_id": null
  },
  "meta": {
    "environment": "sandbox",
    "profile": "default",
    "observed_at": "2026-10-17T12:00:00Z"
  }
}
```

MCP's `isError` is the authoritative tool execution status: success sets it to
`false` (or omits it), with typed `data` and `error: null`. Tool execution failures
set `isError: true`, with `data: null` and structured `error` details. The example
above is the payload of such a failure; `isError` belongs to the enclosing MCP
tool result, outside both the JSON text and `structuredContent`. Payloads contain
only `data`, `error`, and `meta`; there is no top-level `ok` field. Protocol-level
failures remain JSON-RPC errors rather than tool execution results.
Input models reject unknown fields at both the tool and nested request levels.
Decimal values serialize as strings. Client response fields use their declared
JSON aliases (for example, `accountPortfolio`, `nextPageNo`, and `transactionId`),
matching the advertised output schemas. Responses preserve the complete client-modeled data for each broker page.
Errors use static messages without raw input, exception text, or broker payloads.
Numeric broker codes and bounded safe request identifiers may be preserved, with
known secrets excluded. Errors distinguish:

- Invalid requests/policy: `invalid_input`, `execution_disabled`, `tool_not_available`.
- Credentials: `authentication_required`, `authorization_expired`,
  `authentication_failed`, `credential_coordination_failed`.
- Broker/transport: `broker_rejection`, `rate_limited`, `not_found`,
  `service_unavailable`, `invalid_broker_response`, `transport_error`.
- Uncertain mutation outcomes: `uncertain_execution`; unexpected read failures:
  `internal_error`.

Mutation transport loss, malformed responses, and potentially ambiguous server
errors are conservatively uncertain. Cancellation propagates to the SDK; a host
that loses a mutation response must reconcile even when no error result arrives.
No brokerage preview or mutation tool ships yet.

## Read inputs and pagination

Identifiers are top-level arguments; optional client request fields belong in a
nested `request` object. Omit `request`, use `null`, or pass `{}` for client defaults.
For example, `portfolio_get_positions` accepts:

```json
{
  "account_id_key": "account-key",
  "request": {"count": 25, "page_number": 1, "lots_required": true}
}
```

Schemas advertise Python request field names. Client-supported aliases such as
`htmlTags` and `fromDate` are also accepted; conflicting aliases and unknown
fields are rejected. Monetary inputs such as option-chain `strike_price_near`
must be decimal strings, for example `"100.125"`, rather than JSON numbers.
Request date strings are passed to the client without conversion; preserve its
supported broker date formats, such as `01012026` for transaction date filters.

Every read returns one broker response. Pagination is explicit:

- Portfolio responses preserve `accountPortfolio[].nextPageNo` and `next`;
  request the next page with `request.page_number`.
- Transaction responses preserve `marker`, `moreTransactions`, and other
  continuation fields. Pass the marker in the next request. Broker markers are
  inclusive, so boundary transactions can appear again. The adapter preserves
  them; the client's omitted `list_all` iterator performs boundary deduplication.
- Order responses preserve `marker` and `next`; pass `marker` to the next
  `orders_list` call. Counts and filters remain under the caller's control.

No read automatically fetches later broker pages or deduplicates records.

## Response sizes

Each successful read returns the complete client-modeled broker response in
`data`. There is no adapter-imposed size cap, truncation, result cache, or separate
retrieval step. MCP SDK, client, and model-context limits still apply; returning a
complete response does not guarantee that every host can consume arbitrarily
large results.

Use broker pagination, counts, and filters to keep results manageable. For option
chains, narrow the expiration, strike range, or chain type with the supported
request fields. Broker pagination and filters remain explicit caller choices;
the server does not fetch every page or silently rewrite requests.

## Tool coverage

Supported client dependency: `etrade-python>=1.1,<2`. Planned rows do not
represent available tools. Test links open the file containing the named test.

| Client operation | MCP tool | Status | Request model | Tests / notes |
| --- | --- | --- | --- | --- |
| `session.load`, `session.status` | `server_status` | Implemented | — | [test_status_protocol_and_strict_schema](tests/test_server.py)<br>[test_actual_http_discovery_invocation_and_concurrency](tests/test_http.py)<br>[test_actual_stdio_cli_protocol_and_stdout](tests/test_cli.py) |
| `accounts.list` | `accounts_list` | Implemented | — | [Request mapping and field coverage](tests/test_reads.py) |
| `accounts.get_balance` | `accounts_get_balance` | Implemented | `AccountBalanceRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `portfolio.get_positions` | `portfolio_get_positions` | Implemented | `PortfolioRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `transactions.list` | `transactions_list` | Implemented | `TransactionsRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `transactions.get` | `transactions_get` | Implemented | `TransactionDetailsRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `market.get_quote` | `market_get_quote` | Implemented | `QuotesRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `market.get_quotes` | `market_get_quotes` | Implemented | `QuotesRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `market.lookup_product` | `market_lookup_product` | Implemented | `ProductLookupRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `market.get_option_expirations` | `market_get_option_expirations` | Implemented | `OptionExpirationsRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `market.get_option_chain` | `market_get_option_chain` | Implemented | `OptionChainRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `orders.list` | `orders_list` | Implemented | `OrdersRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `orders.preview` | `orders_preview` | Planned | `PreviewOrderRequest` | — |
| `orders.place` | `orders_place` | Planned | `PlaceOrderRequest` | — |
| `orders.preview_change` | `orders_preview_change` | Planned | `PreviewOrderRequest` | — |
| `orders.place_change` | `orders_place_change` | Planned | `PlaceOrderRequest` | — |
| `orders.cancel` | `orders_cancel` | Planned | `CancelOrderRequest` | — |
| `alerts.list` | `alerts_list` | Implemented | `AlertsRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `alerts.get` | `alerts_get` | Implemented | `AlertDetailsRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `alerts.delete` | `alerts_delete` | Planned | — | — |
| `portfolio.iter_positions` | — | Omitted | — | Use explicit single-page tools; no automatic aggregation. |
| `transactions.list_all` | — | Omitted | — | Use explicit single-page tools; no automatic aggregation. |
| `orders.list_all` | — | Omitted | — | Use explicit single-page tools; no automatic aggregation. |

OAuth login, verifier exchange, explicit renewal and revocation remain in the
`etrade` CLI. Automatic client lifecycle management remains active.

The cases in [tests/read_cases.py](tests/read_cases.py) enumerate every supported
read request field. `test_read_request_fields_reach_real_client` verifies their
final HTTP paths and query parameters using the real client;
`test_request_cases_cover_public_client_fields` checks those cases against the
public request models. Preview and mutation coverage follows in later milestones.

## Development and verification

Use Python 3.11+ and uv. CI checks Python 3.11–3.14:

```sh
uv sync --extra dev --frozen
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pyright --pythonpath .venv/bin/python
uv run --frozen pytest
uv build --clear
uv run --frozen python -m twine check --strict dist/*
uv run --frozen python scripts/check_artifacts.py
```

Tests use real MCP discovery/invocation over stdio and loopback HTTP. Broker
integration tests exercise the real client with fake credentials and HTTPX
`MockTransport`; external broker networking is blocked. Artifact checks install
wheel and sdist independently outside the checkout and exercise both transports.
These are offline protocol and mocked brokerage tests, not authenticated broker
validation. No release or live order is submitted by these checks.
See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution and verification guidance.

## License

Apache-2.0. This project is not affiliated with or endorsed by E*TRADE or Morgan
Stanley.
