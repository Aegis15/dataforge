"""Stdio integration tests for the DataForge MCP server."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _write_repairable_csv(path: Path) -> None:
    """Write a small CSV with a deterministic decimal-shift issue."""
    path.write_text(
        "id,amount\n1,100\n2,105\n3,98\n4,1020\n5,103\n",
        encoding="utf-8",
    )


def test_stdio_server_lists_and_calls_profile_tool(tmp_path: Path) -> None:
    csv_path = tmp_path / "amounts.csv"
    _write_repairable_csv(csv_path)
    package_root = Path(__file__).resolve().parents[1]
    repo_root = package_root.parent
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(package_root), str(repo_root), env.get("PYTHONPATH", "")]
    )
    env["DATAFORGE_MCP_ALLOWED_ROOTS"] = str(tmp_path)

    async def run_client() -> None:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "dataforge_mcp.server", "serve"],
            env=env,
        )
        async with (
            stdio_client(server_params) as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert "dataforge_profile" in names

            result = await session.call_tool(
                "dataforge_profile",
                {"path": str(csv_path)},
            )
            assert result.isError is False
            assert result.structuredContent is not None
            payload = result.structuredContent
            if "result" in payload:
                payload = payload["result"]
            assert json.dumps(payload)
            assert payload["rows"] == 5
            assert payload["total_issues"] >= 1

    asyncio.run(run_client())
