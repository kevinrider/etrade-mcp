# Security

etrade-mcp exposes brokerage information and can submit, modify, cancel orders,
or delete alerts when execution permissions are enabled. Tool results can contain
private account data. The current release is 0.1.0. Before 1.0, interfaces may
change between releases.

## Reporting vulnerabilities

Do not include credentials, account identifiers, order details, or sensitive logs
in public issues. Use [GitHub private vulnerability reporting](https://github.com/kevinrider/etrade-mcp/security/advisories/new)
if enabled. If that option is unavailable, open an issue requesting a private
contact without disclosing vulnerability details. No dedicated security email has
been published. Report the affected package/client versions and transport through
that private channel.

## Credentials and private data

Broker OAuth signing, token lifecycle, and credential storage belong to
etrade-python. Use the same OS user, environment, consumer key, and profile for
interactive login and the server. Cooperating processes need client 1.1 or later
and the same credential-lock directory; old clients/direct store writes bypass
coordination. Keyring protection depends on the selected backend. The adapter
neither encrypts its own credential files nor loads `.env` automatically.

Supply consumer credentials and HTTP bearer tokens through protected process
configuration. Do not put them in prompts, arguments, repository files, or example
recordings. Bearer access is separate from broker OAuth; etrade-mcp does not host
an OAuth authorization server. `server_status` reports a local credential estimate,
not an authenticated broker verification.

Broker responses intentionally include account data. A hosted model, harness,
extension, chat history, or transcript store may receive and retain that data.
Choose those consumers and their data policies deliberately. Error diagnostics
redact known secrets and bound text, but broker messages can still contain other
personal information. Do not forward or log results wholesale.

Tool-call logging is off by default. When enabled, schema-selected argument
values such as symbols, prices, quantities, and order settings may be visible;
identifiers and secret-like fields are masked and broker results are excluded.
Treat diagnostics as sensitive. Stdout remains reserved for stdio protocol
traffic. HTTP access logging is disabled. External wire logging, custom hooks,
debuggers, or a process with access to the same user account can bypass these
protections; redaction is not a sandbox.

## Access and execution

HTTP binds only to a loopback IP and requires a bearer token on every request,
with Host/Origin checks. It has no multi-user isolation, remote TLS service,
reverse-proxy support, or arbitrary cross-origin browser access. All authorized
callers share that process's profile and tool permissions. Stdio inherits the
trust boundary of the host that launches it. Use separate processes/scopes where
needed; tool annotations and client-side hiding are not access controls.

Order execution and alert deletion default off. Startup capability switches and
server allowlists control execution access, not approval of an individual action.
A trusted host must obtain human approval for each opening, closing, modification,
cancellation, and roll, binding it to exact account/order targeting and complete
request/preview inputs. LLM statements or approval flags do not attest approval.
A harness with shell access or broker credentials must also be constrained by its
host; an MCP allowlist does not restrict that harness's other capabilities.

The host owns client-order-ID uniqueness, freshness, durable attempt history, and
reconciliation. Use a new ID for each new order or modification, retaining it
through its corresponding preview/placement pair. Mutations are dispatched at
most once per invocation. An explicit repeated call is another attempt; no server
execution journal, deduplication store, or restart replay exists. A timeout,
disconnect, cancellation, lost response, or malformed acknowledgment cannot prove
that a broker operation did not occur. Reconcile before deciding to resubmit, and
do not automatically generate new IDs or previews to bypass an error. Broker
acceptance and cancellation acknowledgments do not establish fills or rollback.

Alert deletion can partially succeed. Inspect retained failed IDs and reconcile
before another attempt; do not automatically repeat an entire batch.

## Validation and distribution

Default tests use synthetic data and real client serialization over mocked broker
HTTP; protocol tests use stdio or loopback sockets. They do not establish broker
acceptance of every request, authenticated execution behavior, model reliability,
or strategy correctness. Do not place live orders as part of development.

Use the documented release workflow and review artifact provenance. PyPI publishing
uses GitHub OIDC and the `pypi` environment rather than a long-lived API token.
