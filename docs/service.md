# Optional Linux user service for local HTTP

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
