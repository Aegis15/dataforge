# dataforge-mcp

`dataforge-mcp` exposes DataForge's shipped CSV profiling, detection, repair,
verification, and transaction-revert paths as Model Context Protocol tools.

```bash
pip install dataforge-mcp
dataforge-mcp serve
```

For local development from this repository:

```bash
cd dataforge-mcp
python -m pip install -e ".[dev]"
dataforge-mcp serve
```

The default transport is stdio, which is what local desktop MCP clients expect.
For local Streamable HTTP experiments:

```bash
dataforge-mcp serve --transport streamable-http --host 127.0.0.1 --port 8000
```

## Tools

- `dataforge_profile(path: str)` - summarize CSV shape plus detected issues.
- `dataforge_detect_errors(path: str)` - return detected issues only.
- `dataforge_verify_fix(fix_spec: dict)` - run one candidate fix through stale
  value checks, safety, and verification.
- `dataforge_apply_repairs(path: str, mode: "dry_run" | "apply")` - propose
  verified repairs and optionally write a reversible transaction.
- `dataforge_revert(txn_id: str)` - restore a transaction's original bytes.

## Client Configuration

Use the same server command for Claude Desktop, Cursor, Windsurf, or any local
MCP client that supports stdio servers:

```json
{
  "mcpServers": {
    "dataforge": {
      "command": "dataforge-mcp",
      "args": ["serve"]
    }
  }
}
```

If your client cannot resolve the console script, replace `command` with the
absolute path returned by your shell:

```bash
which dataforge-mcp
```

On Windows PowerShell:

```powershell
Get-Command dataforge-mcp
```

## Safety Model

`apply` mode uses DataForge's detector -> repairer -> SafetyFilter ->
SMTVerifier -> transaction-log path. The tool writes the transaction journal and
source snapshot before mutating the CSV, and `dataforge_revert` restores the
snapshot only when the current file still matches the recorded post-state hash.

The MCP server does not enable live LLM repair fallback by default. It does not
send CSV contents to any external model provider.

## Release

The package is released independently from the nested `dataforge-mcp/`
directory. The trusted-publishing workflow builds on tags matching:

```text
dataforge-mcp-v*
```

The package depends on `dataforge` and the official Python `mcp` SDK; it does
not vendor DataForge or add MCP dependencies to the core package.
