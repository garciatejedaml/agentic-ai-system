# repo-excalidraw-mcp — Excalidraw MCP Server

An MCP server that lets Claude generate and edit `.excalidraw` diagram files.
Produces architecture diagrams, flowcharts, and freeform sketches that open
directly in [Excalidraw](https://excalidraw.com) or the VS Code extension.

No external API calls. No internet required. Runs in stdio mode — perfect for VDI / air-gapped environments.

---

## Tools

| Tool | Description |
|------|-------------|
| `excalidraw_new` | Create a blank diagram file |
| `excalidraw_add_box` | Add a rectangle / ellipse / diamond with a label |
| `excalidraw_add_arrow` | Connect two elements with an arrow |
| `excalidraw_add_text` | Add a standalone text label |
| `excalidraw_architecture` | **One-shot**: generate a full architecture diagram from nodes + edges |
| `excalidraw_flowchart` | **One-shot**: generate a top-down flowchart from steps |
| `excalidraw_read` | Inspect an existing diagram (element summary) |
| `excalidraw_list` | List `.excalidraw` files in a directory |

---

## Setup

### 1. Install Python dependency

```bash
pip install mcp
# or
pip install -r repo-excalidraw-mcp/requirements.txt
```

Only `mcp` is required — no other packages.

---

### 2. Configure Claude Code (recommended — stdio)

Add to your **`~/.claude.json`** (global) or the project's **`.mcp.json`** file:

```json
{
  "mcpServers": {
    "excalidraw": {
      "command": "python",
      "args": ["/absolute/path/to/repo-excalidraw-mcp/excalidraw_mcp_server.py"],
      "env": {
        "DIAGRAMS_DIR": "/absolute/path/to/your/diagrams"
      }
    }
  }
}
```

> **VDI tip**: Use absolute paths. Relative paths may not resolve correctly inside the VDI
> depending on how Claude Code is launched.

After saving, restart Claude Code (`/reload` or reopen the window).
Verify the server is connected: run `/mcp` — you should see `excalidraw` in the list.

---

### 3. Configure Claude Desktop (alternative)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "excalidraw": {
      "command": "python",
      "args": ["C:\\Users\\you\\repos\\agentic-ai-system\\repo-excalidraw-mcp\\excalidraw_mcp_server.py"],
      "env": {
        "DIAGRAMS_DIR": "C:\\Users\\you\\diagrams"
      }
    }
  }
}
```

---

## Example prompts

Once the MCP server is connected, ask Claude:

```
Create an architecture diagram of our trading system:
- ALB at the top (entry layer)
- api-service and mcp-gateway in the service layer
- DynamoDB and OpenSearch in the data layer
- Draw arrows: ALB → api-service, api-service → DynamoDB, api-service → OpenSearch
Save it to ~/diagrams/trading_arch.excalidraw
```

```
Create a flowchart for the query lifecycle:
1. User Query (oval)
2. RAG Retrieval (rect)
3. LLM Router (rect)
4. All agents responded? (diamond)
5. Synthesize HIGH confidence (rect)
6. Synthesize LOW confidence (rect)
7. Return response (oval)
With a YES/NO branch at step 4.
Save to ~/diagrams/query_flow.excalidraw
```

```
List all my excalidraw diagrams in ~/diagrams
```

---

## Opening diagrams

| Option | How |
|--------|-----|
| **Browser** | Go to [excalidraw.com](https://excalidraw.com) → Open → select the `.excalidraw` file |
| **VS Code** | Install the [Excalidraw extension](https://marketplace.visualstudio.com/items?itemName=pomdtr.excalidraw-editor), then open the `.excalidraw` file directly |
| **Desktop app** | Download from [excalidraw.com/desktop](https://excalidraw.com) |

---

## Color palette

Use these names in the `color` parameter of `excalidraw_add_box` and `nodes`:

| Key | Color | Use for |
|-----|-------|---------|
| `entry` | Blue | Load balancer, API Gateway |
| `service` | Green | Microservices, agents |
| `data` | Orange | Databases, queues, storage |
| `external` | Gray | Third-party / external systems |
| `decision` | Light blue | Decision diamonds |
| `terminal` | Gray | Start / End ovals |
| `warning` | Yellow | Optional / degraded path |
| `error` | Red | Failed / timed-out |
| `default` | Light blue | General purpose |

You can also pass any hex color, e.g. `"#ff6b6b"`.

---

## Node layers (architecture diagrams)

The `excalidraw_architecture` tool auto-positions nodes by layer:

| Layer | Position | Default color | Use for |
|-------|----------|---------------|---------|
| `0` | Top row | Blue | Entry points: ALB, API Gateway |
| `1` | Second row | Green | Services, agents |
| `2` | Third row | Orange | Data: DB, cache, queue |
| `3` | Bottom row | Gray | External: CDN, SaaS |

---

## HTTP mode (optional — for MCP Gateway)

If you want to expose this server via the MCP Gateway on port 9105:

```bash
MCP_TRANSPORT=http MCP_PORT=9105 python repo-excalidraw-mcp/excalidraw_mcp_server.py
```

This requires `repo-mcp-tools/mcp_http_server.py` to be on the Python path.
For standalone local use, the default `stdio` mode is simpler and recommended.
