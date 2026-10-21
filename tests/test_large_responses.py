import json
import os
import sys
from typing import Literal

import httpx
import pytest
from etrade_python import ETradeSettings, OptionChainResponse
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import TextContent

from tests.helpers import authenticated_http, http_server
from tests.large_response_data import CHAIN_DATA
from tests.test_reads import broker_factory
from tests.test_server import payload


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("wire", ["http", "stdio"])
async def test_large_response_arrives_complete(
    broker: ETradeSettings, mode: Literal["auto", "legacy"], wire: str
) -> None:
    expected = OptionChainResponse.model_validate(CHAIN_DATA).model_dump(mode="json", by_alias=True)
    assert len(json.dumps(expected).encode("utf-8")) > 65_536
    calls: list[httpx.Request] = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == "/v1/market/optionchains.json"
        assert request.url.params == httpx.QueryParams({"symbol": "SYN"})
        return httpx.Response(200, json={"OptionChainResponse": CHAIN_DATA})

    async def check(client: Client) -> None:
        tools = (await client.list_tools()).tools
        schema = next(
            tool.output_schema for tool in tools if tool.name == "market_get_option_chain"
        )
        assert schema is not None
        result = await client.call_tool("market_get_option_chain", {"symbol": "SYN"})
        assert not result.is_error, result.model_dump_json()
        assert payload(result)["data"] == expected
        assert len(payload(result)["data"]["optionPairs"]) == 96
        assert payload(result)["data"]["nearPrice"] == "100.1234567890123456789"
        assert (
            payload(result)["data"]["optionPairs"][0]["put"]["displaySymbol"]
            == 'Synthetic 漢字😀 "\\'
        )
        assert isinstance(result.content[0], TextContent)
        assert json.loads(result.content[0].text) == payload(result)

    if wire == "http":
        async with http_server(broker, client_factory=broker_factory(response)) as (url, _):
            async with Client(authenticated_http(url), mode=mode) as client:
                await check(client)
        assert len(calls) == 1
    else:
        async with Client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "tests.large_response_worker"],
                env=os.environ.copy(),
            ),
            mode=mode,
        ) as client:
            await check(client)
