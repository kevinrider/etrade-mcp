# Contributing

Use Python 3.11+ and uv. Run commands from the repository root. CI explicitly
selects Python 3.11–3.14.

## Install and check

```sh
uv sync --extra dev --frozen
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pyright --pythonpath .venv/bin/python
```

Use `uv run --frozen ruff format .` to apply formatting. When intentionally
changing dependencies, update `pyproject.toml`, run `uv lock`, and commit the
updated `uv.lock`. Ordinary setup and CI use the committed lockfile without
updating it. uv uses an available interpreter satisfying the Python 3.11+
requirement. Set `UV_PYTHON=3.11` in your shell to explicitly select an interpreter
for both synchronization and subsequent `uv run` commands. CI sets `UV_PYTHON`
for each matrix job.

Make users can run `make install`, `make check`, and `make format`. The Makefile
wraps the same commands shown here; Make is optional.

## Build and verify distributions

```sh
uv build --clear
uv run --frozen python -m twine check --strict dist/*
uv run --frozen python scripts/check_artifacts.py
```

Or run `make package-check`. The verification script checks wheel/source archive
contents, installs each artifact into a separate temporary virtual environment,
and checks imports, version metadata, and `py.typed` outside the checkout. It
uses the invoking Python interpreter and uv, requires package-index access for
source-build dependencies, and deletes its temporary environments on completion.
It never publishes artifacts or contacts E*TRADE.

The wheel contains the typed package and distribution metadata. The source
distribution also includes development instructions and verification scripts.
Version `0.1.0` is defined only in `src/etrade_mcp/_version.py`; Hatchling reads it
for package metadata.

## Implementation expectations

Milestone 0 has no server behavior, runtime dependencies, command-line entry
point, or placeholder tests. Add substantive tests with later implementation and
enforce the planned 90% statement/branch coverage threshold then.

Implement the requested milestone and verify its acceptance criteria before
marking it complete. Keep runtime network code async and typed. Use only public
`etrade-python` APIs, keeping that client independently usable and reusing its
models, OAuth lifecycle, and brokerage logic. Production code must use the real
client; mock broker responses belong only in tests.

The host owns human approval, request/preview binding, execution history,
duplicate prevention, and recovery. Do not add an adapter execution database,
preparation records, or background monitoring. Preserve preview/placement
separation and never add automatic mutation retries or resubmit a mutation to
reconstruct a lost response. Future offline tests must use fake credentials and
mock broker HTTP responses, exercise the real client, and block accidental broker
access. Keep stdout reserved for MCP protocol traffic during stdio serving;
diagnostics must go to stderr.

Lint, formatting, and strict type checks must pass. Packaging changes also require
the distribution checks above. Report completed verification separately from
planned checks or authenticated broker validation.

Do not add credentials, customer data, `.env` files, or live recordings. Keep
secrets out of results, errors, logs, and examples. Source contributions use
Apache-2.0. Publication and authenticated broker validation are separate,
explicitly authorized activities; development must not place live orders.

## Git handoff

Git is unavailable in the current development environment. Agents must not run
Git commands or install Git; provide any needed commands to the repository owner
to execute locally. After reviewing the prepared files, initialize if needed with:

```sh
git init -b main
git status --short
```

Review and stage files locally before making an initial commit. Creating a
remote, pushing, and publishing are separate actions.
