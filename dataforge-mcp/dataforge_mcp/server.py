"""Executable MCP server for DataForge."""

from __future__ import annotations

import argparse
from typing import Literal

from mcp.server.fastmcp import FastMCP

from dataforge_mcp.tools import (
    dataforge_apply_repairs,
    dataforge_detect_errors,
    dataforge_profile,
    dataforge_revert,
    dataforge_verify_fix,
)

TransportLiteral = Literal["stdio", "streamable-http"]


def create_server(*, host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    """Create a FastMCP server with all DataForge tools registered."""
    mcp = FastMCP(
        "DataForge",
        instructions=(
            "DataForge profiles CSVs, detects data-quality issues, proposes "
            "verified repairs, applies reversible transactions, and reverts them."
        ),
        host=host,
        port=port,
        stateless_http=True,
        json_response=True,
    )
    mcp.tool(name="dataforge_profile")(dataforge_profile)
    mcp.tool(name="dataforge_detect_errors")(dataforge_detect_errors)
    mcp.tool(name="dataforge_verify_fix")(dataforge_verify_fix)
    mcp.tool(name="dataforge_apply_repairs")(dataforge_apply_repairs)
    mcp.tool(name="dataforge_revert")(dataforge_revert)
    return mcp


def serve(
    *,
    transport: TransportLiteral = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run the DataForge MCP server."""
    server = create_server(host=host, port=port)
    server.run(transport=transport)


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the console script."""
    parser = argparse.ArgumentParser(prog="dataforge-mcp")
    subparsers = parser.add_subparsers(dest="command")
    serve_parser = subparsers.add_parser("serve", help="Start the MCP server.")
    serve_parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport to use.",
    )
    serve_parser.add_argument("--host", default="127.0.0.1", help="HTTP host.")
    serve_parser.add_argument("--port", default=8000, type=int, help="HTTP port.")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Console entry point for ``dataforge-mcp``."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        raise SystemExit(0)
    if args.command == "serve":
        serve(transport=args.transport, host=args.host, port=args.port)
        return
    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
