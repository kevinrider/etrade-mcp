# Contributing

Contributions to etrade-mcp are welcome. For a bug report, include steps to
reproduce it, expected and actual behavior, and the Python and package versions.
Discuss substantial features or architecture changes in an issue before starting
implementation so the proposed change can be agreed on with maintainers.

## Set up a development environment

Fork the repository on GitHub, clone your fork, and create a branch for your
change. Install Python 3.11+ and uv, then run these commands from the repository
root:

```sh
uv sync --extra dev --frozen
uv run --frozen etrade-mcp --version
```

No E*TRADE credentials or authenticated broker access are needed to run the test
suite. See the [README](README.md) for server configuration and manual usage.

uv selects an available compatible Python interpreter. To select one explicitly,
set `UV_PYTHON`, for example `export UV_PYTHON=3.11`, before running setup and
checks. CI validates Python 3.11–3.14.

The committed `uv.lock` records development dependency versions. `--frozen` uses
that lockfile without updating it. When changing dependencies, update
`pyproject.toml`, run `uv lock`, and include the updated lockfile in your pull
request.

## Make changes

Keep changes focused on the problem being addressed and add relevant tests for
new behavior or bug fixes. Update user-facing documentation when configuration,
tools, or behavior change.

etrade-mcp is a thin adapter over etrade-python. Keep runtime network code async
and typed, use only public client APIs, and reuse the client's models, OAuth
lifecycle, credential stores, and brokerage logic. Production code uses the real
client; mock broker responses belong only in tests. Preserve supported request
fields and monetary precision when adding tools.

The consuming host owns human approval, request/preview binding, execution
history, duplicate prevention, and recovery. Preserve the separation between
preview and placement. Do not add automatic mutation retries, resubmit a mutation
to reconstruct a lost response, or introduce an adapter execution database,
preparation records, or background monitoring.

Keep stdout reserved for MCP protocol traffic during stdio serving; send
diagnostics to stderr. Keep credentials and customer data out of results, errors,
logs, examples, and submitted files. Do not commit `.env` files or live brokerage
recordings.

Maintain the [README tool coverage table](README.md#tool-coverage) manually when
client operations or MCP tools change. Link implemented tools to relevant tests,
distinguish planned tools, explain intentional omissions, and document coverage
of request fields when adding brokerage wrappers.

## Run checks

Before submitting a pull request, run:

```sh
uv lock --check
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pyright --pythonpath .venv/bin/python
uv run --frozen pytest
```

To apply formatting, use `uv run --frozen ruff format .`. If Make is available,
`make install`, `make check`, and `make format` wrap the setup, code checks, and
formatting commands. Run `uv lock --check` separately.

The suite enforces at least 90% combined statement/branch coverage. Brokerage
integration tests must exercise the real client with fake credentials and mocked
broker HTTP responses. Existing fixtures isolate credential storage and block
external broker networking. Protocol tests exercise actual stdio and loopback
HTTP connections. Keep offline tests independent of broker authorization, and
never place live orders as part of development or automated testing.

## Verify distributions

For packaging changes, also run:

```sh
uv build --clear
uv run --frozen python -m twine check --strict dist/*
uv run --frozen python scripts/check_artifacts.py
```

Alternatively, run `make package-check`. The artifact checker validates archive
contents, installs the wheel and source distribution into separate temporary
virtual environments, and checks imports, package metadata, the CLI, and MCP
discovery/invocation over stdio and authenticated loopback HTTP outside the
checkout. It uses dummy credentials and does not contact E*TRADE or publish
artifacts. Package-index access is needed to install build and runtime
dependencies; temporary environments are removed afterward.

## Submit a pull request

Push your branch to your fork and open a pull request against the repository's
default branch. Describe the problem, the resulting behavior, and any relevant
compatibility considerations. Link the related issue when there is one, identify
documentation updates, and state which checks you ran and their results.

Distinguish offline protocol tests and mocked brokerage integration tests from
any separately arranged authenticated broker validation. Note checks you could
not run and why. Address review feedback and keep the pull request focused;
release publishing is handled separately by maintainers.

Contributions are provided under the project's [Apache-2.0 license](LICENSE).
