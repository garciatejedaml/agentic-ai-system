# repo-mcp-tools — MCP Server Implementations

Model Context Protocol (MCP) servers for KDB+ and AMPS integrations.
These run as stdio subprocesses spawned by the agents in `repo-api`.

## Structure

```
kdb_mcp_server.py    ← KDB Bond RFQ analytics (DuckDB/Parquet in POC mode, KDB+ in server mode)
amps_mcp_server.py   ← AMPS pub/sub: subscribe, SOW query, publish, server info
docker/
  kdb/               ← Dockerfile + init.q for local KDB+ server
  amps/              ← Dockerfile + config.xml for local AMPS server
```

## Usage

These servers are started automatically by `mcp_clients.py` in `repo-api` via subprocess.
Set `KDB_ENABLED=true` or `AMPS_ENABLED=true` in the environment to enable them.

### Run standalone (for testing)

```bash
# KDB MCP server
python kdb_mcp_server.py

# AMPS MCP server (requires AMPS_HOST + AMPS_PORT set)
python amps_mcp_server.py
```

### Docker servers (start before the API when running locally)

```bash
# From repo-local-dev/
docker compose -f docker-compose.kdb.yml up -d
docker compose -f docker-compose.amps.yml up -d
```

## In Docker container

The Dockerfile (`repo-api/Dockerfile`) copies this entire directory to
`/app/src/mcp_server/` and sets `MCP_SERVER_DIR=/app/src/mcp_server` so
`mcp_clients.py` can locate the scripts at runtime.
