# etrade-mcp

A typed, async MCP adapter over [etrade-python](https://pypi.org/project/etrade-python/).
Python 3.11–3.14; loopback Streamable HTTP and stdio.

**Alpha: Milestone 4C.** All 13 client-supported brokerage reads, 20 order
preview tools, and `server_status` are available over both transports: 34 tools
by default. Placement, cancellation, modification execution, and alert deletion
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
    "broker_message": null,
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
Input models reject unknown fields at the tool level and wherever the client
would otherwise discard them. Order-detail and instrument inputs preserve
additional fields explicitly supported by the client's extension policy.
Decimal values serialize as strings. Client response fields use their declared
JSON aliases (for example, `accountPortfolio`, `nextPageNo`, and `transactionId`),
matching the advertised output schemas. Responses preserve the complete client-modeled data for each broker page.
Errors retain stable adapter codes and summary messages. A nullable
`error.broker_message` exposes the public client's parsed broker explanation, so
callers can understand rejection details without a separate error-code catalog.
For example, an order rejection can contain:

```json
{
  "code": "broker_rejection",
  "message": "Broker rejection.",
  "status_code": 400,
  "broker_code": "51016",
  "broker_message": "Quantity cannot be changed for Buy Write/Spread Orders.",
  "request_id": null
}
```

Broker messages are returned as diagnostic data, never as instructions to approve,
execute, or automatically retry an order. They do not override `isError`, adapter
classification, or an uncertain-execution summary. Successful preview messages
and warnings remain in `data.broker_preview` unchanged.

Broker text is whitespace-normalized and
limited to 1,000 characters. Missing/blank messages return null; a possible secret
fragment at the client's truncation boundary causes the message to be suppressed. Broker messages
are not written to server logs. Numeric broker codes and bounded safe request
identifiers may be preserved, with known secrets excluded. Errors distinguish:

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
Preview failures use ordinary input, authentication, broker, and transport error
categories. A preview failure does not indicate uncertain trade execution.
No brokerage mutation tool ships yet.

## Tool guidance

MCP `tools/list` exposes usage descriptions, input field guidance (including
nested order fields), and complete synthetic argument examples. View these in
MCP Inspector or your client's discovery response. Hosts decide how to present
descriptions and schema examples to their models; the server's input validation
still applies independently.

Examples show request structure, not current contracts, market prices, account
eligibility, or authenticated broker acceptance. Use your own account identifiers
and broker-listed contracts. Omit unused optional objects or use null, especially
`disclosure` and `mf_quantity`: explicit objects are preserved even when their
children are all null, and the broker may reject the resulting empty objects.
False and zero values are preserved where the client supports them.

General and specialized previews return the complete broker response under
`data.broker_preview` and reusable placement inputs under `data.placement_arguments`.
No execution tools have been added.

## Order previews and host review

`orders_preview` accepts an account ID key and a required complete client preview
request under `request`. `orders_preview_change` takes the same fields plus a
positive integer `order_id` identifying the existing order. A change preview is
a complete replacement request, not a patch. For example:

```json
{
  "account_id_key": "account-key",
  "request": {
    "order_type": "EQ",
    "client_order_id": "ExamplePreview1",
    "orders": [{
      "price_type": "LIMIT",
      "limit_price": "10.125",
      "order_term": "GOOD_FOR_DAY",
      "instruments": [{
        "product": {"symbol": "SYN", "security_type": "EQ"},
        "order_action": "BUY",
        "quantity": "1"
      }]
    }]
  }
}
```

Use Python field names as advertised by discovery, or client-supported aliases
such as `orderType`, `clientOrderId`, `Order`, `Instrument`, and `Product`.
Conflicting duplicate spellings are rejected. All modeled prices, strikes,
quantities, lot sizes, and mutual-fund amounts require decimal strings. The
client's unused empty `stop_price` placeholder remains supported. Multiple order
entries and instruments, alternate quantity types, lots, disclosures, routing,
and supported order-detail/instrument extensions pass through the public client
models. Product, lot, mutual-fund quantity, disclosure, and outer request models
reject unknown fields instead of silently losing them.

All previews return `data.broker_preview` with the complete client-modeled broker
preview, including `PreviewIds`, `Order`, estimated amounts, disclosures, and
warnings. `data.placement_arguments` contains `account_id_key` and a complete
broker-aliased `PlaceOrderRequest` under `request`, constructed from the actual
normalized preview request plus every returned numeric preview ID, in broker
order. Change previews also include `order_id`. Preview-ID response metadata is
not copied into the placement request. Supported order extensions, false/zero
values, and decimal precision are preserved; client broker metadata is stripped.

The adapter does not create
an operation handle, save a pending order, generate a client order ID, associate
previews across calls, or submit an order. Each valid, permitted call invokes the
selected client preview method once. Client previews use no automatic retries, including
on rate limits, server errors, malformed responses, or timeouts. A restart does
not recover an earlier result or automatically redispatch a preview.

The consuming host must retain the complete request, including extensions, with
its broker preview IDs, timestamp, and warnings; display it for review; and own
freshness and human approval. A preview or an execution capability switch is not
approval. Material request changes require renewed review and approval and a new
preview as required by the broker and host policy. Multi-leg requests may include
closing and opening legs, but the server performs no roll orchestration or
multi-order rollback. For a change preview, the host must also verify the exact
account/order target. Placement and change placement remain future tools.

## Specialized order previews

Choose the families you use through `--tool-allowlist`. Selection does not
implicitly enable companion tools. For example, an equity-only process can use:

```sh
uv run --frozen etrade-mcp serve \
  --tool-allowlist server_status,accounts_list,market_get_quote,orders_list,orders_preview_equity,orders_preview_change_equity
```

For single-option workflows, select `orders_preview_single_option` and
`orders_preview_change_single_option` plus the market/account tools you need.
Omitting the allowlist exposes all 34 implemented tools. Configure separate
processes when consumers need different tool exposure.

Every new preview accepts `{account_id_key, request}`. Every change preview
accepts `{account_id_key, order_id, request}` and requires a complete replacement,
not a patch. No existing order is fetched implicitly. The broker decides which
fields of a working order can be changed, including spread/buy-write quantities.

Synthetic equity example for `orders_preview_equity`:

```json
{
  "account_id_key": "synthetic-key",
  "request": {
    "client_order_id": "ExampleEquity001",
    "symbol": "SYN",
    "order_action": "BUY",
    "quantity": "100",
    "price_type": "LIMIT",
    "limit_price": "5.00"
  }
}
```

For `orders_preview_change_equity`, add the existing `order_id` at the top level
and supply the entire desired request. Defaults are `GOOD_FOR_DAY` and `REGULAR`.
All families accept optional `all_or_none`, preserving explicit `false`.

Equity and single options support MARKET, LIMIT, STOP, and STOP_LIMIT. LIMIT
requires `limit_price`; STOP requires `stop_price`; STOP_LIMIT requires both.
Combinations support NET_DEBIT and NET_CREDIT with a positive `limit_price`
magnitude on the broker pricing basis, or NET_EVEN with no price. Omit unused
prices or use null. All prices, strikes, and quantities are positive finite
decimal strings; option quantities must be whole contracts. Use actual listed
expirations in YYYY-MM-DD format and explicit contract strikes and rights.

Named combinations require `position_effect`: OPEN or CLOSE. Their strike roles
always describe the opening structure. CLOSE reverses every opening BUY role
to SELL_CLOSE and every SELL role to BUY_CLOSE. Wing structures also require
`wing_action`: BUY or SELL for the opening outer legs. No debit/credit, contract,
price, holding, or strategy is inferred.

Buy-writes open stock BUY plus call SELL_OPEN, with independent stock/option
quantities and no assumed multiplier. Paired unwinds use the general tools.
Specialized tools omit advanced terms, routing, lots, disclosures, reserve/OSI
metadata, additional extensions, alternate sizing, multiple entries, and mixed
opening/closing adjustments. These remain available in `orders_preview` and
`orders_preview_change`. Broker acceptance and account eligibility remain broker
responsibilities. Every tool advertises its precise fields and synthetic example.

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
| `orders.preview` | `orders_preview` | Implemented | `PreviewOrderRequest` | [Preview mapping, nested fields, permissions, and no-retry tests](tests/test_previews.py) |
| `orders.place` | `orders_place` | Planned | `PlaceOrderRequest` | — |
| `orders.preview_change` | `orders_preview_change` | Implemented | `PreviewOrderRequest` | [Explicit target, replacement bodies, and protocol tests](tests/test_previews.py) |
| `orders.place_change` | `orders_place_change` | Planned | `PlaceOrderRequest` | — |
| `orders.cancel` | `orders_cancel` | Planned | `CancelOrderRequest` | — |
| `alerts.list` | `alerts_list` | Implemented | `AlertsRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `alerts.get` | `alerts_get` | Implemented | `AlertDetailsRequest` | [Request mapping and field coverage](tests/test_reads.py) |
| `alerts.delete` | `alerts_delete` | Planned | — | — |
| `portfolio.iter_positions` | — | Omitted | — | Use explicit single-page tools; no automatic aggregation. |
| `transactions.list_all` | — | Omitted | — | Use explicit single-page tools; no automatic aggregation. |
| `orders.list_all` | — | Omitted | — | Use explicit single-page tools; no automatic aggregation. |

The specialized tools below all call `orders.preview` or `orders.preview_change`
with public `PreviewOrderRequest` models. New/change request mappings, general
parity, native errors, HTTP/stdio schemas, and permissions are covered by
[tests/test_specialized_previews.py](tests/test_specialized_previews.py), with
synthetic expected bodies in [tests/specialized_cases.py](tests/specialized_cases.py).

| Family | New preview | Change preview | Construction / limitations |
| --- | --- | --- | --- |
| Equity | `orders_preview_equity` | `orders_preview_change_equity` | One EQ leg; explicit equity action. |
| Single option | `orders_preview_single_option` | `orders_preview_change_single_option` | One OPTN leg; explicit right, expiration, strike, and action. |
| Buy-write | `orders_preview_buy_write` | `orders_preview_change_buy_write` | Equity BUY + call SELL_OPEN; independent quantities; opening only. |
| Vertical | `orders_preview_vertical` | `orders_preview_change_vertical` | Two distinct strikes, same right/expiration, equal quantities. |
| Butterfly | `orders_preview_butterfly` | `orders_preview_change_butterfly` | Three ascending equally spaced strikes; same right; 1:2:1. |
| Condor | `orders_preview_condor` | `orders_preview_change_condor` | Four ascending strikes; same right; 1:1:1:1; unequal wing widths allowed. |
| Iron butterfly | `orders_preview_iron_butterfly` | `orders_preview_change_iron_butterfly` | Put/put/call/call; shared middle strike; equal wing widths and quantities. |
| Iron condor | `orders_preview_iron_condor` | `orders_preview_change_iron_condor` | Ascending put/put/call/call; equal quantities; unequal wing widths allowed. |
| Call spread + short put | `orders_preview_call_spread_short_put` | `orders_preview_change_call_spread_short_put` | BUY call / SELL call / SELL put opening roles; same expiration, equal quantities. |

OAuth login, verifier exchange, explicit renewal and revocation remain in the
`etrade` CLI. Automatic client lifecycle management remains active.

The cases in [tests/read_cases.py](tests/read_cases.py) enumerate every supported
read request field. `test_read_request_fields_reach_real_client` verifies their
final HTTP paths and query parameters using the real client;
`test_request_cases_cover_public_client_fields` checks those cases against the
public request models. `test_preview_nested_field_coverage_and_schema` in
[tests/test_previews.py](tests/test_previews.py) checks every public preview request
field, including nested models. Its protocol cases cover equity, options, verticals,
three-leg orders, iron condors, buy-writes, mixed closing/opening legs, multiple
order entries, and alternate sizing. Fixtures are synthetic client-valid contracts,
not evidence that the broker accepts every combination. Mutation coverage follows
in later milestones.

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
