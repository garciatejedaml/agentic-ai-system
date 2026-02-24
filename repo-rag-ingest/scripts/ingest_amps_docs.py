#!/usr/bin/env python3
"""
AMPS Documentation Ingestion Script

Fetches AMPS server and Python client documentation and ingests it into
the ChromaDB RAG so agents can answer questions about AMPS concepts,
configuration, Python client API, Q queries, etc.

Sources (in priority order):
  1. Local AMPS docs extracted from the binary (if AMPS.tar was unpacked)
  2. Official AMPS documentation website (https://crankuptheamps.com/documentation)
  3. Bundled static knowledge (always available, no network/files required)

Usage:
  python scripts/ingest_amps_docs.py                    # ingest all sources
  python scripts/ingest_amps_docs.py --source static    # only bundled knowledge
  python scripts/ingest_amps_docs.py --source web       # only fetch from web
  python scripts/ingest_amps_docs.py --source local     # only local AMPS docs

AWS schedule trigger:
  The same script is invoked by EventBridge Scheduler → Lambda → ECS task.
  Set SOURCE env var: SOURCE=web python scripts/ingest_amps_docs.py
"""
import argparse
import os
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rag.retriever import get_retriever


# ── Static bundled AMPS knowledge ─────────────────────────────────────────────
# Always ingested. Covers key concepts that agents need to reason correctly.

_STATIC_DOCS = [
    {
        "source": "amps-concepts",
        "text": """
# AMPS Core Concepts

## What is AMPS?
AMPS (Advanced Message Processing System) by 60East Technologies is a
high-performance pub/sub messaging engine designed for financial data.
It is widely used in capital markets for real-time market data, order routing,
and position management.

## State of World (SOW)
The SOW is AMPS's built-in snapshot store. For each topic configured with SOW:
- AMPS stores the LATEST version of each record, keyed by a configurable field.
- A SOW query returns the current state of all records (like a SELECT * with dedup).
- SOW is stored in memory-mapped files (.sow) and survives server restarts.
- Example: positions SOW stores one record per (trader_id, isin) — always latest.

## Topics and Message Types
- A topic is a named stream of messages (like a Kafka topic but with SOW).
- Each topic has a message type: JSON, FIX, NVFIX, Binary, etc.
- Topics can be: pure pub/sub (no SOW), SOW-only, or SOW + subscribe.

## Subscribe vs SOW Query
- Subscribe: receive messages as they are published in real-time (streaming).
- SOW query: get a snapshot of the current state (one record per key).
- For analytics: prefer SOW query (less volume, current state).
- For event detection: use subscribe (all updates, in order).

## Content Filters
AMPS supports XPath-style content filters on any field:
  /desk = 'HY'
  /price > 100
  /desk = 'HY' AND /side = 'buy'
  /trader_id IN ('T_HY_001', 'T_HY_002')
Filters are applied server-side before messages are sent to clients.

## AMPS Python Client
The amps-python-client library (pip install amps-python-client) provides:
  from AMPS import Client, Command
  client = Client("my-app")
  client.connect("tcp://localhost:9007/amps/json")
  client.logon()
  # SOW query
  for msg in client.execute(Command("sow").set_topic("positions")):
      print(msg.get_data())
  # Subscribe with filter
  cmd = Command("subscribe").set_topic("orders").set_filter("/desk = 'HY'")
  for msg in client.execute(cmd):
      ...
  client.disconnect()
""",
    },
    {
        "source": "amps-admin-api",
        "text": """
# AMPS HTTP Admin API

AMPS exposes a monitoring HTTP interface (default port 8085).

## Key Endpoints

### GET /amps.json
Returns full server status:
- version, uptime, connected clients count
- memory usage (RSS, virtual)
- CPU utilization
- transport stats (messages received/sent per second)
- list of currently connected clients with names and IPs

### GET /topics.json
Returns all configured topics with statistics:
- topic name and message type
- SOW status (enabled/disabled), SOW record count
- messages per second (in and out)
- SOW memory usage in bytes
- SOW file path

### GET /clients.json
Returns currently connected clients:
- client name, connection time, IP address
- messages sent/received per client
- subscriptions count per client

## Usage in Python
  import urllib.request, json
  with urllib.request.urlopen("http://localhost:8085/amps.json") as r:
      data = json.loads(r.read())
  version = data["amps"]["instance"]["version"]
  uptime  = data["amps"]["instance"]["uptime"]
""",
    },
    {
        "source": "amps-config",
        "text": """
# AMPS Server Configuration (config.xml)

AMPS is configured via an XML file passed at startup: ampServer config.xml

## Key sections

### Admin (HTTP monitoring port)
  <Admin>
    <InetAddr>0.0.0.0:8085</InetAddr>
  </Admin>

### Transport (client connections)
  <Transport>
    <Name>tcp-json</Name>
    <Type>tcp</Type>
    <InetAddr>0.0.0.0:9007</InetAddr>
    <MessageType>json</MessageType>
    <Protocol>amps</Protocol>
  </Transport>

### SOW Topic definition
  <Topic>
    <Name>bond_rfq</Name>
    <MessageType>json</MessageType>
    <Key>/rfq_id</Key>
    <SOW>
      <Type>HashFile</Type>
      <Filename>/sow/bond_rfq.sow</Filename>
      <RecordSize>256</RecordSize>
    </SOW>
  </Topic>

## SOW key field
The Key field uniquely identifies each record in the SOW.
For bond_rfq: /rfq_id (one record per RFQ id)
For positions: could be /trader_id+/isin composite key
""",
    },
    {
        "source": "amps-mcp-tools",
        "text": """
# AMPS MCP Tools Reference

The AMPS MCP server exposes 5 tools to Strands agents.

## amps_server_info
Fetches /amps.json from the HTTP admin interface.
Returns: version, uptime, client count, memory usage, CPU stats.
No parameters required.

## amps_list_topics
Fetches /topics.json — all topics with stats.
Returns: topic names, message types, SOW status, record counts, throughput.
No parameters required.

## amps_sow_query(topic, filter="")
Queries the State-of-World for a topic.
Returns current state of all records (latest version per key).
- topic: topic name (e.g. "positions", "orders")
- filter: optional AMPS content filter (e.g. "/desk = 'HY'")

Best for: current state queries, "what are the current positions", snapshot analysis.

## amps_subscribe(topic, filter="", max_messages=10)
Subscribes to a topic and collects up to max_messages.
Returns a sample of recent streaming messages.
- topic: topic name
- filter: optional content filter
- max_messages: how many messages to collect before returning (default 10)

Best for: seeing recent data flow, event samples, delta stream analysis.
Warning: on high-throughput topics, use a tight filter and low max_messages.

## amps_publish(topic, data)
Publishes a JSON message to a topic.
- topic: destination topic
- data: JSON string to publish
Use for testing, event injection, or triggering downstream processors.
""",
    },
    {
        "source": "kdb-mcp-tools",
        "text": """
# KDB MCP Tools Reference (Bond RFQ Analytics)

The KDB MCP server exposes 4 tools for historical Bond RFQ analysis.

## kdb_list_tables
Lists available tables in the KDB historical store.
In POC mode: shows DuckDB tables loaded from Parquet files.
In server mode: shows KDB+ tables.

## kdb_get_schema(table)
Returns column names and types for a table.
Main table: bond_rfq
Columns: rfq_id, desk, trader_id, trader_name, isin, bond_name, issuer, sector,
         rating, side, notional_usd, price, spread_bps, coupon,
         rfq_date, rfq_time, response_time_ms, won, hit_rate, venue

## kdb_query(code, limit=100)
Executes a SQL query (POC mode) or Q code (server mode).
Returns up to limit rows.
POC example:
  SELECT trader_id, AVG(hit_rate), COUNT(*) FROM bond_rfq
  WHERE desk='HY' GROUP BY trader_id ORDER BY AVG(hit_rate) DESC

## kdb_rfq_analytics(desk, date_from, date_to, group_by, top_n)
High-level aggregated analytics. Computes per group:
  rfq_count, avg_spread_bps, total_notional_usd, avg_hit_rate, wins, avg_response_ms
Returns top_n results ranked by avg_hit_rate.
- desk: HY / IG / EM / RATES (or empty for all)
- date_from / date_to: YYYY-MM-DD format
- group_by: trader_id (default), desk, sector, venue
- top_n: number of results (default 20)

This is the recommended starting tool for most trading performance queries.
""",
    },
    {
        "source": "bond-rfq-domain",
        "text": """
# Bond RFQ Domain Knowledge

## What is an RFQ?
A Request For Quote (RFQ) is when a client asks a trader to provide a price
for a bond transaction. The trader responds with a bid/ask, and the client
either trades (hit/lift) or walks away.

## Bond Desks
- HY (High Yield): bonds rated BB+ and below. Spreads 200-600 bps over UST.
  Higher risk, wider markets, more alpha potential for skilled traders.
- IG (Investment Grade): bonds rated BBB- and above. Spreads 40-220 bps over UST.
  Lower risk, tighter markets, volume-driven.
- EM (Emerging Markets): sovereign and corporate bonds from developing economies.
  Mix of HY and IG ratings, currency and political risk.
- RATES: government bonds (US Treasury, Bunds, Gilts). Spreads < 80 bps.

## Key Performance Metrics
- hit_rate: fraction of RFQs where the trader won the trade.
  Good HY trader: > 60%. Average: 40-55%.
- spread_bps: price quoted in basis points over the benchmark (UST).
  Lower spread = tighter/better price for the client.
- notional_usd: face value of the bond in USD. Indicates trading volume.
- response_time_ms: how fast the trader responded to the RFQ.

## What defines "best strategy"?
NOT just highest hit_rate — winning every RFQ means you're too cheap.
The best strategy balances:
1. Competitive hit_rate (60-75% for HY)
2. Spread discipline (not systematically tighter than peers)
3. High notional (active in the market)
4. Fast response time (good market access and pricing models)

A trader with 72% hit_rate AND avg spread at market levels is better than
one with 85% hit_rate who is always the cheapest (likely losing money).
""",
    },
]


# ── Web fetcher ────────────────────────────────────────────────────────────────

def _fetch_web_docs() -> list[dict]:
    """Fetch AMPS documentation from the official website."""
    import urllib.request
    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self._in_body = True
            self._skip_tags = {"script", "style", "nav", "header", "footer"}
            self._current_skip = None
            self.text_parts = []

        def handle_starttag(self, tag, attrs):
            if tag in self._skip_tags:
                self._current_skip = tag
        def handle_endtag(self, tag):
            if tag == self._current_skip:
                self._current_skip = None
        def handle_data(self, data):
            if self._current_skip is None and data.strip():
                self.text_parts.append(data.strip())

    urls = [
        ("https://crankuptheamps.com/documentation/", "amps-docs-overview"),
        ("https://crankuptheamps.com/documentation/html/5.3.4/client/python/", "amps-python-client-docs"),
    ]

    docs = []
    for url, source in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            parser = TextExtractor()
            parser.feed(html)
            text = "\n".join(parser.text_parts)
            if len(text) > 200:
                docs.append({"source": source, "text": text[:8000]})  # cap per page
                print(f"  [web] Fetched {source}: {len(text)} chars")
        except Exception as e:
            print(f"  [web] Could not fetch {url}: {e}")
    return docs


# ── Local docs from AMPS binary ────────────────────────────────────────────────

def _find_local_docs() -> list[dict]:
    """Look for HTML/text docs in the extracted AMPS binary or installed package."""
    docs = []
    search_paths = [
        Path("amps/binaries"),
        Path("/AMPS/docs"),
        Path("docker/amps"),
    ]
    for base in search_paths:
        if not base.exists():
            continue
        for ext in ("*.txt", "*.md", "*.rst"):
            for f in base.rglob(ext):
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                    if len(text.strip()) > 100:
                        docs.append({"source": f"local:{f.name}", "text": text[:6000]})
                        print(f"  [local] Found {f}")
                except Exception:
                    pass
    return docs


# ── Main ──────────────────────────────────────────────────────────────────────

def ingest(source: str = "all") -> None:
    retriever = get_retriever()
    docs: list[dict] = []

    if source in ("all", "static"):
        print(f"Loading {len(_STATIC_DOCS)} static AMPS knowledge documents...")
        docs.extend(_STATIC_DOCS)

    if source in ("all", "local"):
        print("Searching for local AMPS docs...")
        local = _find_local_docs()
        print(f"  Found {len(local)} local documents.")
        docs.extend(local)

    if source in ("all", "web"):
        print("Fetching AMPS docs from web...")
        web = _fetch_web_docs()
        print(f"  Fetched {len(web)} web documents.")
        docs.extend(web)

    if not docs:
        print("No documents to ingest.")
        return

    print(f"\nIngesting {len(docs)} documents into ChromaDB RAG...")
    for doc in docs:
        retriever.add_texts(
            texts=[doc["text"]],
            metadatas=[{"source": doc["source"]}],
        )
        print(f"  ✓ {doc['source']}")

    total = retriever.count()
    print(f"\nDone. RAG now contains {total} total chunks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest AMPS documentation into RAG")
    parser.add_argument(
        "--source",
        choices=["all", "static", "web", "local"],
        default=os.getenv("SOURCE", "all"),
        help="Which documentation sources to ingest (default: all)",
    )
    args = parser.parse_args()
    ingest(args.source)
