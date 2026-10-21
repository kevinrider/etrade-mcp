"""Authenticated loopback ASGI transport; no OAuth authorization server."""

from __future__ import annotations

import hashlib
import hmac
from typing import cast

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import INVALID_PARAMS, INVALID_REQUEST, PARSE_ERROR, ErrorData, JSONRPCError
from pydantic import ValidationError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from etrade_mcp.config import ConfigurationError, ServerSettings
from etrade_mcp.server import Runtime


class ProtocolErrorSanitizer:
    """Remove SDK diagnostics produced before tool validation can run.

    Only HTTP 400 JSON responses are buffered. Successful tool responses and
    other ASGI traffic pass through directly, regardless of their size.
    Non-validation protocol errors retain data needed for version negotiation.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def sanitized_body(body: bytes) -> bytes:
        messages = {
            PARSE_ERROR: "Parse error.",
            INVALID_REQUEST: "Invalid request.",
            INVALID_PARAMS: "Invalid request parameters.",
        }
        code, request_id = INVALID_REQUEST, None
        try:
            error = JSONRPCError.model_validate_json(body)
        except ValidationError:
            pass  # Never return an unrecognized diagnostic body verbatim.
        else:
            code, request_id = error.error.code, error.id
            if code not in messages:
                return body
        return (
            JSONRPCError(
                jsonrpc="2.0", id=request_id, error=ErrorData(code=code, message=messages[code])
            )
            .model_dump_json(exclude_unset=True)
            .encode("utf-8")
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start: Message | None = None
        body = bytearray()

        async def sanitized_send(message: Message) -> None:
            nonlocal start
            if message["type"] == "http.response.start" and message["status"] == 400:
                headers = message.get("headers", [])
                if any(
                    name.lower() == b"content-type"
                    and value.split(b";", 1)[0].strip().lower() == b"application/json"
                    for name, value in headers
                ):
                    start = dict(message)
                    return
            if start is not None and message["type"] == "http.response.body":
                body.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    sanitized = self.sanitized_body(bytes(body))
                    start["headers"] = [
                        (name, value)
                        for name, value in start.get("headers", [])
                        if name.lower() != b"content-length"
                    ] + [(b"content-length", str(len(sanitized)).encode("ascii"))]
                    await send(start)
                    await send({"type": "http.response.body", "body": sanitized})
                    start = None
                    body.clear()
                return
            await send(message)

        await self.app(scope, receive, sanitized_send)


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
    return BearerGate(ProtocolErrorSanitizer(app), settings.http_bearer_token.get_secret_value())
