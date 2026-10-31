# Install and authenticate

Install the published package with Python 3.11+ and uv:

```sh
uv tool install --with-executables-from etrade-python etrade-mcp
etrade-mcp --version
etrade --version
```

uv builds the package and exposes both `etrade-mcp` and the client's `etrade`
authentication CLI from the same isolated tool environment. If you already have
a compatible `etrade` CLI installed (`etrade-python>=1.1,<2`), use
`uv tool install etrade-mcp` to keep that executable and avoid a conflict. For
development, use the setup commands in
[CONTRIBUTING.md](https://github.com/kevinrider/etrade-mcp/blob/main/CONTRIBUTING.md) and launch with `uv run etrade-mcp` instead.

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
