# Connecting MCP clients

These examples configure the existing tools; they do not provide a trading
strategy or a human-approval controller. Install the package and complete broker
OAuth as described in the [README](README.md#install-and-authenticate) first.
Use the same sandbox/production environment and profile for login and serving.

Choose HTTP or stdio for a given server entry. Start a fresh client session after
changing configuration. `etrade-mcp` must be on the launching user's PATH; replace
it with an absolute executable path if needed. Desktop clients may not inherit
terminal environment variables. Supply secrets through the client's protected
launch environment, never in a prompt or committed configuration.

## HTTP: start the server separately

Provide `ETRADE_CONSUMER_KEY`, `ETRADE_CONSUMER_SECRET`, and
`ETRADE_MCP_HTTP_BEARER_TOKEN` through protected process configuration. Keep one
stable bearer value for the server and authorized clients; generating a different
value in each shell will fail authentication. This example exposes only local
status and market reads, with both mutation capabilities explicitly disabled:

```sh
etrade-mcp serve --transport streamable-http --environment sandbox --profile default \
  --no-enable-order-execution --no-enable-alert-deletion \
  --tool-allowlist server_status,market_get_quote,market_get_quotes,market_lookup_product,market_get_option_expirations,market_get_option_chain
```

The endpoint is `http://127.0.0.1:8000/mcp`. HTTP clients need its bearer token;
they do not need broker credentials. The server owns broker OAuth. No MCP OAuth
login is required or provided. Clients must reach the same machine/network
namespace's loopback endpoint; `127.0.0.1` inside a separate container or remote
host is not the host endpoint. Non-loopback binding and hosted proxy deployment
are outside this server's supported configuration.

### Codex

Add this table to `~/.codex/config.toml`. It references the token variable rather
than storing its value:

```toml
[mcp_servers.etrade]
url = "http://127.0.0.1:8000/mcp"
bearer_token_env_var = "ETRADE_MCP_HTTP_BEARER_TOKEN"
```

Alternatively, let Codex launch the same market-only scope through stdio:

```toml
[mcp_servers.etrade]
command = "etrade-mcp"
args = ["serve", "--transport", "stdio", "--environment", "sandbox", "--profile", "default", "--no-enable-order-execution", "--no-enable-alert-deletion", "--tool-allowlist", "server_status,market_get_quote,market_get_quotes,market_lookup_product,market_get_option_expirations,market_get_option_chain"]
env_vars = ["ETRADE_CONSUMER_KEY", "ETRADE_CONSUMER_SECRET"]
```

Use one table for `etrade`, not both. Codex documents these settings in its
[official MCP configuration guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

### Claude Code

For a project-scoped HTTP connection, put this in `.mcp.json`; Claude Code expands
the token reference from its launch environment:

```json
{
  "mcpServers": {
    "etrade": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "Authorization": "Bearer ${ETRADE_MCP_HTTP_BEARER_TOKEN}"
      }
    }
  }
}
```

For stdio, replace that entry with:

```json
{
  "mcpServers": {
    "etrade": {
      "type": "stdio",
      "command": "etrade-mcp",
      "args": [
        "serve", "--transport", "stdio", "--environment", "sandbox", "--profile", "default",
        "--no-enable-order-execution", "--no-enable-alert-deletion",
        "--tool-allowlist", "server_status,market_get_quote,market_get_quotes,market_lookup_product,market_get_option_expirations,market_get_option_chain"
      ],
      "env": {
        "ETRADE_CONSUMER_KEY": "${ETRADE_CONSUMER_KEY}",
        "ETRADE_CONSUMER_SECRET": "${ETRADE_CONSUMER_SECRET}"
      }
    }
  }
}
```

Before launching a stdio client, remove inherited HTTP-only settings:

```sh
unset ETRADE_MCP_HTTP_BEARER_TOKEN ETRADE_MCP_HOST ETRADE_MCP_PORT
```

Stdio rejects these settings rather than silently ignoring them. Use a separate
shell/session if another HTTP connection needs the bearer variable. In Claude
Code, `/mcp` shows connection status and available tools. Configuration and
variable expansion follow the [official MCP guide](https://code.claude.com/docs/en/mcp).

## Generic Python MCP client

In an environment containing the package dependencies, this HTTP example lists
tools and invokes status only. It does not send a brokerage request:

```python
import asyncio
import os
from contextlib import asynccontextmanager

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


@asynccontextmanager
async def connection(http):
    async with streamable_http_client("http://127.0.0.1:8000/mcp", http_client=http) as streams:
        yield streams[0], streams[1]


async def main():
    async with httpx2.AsyncClient(
        headers={"Authorization": "Bearer " + os.environ["ETRADE_MCP_HTTP_BEARER_TOKEN"]},
        trust_env=False,
    ) as http:
        async with Client(connection(http)) as client:
            print([tool.name for tool in (await client.list_tools()).tools])
            result = await client.call_tool("server_status", {})
            if result.is_error:
                raise RuntimeError("Status failed; inspect structured error details privately.")
            print(result.structured_content)


asyncio.run(main())
```

For equivalent stdio scope, replace the HTTP connection with:

```python
import os
from mcp import Client
from mcp.client.stdio import StdioServerParameters

parameters = StdioServerParameters(
    command="etrade-mcp",
    args=[
        "serve",
        "--transport",
        "stdio",
        "--environment",
        "sandbox",
        "--profile",
        "default",
        "--no-enable-order-execution",
        "--no-enable-alert-deletion",
        "--tool-allowlist",
        "server_status,market_get_quote,market_get_quotes,market_lookup_product,market_get_option_expirations,market_get_option_chain",
    ],
    env={
        "ETRADE_CONSUMER_KEY": os.environ["ETRADE_CONSUMER_KEY"],
        "ETRADE_CONSUMER_SECRET": os.environ["ETRADE_CONSUMER_SECRET"],
    },
)
# Inside an async function:
# async with Client(parameters) as client:
#     result = await client.call_tool("server_status", {})
```

Do not assume every client's JSON configuration expands `${VARIABLE}`. That
syntax above is specific to Claude Code; Codex has named environment-reference
fields, and Python reads `os.environ`. HTTP headers must contain the resolved
bearer value. Verify each client adapter's behavior before supplying secrets.

These configurations are checked against official client documentation and the
server's protocol tests; they are not a claim that every client/version/model has
been manually validated. See the README for synthetic order examples and the
[execution boundary](README.md#configuration-and-execution-boundary).

## Optional Linux user service for local HTTP

A foreground server is sufficient. If using systemd, run a user service under the
same OS user and keyring backend used for `etrade auth login`. Create a private
configuration directory and environment file; do not commit its contents:

```sh
install -d -m 700 "$HOME/.config/etrade-mcp"
touch "$HOME/.config/etrade-mcp/environment"
chmod 600 "$HOME/.config/etrade-mcp/environment"
```

Populate the file privately with environment assignments (not shell commands), including broker credentials, the selected environment, and the HTTP
bearer token. It is loaded by systemd, not by the adapter. A structural template:

```text
ETRADE_CONSUMER_KEY=replace-with-issued-key
ETRADE_CONSUMER_SECRET=replace-with-issued-secret
ETRADE_ENVIRONMENT=sandbox
ETRADE_MCP_HTTP_BEARER_TOKEN=replace-with-one-generated-token
```

Place a unit at `~/.config/systemd/user/etrade-mcp.service`, adjusting `ExecStart`
to the installed executable path (`uv tool dir --bin` locates the tool directory):

```ini
[Unit]
Description=Local E*TRADE MCP server

[Service]
Type=simple
EnvironmentFile=%h/.config/etrade-mcp/environment
ExecStart=%h/.local/bin/etrade-mcp serve --transport streamable-http --environment sandbox --profile default --no-enable-order-execution --no-enable-alert-deletion
Restart=on-failure

[Install]
WantedBy=default.target
```

Then use `systemctl --user daemon-reload` and
`systemctl --user enable --now etrade-mcp`. Check status with
`systemctl --user status etrade-mcp` and logs with
`journalctl --user -u etrade-mcp`; stop it with
`systemctl --user disable --now etrade-mcp`.

An interactive desktop keyring may be unavailable or locked in a user service or
at boot. Verify backend/session access; do not substitute a plaintext credential
store to work around that. Perform OAuth login interactively outside the unit,
with matching credentials/environment/profile. Expired credentials require a new
login. Restarting the service cannot recover a lost execution outcome or replay
an order; the host still owns reconciliation. No service is installed or enabled
by package installation.
