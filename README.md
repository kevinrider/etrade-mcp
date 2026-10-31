# etrade-mcp

<div align="center">
<a href="https://github.com/kevinrider/etrade-mcp/releases"><img src="https://img.shields.io/github/release/kevinrider/etrade-mcp.svg?style=flat-square" alt="Latest Version"></a>
<a href="https://github.com/kevinrider/etrade-mcp/actions/workflows/ci.yml"><img src="https://github.com/kevinrider/etrade-mcp/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://github.com/kevinrider/etrade-mcp/issues"><img src="https://img.shields.io/github/issues/kevinrider/etrade-mcp" alt="GitHub issues"></a>
<a href="https://github.com/kevinrider/etrade-mcp/blob/main/LICENSE"><img src="https://img.shields.io/github/license/kevinrider/etrade-mcp" alt="License"></a>
</div>

**E*TRADE, one tool call away.**

Give your agent a brokerage toolkit: accounts, quotes, positions, option chains, and order
management, through a typed Python MCP server backed by
[etrade-python](https://pypi.org/project/etrade-python/).

[Documentation](https://kevinrider.github.io/etrade-mcp/) ·
[Tool coverage](https://kevinrider.github.io/etrade-mcp/reference/tool-coverage/) ·
[Client setup](https://kevinrider.github.io/etrade-mcp/connections/) ·
[Changelog](https://github.com/kevinrider/etrade-mcp/blob/main/CHANGELOG.md)

## A toolkit that fits your harness

- **Read the account.** Balances, positions, transactions, orders, and alerts.
- **Explore the market.** Quotes, product lookup, option expirations, and chains.
- **Preview precisely.** Equity, single options, buy-writes, spreads, butterflies,
  condors, and general multi-leg requests—with monetary values kept as decimal strings.
- **Choose your tools.** Expose a focused allowlist or the complete catalog.
- **Connect your way.** Local stdio or authenticated loopback Streamable HTTP.

There are **34 tools by default**: 13 brokerage reads, 20 new/change previews,
and `server_status`. Explicitly enabling order execution and alert deletion
brings the complete catalog to **38 tools**. Strategy, scheduling, and portfolio
decisions stay in your application.

## Get started

Requires **Python 3.11–3.14** and [uv](https://docs.astral.sh/uv/).

```sh
uv tool install --with-executables-from etrade-python etrade-mcp
etrade-mcp --version
etrade --version
```

This exposes both the server and the client's OAuth CLI. Already have a
compatible `etrade` executable? See the
[installation guide](https://kevinrider.github.io/etrade-mcp/getting-started/)
for that setup.

Provide `ETRADE_CONSUMER_KEY` and `ETRADE_CONSUMER_SECRET` through your protected
process environment, using keys issued for the selected broker environment.
Then log in interactively:

```sh
export ETRADE_ENVIRONMENT=sandbox
etrade auth login --profile default
```

Start local HTTP with a generated bearer credential in your private shell:

```sh
export ETRADE_MCP_HTTP_BEARER_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
etrade-mcp serve --environment sandbox --profile default \
  --no-enable-order-execution --no-enable-alert-deletion
```

Connect your host to `http://127.0.0.1:8000/mcp`, using that same bearer token.
For Codex, Claude Code, generic Python, or stdio, follow the
[connection examples](https://kevinrider.github.io/etrade-mcp/connections/).
Broker OAuth and the MCP bearer credential serve different purposes; keep both
out of prompts and committed configuration.

## Ask your agent

Once connected and authenticated, try:

> Get the AAPL quote. Report the last trade price, bid, ask, quote status, and
> broker timestamp exactly as returned.

Then explore [workflow recipes](https://kevinrider.github.io/etrade-mcp/workflows/)
and [order previews](https://kevinrider.github.io/etrade-mcp/previews/).
Each tool advertises its input schema, field descriptions, and synthetic examples.
You can also inspect these directly in [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

## Preview first. Execute deliberately.

**Execution is disabled by default.** Previews do not place orders.
The consuming host must obtain human approval bound to the exact account,
request, and preview before invoking an execution tool. A model's approval flag
or a server capability switch does not establish that approval.

The host also owns submission history and reconciliation after uncertain
outcomes. See the [execution guide](https://kevinrider.github.io/etrade-mcp/execution/)
for permissions, client-order-ID lifecycle, cancellations, and recovery.

## Under the hood

Thin adapters call the public async client APIs. Both transports expose the same
validated tools and structured responses, with native MCP error signaling.
Brokerage behavior, OAuth, and coordinated credential storage stay in
`etrade-python>=1.1,<2`.

Offline tests cover actual MCP messages and real client serialization with mocked
broker HTTP. Built wheel/sdist checks run outside the checkout. These checks do
not establish broker acceptance of every order or reliability of every model.

## Join in

[Contributing](https://github.com/kevinrider/etrade-mcp/blob/main/CONTRIBUTING.md) ·
[Issues](https://github.com/kevinrider/etrade-mcp/issues) ·
[Security](https://github.com/kevinrider/etrade-mcp/blob/main/SECURITY.md)

Apache-2.0. This project is not affiliated with or endorsed by E*TRADE or Morgan
Stanley.
