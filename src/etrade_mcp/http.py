"""Authenticated loopback ASGI transport; no OAuth authorization server."""

from __future__ import annotations

import hashlib
import hmac
from typing import cast

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from etrade_mcp.config import ConfigurationError, ServerSettings
from etrade_mcp.server import Runtime


class BearerGate:
    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.digest = hashlib.sha256(token.encode("ascii")).digest()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = cast(list[tuple[bytes, bytes]], scope["headers"])
        values = [v for k, v in headers if k.lower() == b"authorization"]
        supplied: list[bytes] = values[0].split() if len(values) == 1 else []
        valid = (
            len(supplied) == 2
            and supplied[0].lower() == b"bearer"
            and hmac.compare_digest(hashlib.sha256(supplied[1]).digest(), self.digest)
        )
        if not valid:
            response = JSONResponse(
                {"error": "unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def create_http_app(server: MCPServer[Runtime], settings: ServerSettings) -> ASGIApp:
    if settings.transport != "streamable-http" or settings.http_bearer_token is None:
        raise ConfigurationError("HTTP transport configuration is required")
    host = settings.bind_host
    authority = f"[{host}]" if ":" in host else host
    authorities = [f"{authority}:{settings.bind_port}", f"localhost:{settings.bind_port}"]
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        host=host,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=authorities,
            allowed_origins=[f"http://{name}" for name in authorities],
        ),
    )
    return BearerGate(app, settings.http_bearer_token.get_secret_value())
