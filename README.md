# etrade-mcp

A Python MCP adapter over the typed, async
[etrade-python](https://pypi.org/project/etrade-python/) E*TRADE client.

**Status:** under active development

The planned server supports loopback Streamable HTTP and stdio with the same
tools and permissions. It will default to sandbox and read/preview capabilities.
The consuming host owns human approval, request/preview binding, submission
history, duplicate prevention, and reconciliation. The adapter will provide
direct client wrappers without an application database or execution journal.

## Development

Use Python 3.11+ and uv. CI validates Python 3.11–3.14. From the repository root:

```sh
uv sync --extra dev --frozen
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pyright --pythonpath .venv/bin/python
uv build --clear
uv run --frozen python -m twine check --strict dist/*
uv run --frozen python scripts/check_artifacts.py
```

If Make is available, the equivalent workflow is `make install`, `make check`,
and `make package-check`. No brokerage credentials are needed for this milestone.
See [CONTRIBUTING.md](CONTRIBUTING.md) for tooling and artifact verification.

## License

Apache-2.0. This project is not affiliated with or endorsed by E*TRADE or Morgan
Stanley.
