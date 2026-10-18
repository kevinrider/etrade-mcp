"""CLI entry point. Secrets are environment-only and errors never print values."""

from __future__ import annotations

import logging
from typing import Annotated, Any

import typer
import uvicorn
from etrade_python import ETradeSettings
from pydantic import ValidationError

from etrade_mcp._version import __version__
from etrade_mcp.config import ConfigurationError, ServerConfig, ServerSettings
from etrade_mcp.http import create_http_app
from etrade_mcp.server import create_server

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


@app.callback(invoke_without_command=True)
def main(version: Annotated[bool, typer.Option("--version", is_eager=True)] = False) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def serve(
    transport: Annotated[str | None, typer.Option()] = None,
    environment: Annotated[str | None, typer.Option()] = None,
    profile: Annotated[str | None, typer.Option()] = None,
    host: Annotated[str | None, typer.Option()] = None,
    port: Annotated[int | None, typer.Option()] = None,
    enable_order_execution: Annotated[bool | None, typer.Option()] = None,
    enable_alert_deletion: Annotated[bool | None, typer.Option()] = None,
    tool_allowlist: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Serve one trusted credential profile over loopback HTTP or stdio."""
    options: dict[str, Any] = {
        "transport": transport,
        "profile": profile,
        "host": host,
        "port": port,
        "enable_order_execution": enable_order_execution,
        "enable_alert_deletion": enable_alert_deletion,
        "tool_allowlist": tool_allowlist,
    }
    try:
        settings = ServerSettings(**{k: v for k, v in options.items() if v is not None})
        broker = ETradeSettings(**({"environment": environment} if environment is not None else {}))
        config = ServerConfig(server=settings, broker=broker)
        server = create_server(config)
    except Exception as error:
        if isinstance(error, ValidationError):
            message = (
                "Invalid server configuration; check transport, credentials and policy settings."
            )
        elif isinstance(error, ConfigurationError):
            message = str(error)
        else:
            message = "Invalid broker/server configuration; check environment and credentials."
        typer.echo(message, err=True)
        raise typer.Exit(2) from None

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s", force=True)
    # Library debug/error tracebacks may contain caller-supplied data. Adapter
    # errors are sanitized results; SDK internals only emit critical diagnostics.
    logging.getLogger("mcp").setLevel(logging.CRITICAL)
    try:
        if settings.transport == "stdio":
            server.run(transport="stdio")
        else:
            uvicorn.run(
                create_http_app(server, settings),
                host=settings.bind_host,
                port=settings.bind_port,
                access_log=False,
                proxy_headers=False,
                log_level="warning",
            )
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        typer.echo("Server stopped because of an internal failure.", err=True)
        raise typer.Exit(1) from None
