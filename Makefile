.PHONY: install lint format format-check type test check build twine-check artifact-check package-check

install:
	uv sync --extra dev --frozen

lint:
	uv run --frozen ruff check .

format:
	uv run --frozen ruff format .

format-check:
	uv run --frozen ruff format --check .

type:
	uv run --frozen pyright --pythonpath .venv/bin/python

test:
	uv run --frozen pytest -n 4

check: lint format-check type test

build:
	uv build --clear

twine-check:
	uv run --frozen python -m twine check --strict dist/*

artifact-check:
	uv run --frozen python scripts/check_artifacts.py

package-check: build
	uv run --frozen python -m twine check --strict dist/*
	uv run --frozen python scripts/check_artifacts.py
