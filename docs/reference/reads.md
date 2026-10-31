# Read inputs and pagination

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
