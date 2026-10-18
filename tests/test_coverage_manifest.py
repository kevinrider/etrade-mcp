import ast
import inspect
import json
from pathlib import Path
from typing import Any, cast

import etrade_python
import pytest
from mcp import Client

from etrade_mcp.config import ServerConfig
from etrade_mcp.server import create_server
from tests.conftest import memory_client

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def manifest() -> dict[str, Any]:
    return json.loads((ROOT / "tool-coverage.json").read_text())


async def test_coverage_manifest_tracks_public_operations_and_tests(
    config: ServerConfig, manifest: dict[str, Any]
) -> None:
    async with memory_client(config.broker, "manifest") as broker:
        supported = {
            f"{service}.{operation}"
            for service in ("accounts", "portfolio", "transactions", "market", "orders", "alerts")
            for operation, _ in inspect.getmembers(
                cast(type[Any], type(getattr(broker, service))), inspect.isfunction
            )
            if not operation.startswith("_")
        }
    accounted = {row["client_operation"] for row in manifest["planned"]}
    accounted.update(row["client_operation"] for row in manifest["intentional_omissions"])
    for row in manifest["implemented"]:
        accounted.update(row["client_operations"])
        assert row["tests"]
        for selector in row["tests"]:
            filename, function = selector.split("::")
            tree = ast.parse((ROOT / filename).read_text())
            assert any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function
                for node in ast.walk(tree)
            )
    assert supported == {name for name in accounted if not name.startswith("session.")}
    for row in manifest["planned"]:
        if row["request_model"] is not None:
            assert hasattr(etrade_python, row["request_model"])
    async with Client(create_server(config, client_factory=memory_client)) as client:
        assert {tool.name for tool in (await client.list_tools()).tools} == {
            row["tool"] for row in manifest["implemented"]
        }
