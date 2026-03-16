# repo-mcp-tools — MCP Server Implementations

Model Context Protocol (MCP) servers providing tool access to financial data sources.
Each server runs as a persistent HTTP service (Starlette + uvicorn) and auto-registers
with a DynamoDB registry so the MCP Gateway can discover it without restarts.

## Servers

| Server | Port | Data source | Key tools |
|--------|------|-------------|-----------|
| `amps_mcp_server.py` | 9100 | AMPS Core pub/sub | `subscribe_topic`, `sow_query`, `publish_message` |
| `kdb_mcp_server.py` | 9101 | KDB+ / S3 Parquet | `query_rfq_history`, `get_trader_rankings`, `get_desk_performance` |
| `portfolio_mcp_server.py` | 9102 | AMPS `portfolio_nav` topic | `get_portfolio_holdings`, `get_portfolio_exposure` |
| `cds_mcp_server.py` | 9103 | AMPS `cds_spreads` topic | `get_cds_spreads`, `get_cds_term_structure`, `screen_credits` |
| `etf_mcp_server.py` | 9104 | AMPS `etf_nav` topic | `get_etf_nav`, `get_etf_flows`, `get_etf_basket` |

## Transport — HTTP/SSE (Phase 5)

Servers run as standalone HTTP services using `mcp_http_server.py`:

```bash
MCP_TRANSPORT=http python mcp_http_server.py amps_mcp_server --port 9100
```

The MCP Gateway (`repo-api/src/mcp_gateway/`) aggregates all servers: it lists tools from
every healthy server and routes tool calls to the owning backend transparently.

## Auto-registration

On startup each server registers itself in DynamoDB table `agentic-ai-{env}-mcp-registry`:

```python
# mcp_registry_client.py
{
  "server_id":   "amps-mcp",
  "endpoint":    "http://amps-mcp:9100",
  "tools":       ["subscribe_topic", "sow_query", ...],
  "ttl":         <now + 90s>   # auto-expires if server goes down
}
```

A background heartbeat thread refreshes the TTL every 60 seconds. If the container stops,
the entry expires after 90s and the Gateway stops routing to it — no manual cleanup needed.

## Structure

```
mcp_http_server.py      ← Wraps any MCP server as HTTP/SSE (MCP_TRANSPORT=http)
mcp_registry_client.py  ← DynamoDB registration + heartbeat thread
amps_mcp_server.py      ← AMPS tools
kdb_mcp_server.py       ← KDB+ / Parquet tools
portfolio_mcp_server.py ← Portfolio NAV tools
cds_mcp_server.py       ← CDS spread tools
etf_mcp_server.py       ← ETF analytics tools
docker/
  amps/                 ← Dockerfile + AMPS config.xml
  kdb/                  ← Dockerfile + KDB+ init.q
```

## Local development

```bash
cd repo-local-dev
docker compose --profile agents up -d   # starts all MCP servers on ports 9100-9104

# Verify a server registered in DynamoDB
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
    dynamodb scan --table-name agentic-ai-staging-mcp-registry \
    --query 'Items[].{id:server_id.S,url:endpoint.S}' --output table --no-cli-pager

# Query the MCP Gateway tool list (aggregates all servers)
curl http://localhost:9000/tools | jq '.tools[].name'
```

## Environment variables

```bash
MCP_TRANSPORT=http              # http | stdio (default stdio)
MCP_REGISTRY_TABLE=agentic-ai-staging-mcp-registry
AWS_ENDPOINT_URL=http://localstack:4566   # LocalStack in local dev; blank in AWS
AWS_DEFAULT_REGION=us-east-1

# AMPS connection (amps_mcp_server + portfolio/cds/etf)
AMPS_HOST=amps-core
AMPS_PORT=9007

# KDB (kdb_mcp_server)
KDB_MODE=poc           # poc = DuckDB/Parquet | server = live KDB+ instance
KDB_DATA_PATH=/app/data/kdb
```
