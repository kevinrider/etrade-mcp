# Order previews

## Tool guidance

MCP `tools/list` exposes usage descriptions, input field guidance (including
nested order fields), and complete synthetic argument examples. View these in
[MCP Inspector](https://github.com/modelcontextprotocol/inspector) or your client's
discovery response. Hosts decide how to present
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
Shared placement, change-placement, cancellation, and alert-deletion tools are
available under explicit startup permissions; see [Execution tools](execution.md).

## Complete preview requests and host review

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

Preview tools do not create an operation handle, save a pending order, generate a client order ID, associate
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
account/order target. Use the shared [placement tools](execution.md) only after host approval.

## Specialized order previews

Choose the families you use through `--tool-allowlist`. Selection does not
implicitly enable companion tools. For example, an equity-only process can use:

```sh
uv run --frozen etrade-mcp serve \
  --tool-allowlist server_status,accounts_list,market_get_quote,orders_list,orders_preview_equity,orders_preview_change_equity
```

For single-option workflows, select `orders_preview_single_option` and
`orders_preview_change_single_option` plus the market/account tools you need.
Omitting the allowlist exposes all capability-permitted tools: 34 by default,
37 with order execution, 35 with alert deletion, and 38 with both enabled.
Configure separate processes when consumers need different tool exposure.

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
