# etrade-mcp

E*TRADE, one tool call away.

etrade-mcp connects MCP-compatible agents and applications to the typed, async
[etrade-python client](https://pypi.org/project/etrade-python/). Read accounts and
markets, inspect option contracts, and build precise order previews without
embedding brokerage logic in your harness.

**Current release: 0.1.0.** Install `etrade-mcp` from PyPI. Interfaces may evolve
before 1.0.

## Start here

1. [Install and authenticate](getting-started.md) with the client CLI.
2. [Connect your MCP host](connections.md) through loopback HTTP or stdio.
3. [Choose the tools you need](workflows.md), from focused equities to the full catalog.
4. [Preview orders](previews.md) and review the broker's complete response.

## What is available?

| Capability | Tools |
| --- | --- |
| Accounts, positions, transactions, market data, orders, and alerts | 13 brokerage reads |
| General and nine specialized families, each with new/change previews | 20 previews |
| Local versions, permissions, and credential estimate | `server_status` |
| Explicitly enabled placement, change placement, cancellation, and alert deletion | 4 mutations |

That is **34 tools by default**, or **38 with both execution capabilities enabled**.
Exact-name allowlists let each host expose only the tools it needs. See the
[coverage matrix](reference/tool-coverage.md) for public client methods, request
models, test evidence, and intentional omissions.

## Execution belongs to the host

Execution defaults off. Preview is separate from placement, and neither a startup
switch nor an LLM statement establishes human approval. The trusted host owns
exact-request review, approval, submission history, and reconciliation after an
uncertain result. See [execution tools](execution.md) before enabling mutations.
Strategies, scheduling, and portfolio decisions stay outside this package.

## Reference and troubleshooting

- [Configuration and permission boundaries](configuration.md)
- [Tool results, broker errors, and validation details](reference/responses.md)
- [Pagination, precision, and response sizes](reference/reads.md)
- [Redacted diagnostic logging](diagnostics.md)
- [Optional local Linux service](service.md)

## Development and verification

Python 3.11–3.14 are supported. Tests exercise real MCP stdio/loopback HTTP
messages and real client serialization with synthetic broker HTTP responses.
They do not establish authenticated broker acceptance, model reliability, or
strategy correctness. Wheel and sdist checks install independently outside the
checkout. No live orders or package publication are part of those checks.

The [contributor guide](https://github.com/kevinrider/etrade-mcp/blob/main/CONTRIBUTING.md)
contains environment setup, lint/type/test commands, coverage requirements,
parallel/serial test options, and distribution verification.

## Project

- [Security and private vulnerability reporting](https://github.com/kevinrider/etrade-mcp/blob/main/SECURITY.md)
- [Changelog](https://github.com/kevinrider/etrade-mcp/blob/main/CHANGELOG.md)
- [Source and issues](https://github.com/kevinrider/etrade-mcp)

Apache-2.0. This project is not affiliated with or endorsed by E*TRADE or Morgan
Stanley.
