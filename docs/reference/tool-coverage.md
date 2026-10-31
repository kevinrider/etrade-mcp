# Tool coverage

Supported client dependency: `etrade-python>=1.1,<2`. The matrix lists implemented
operations and intentional omissions. Test links open the file containing the named test.

| Client operation | MCP tool | Status | Request model | Tests / notes |
| --- | --- | --- | --- | --- |
| `session.load`, `session.status` | `server_status` | Implemented | — | [test_status_protocol_and_strict_schema](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_server.py)<br>[test_actual_http_discovery_invocation_and_concurrency](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_http.py)<br>[test_actual_stdio_cli_protocol_and_stdout](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_cli.py) |
| `accounts.list` | `accounts_list` | Implemented | — | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `accounts.get_balance` | `accounts_get_balance` | Implemented | `AccountBalanceRequest` | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `portfolio.get_positions` | `portfolio_get_positions` | Implemented | `PortfolioRequest` | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `transactions.list` | `transactions_list` | Implemented | `TransactionsRequest` | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `transactions.get` | `transactions_get` | Implemented | `TransactionDetailsRequest` | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `market.get_quote` | `market_get_quote` | Implemented | `QuotesRequest` | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `market.get_quotes` | `market_get_quotes` | Implemented | `QuotesRequest` | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `market.lookup_product` | `market_lookup_product` | Implemented | `ProductLookupRequest` | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `market.get_option_expirations` | `market_get_option_expirations` | Implemented | `OptionExpirationsRequest` | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `market.get_option_chain` | `market_get_option_chain` | Implemented | `OptionChainRequest` | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `orders.list` | `orders_list` | Implemented | `OrdersRequest` | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `orders.preview` | `orders_preview` | Implemented | `PreviewOrderRequest` | [Preview mapping, nested fields, permissions, and no-retry tests](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_previews.py) |
| `orders.place` | `orders_place` | Implemented | `PlaceOrderRequest` | [Mapping, permissions, ambiguity, and no-retry tests](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_mutations.py) |
| `orders.preview_change` | `orders_preview_change` | Implemented | `PreviewOrderRequest` | [Explicit target, replacement bodies, and protocol tests](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_previews.py) |
| `orders.place_change` | `orders_place_change` | Implemented | `PlaceOrderRequest` | [Mapping, permissions, ambiguity, and no-retry tests](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_mutations.py) |
| `orders.cancel` | `orders_cancel` | Implemented | `CancelOrderRequest` | [Mapping, permissions, ambiguity, and no-retry tests](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_mutations.py) |
| `alerts.list` | `alerts_list` | Implemented | `AlertsRequest` | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `alerts.get` | `alerts_get` | Implemented | `AlertDetailsRequest` | [Request mapping and field coverage](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_reads.py) |
| `alerts.delete` | `alerts_delete` | Implemented | — | [Mapping, permissions, ambiguity, and no-retry tests](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_mutations.py) |
| `portfolio.iter_positions` | — | Omitted | — | Use explicit single-page tools; no automatic aggregation. |
| `transactions.list_all` | — | Omitted | — | Use explicit single-page tools; no automatic aggregation. |
| `orders.list_all` | — | Omitted | — | Use explicit single-page tools; no automatic aggregation. |

The specialized tools below all call `orders.preview` or `orders.preview_change`
with public `PreviewOrderRequest` models. New/change request mappings, general
parity, native errors, HTTP/stdio schemas, and permissions are covered by
[tests/test_specialized_previews.py](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_specialized_previews.py), with
synthetic expected bodies in [tests/specialized_cases.py](https://github.com/kevinrider/etrade-mcp/blob/main/tests/specialized_cases.py).

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

The cases in [tests/read_cases.py](https://github.com/kevinrider/etrade-mcp/blob/main/tests/read_cases.py) enumerate every supported
read request field. `test_read_request_fields_reach_real_client` verifies their
final HTTP paths and query parameters using the real client;
`test_request_cases_cover_public_client_fields` checks those cases against the
public request models. `test_preview_nested_field_coverage_and_schema` in
[tests/test_previews.py](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_previews.py) checks every public preview request
field, including nested models. Its protocol cases cover equity, options, verticals,
three-leg orders, iron condors, buy-writes, mixed closing/opening legs, multiple
order entries, and alternate sizing. Fixtures are synthetic client-valid contracts,
not evidence that the broker accepts every combination. Mutation mapping,
permissions, partial failures, and uncertain outcomes are covered by
[tests/test_mutations.py](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_mutations.py).

The final protocol audit in [tests/test_protocol_audit.py](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_protocol_audit.py)
adds every read operation over actual stdio in both supported protocol modes,
focused/full/empty catalog enforcement over both transports, explicit pagination
through terminal empty pages, HTTP socket loss after dispatch, and killed-process
restart without mutation replay. Its recovery reads and explicit repeated calls
use synthetic broker responses; they do not establish actual execution or fills.
Existing HTTP access-control, response-contract, logging, and large-response tests
remain in [tests/test_http.py](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_http.py),
[tests/test_response_contract.py](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_response_contract.py),
[tests/test_tool_logging.py](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_tool_logging.py), and
[tests/test_large_responses.py](https://github.com/kevinrider/etrade-mcp/blob/main/tests/test_large_responses.py).
