# Tool and result contract

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
    "request_id": null,
    "validation_errors": [],
    "alert_deletion_result": null
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
  "request_id": null,
  "validation_errors": [],
  "alert_deletion_result": null
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
Brokerage mutations require explicit startup permissions; see [Execution tools](../execution.md).

## Local validation diagnostics

Before a broker request, invalid inputs return `isError: true`, `code: invalid_input`,
and safe correction details under `error.validation_errors`. For example, an
invalid equity quantity can produce this error-object excerpt:

```json
{
  "code": "invalid_input",
  "message": "Tool arguments are invalid.",
  "validation_errors": [
    {
      "path": ["request", "quantity"],
      "code": "greater_than",
      "message": "Must be greater than 0."
    }
  ]
}
```

Paths use canonical Python field names and zero-based array indices, even when
arguments used client aliases. A cross-field rule may point to its containing
object, such as `["request"]` for a missing limit price. Details cover missing
fields, incorrect types, decimal strings, supported choices, order price rules,
expiration dates, option quantities, and strike relationships. Recognized client
validation failures before HTTP dispatch use the same structure. Unrecognized
reasons receive safe generic guidance; reported details are not a promise that
all invalid combinations have been found in one pass.

The server never includes submitted values, unknown field names, arbitrary
exception messages/context, or internal union labels in these details. Unknown
keys point to the nearest recognized parent. Details are deduplicated and limited
to 20 entries; if more remain, the last entry is an omission notice. Paths contain
at most 16 components and messages at most 256 characters. Non-validation errors
have an empty list; local validation errors have no broker message. Protocol-level
JSON-RPC errors keep their existing format. This diagnostic change does not alter
accepted inputs, tool permissions, broker requests, or retry behavior.
