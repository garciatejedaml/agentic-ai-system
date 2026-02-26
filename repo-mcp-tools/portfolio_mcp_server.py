#!/usr/bin/env python3
"""
Portfolio MCP Server — Phase 3

Exposes portfolio holdings and exposure analytics as MCP tools.
POC data is generated in-memory at startup (no external DB needed).

Tools:
  - portfolio_list            → all portfolios with summary stats
  - portfolio_holdings        → full position list for a portfolio
  - portfolio_exposure        → aggregated exposure by desk / asset_class
  - portfolio_concentration   → top N positions by weight

Schema (portfolio_positions):
  portfolio_id, portfolio_name, desk, isin, bond_name, issuer, sector,
  asset_class, quantity, cost_basis_usd, market_value_usd, weight_pct,
  duration_years, spread_bps
"""
import asyncio
import json
import logging
import sys
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

logger = logging.getLogger(__name__)

# ── POC Data Generation ─────────────────────────────────────────────────────

def _build_poc_data():
    import random
    random.seed(42)

    portfolios = [
        ("HY_MAIN",     "High Yield Main",         "HY",    "HighYield"),
        ("IG_CORE",     "Investment Grade Core",    "IG",    "InvestGrade"),
        ("EM_BLEND",    "Emerging Markets Blend",   "EM",    "EmergingMkt"),
        ("RATES_GOV",   "Rates Government",         "RATES", "Government"),
        ("MULTI_STRAT", "Multi-Strategy",           "MULTI", "Mixed"),
    ]

    sectors_by_desk = {
        "HY":    ["Energy", "Retail", "Healthcare", "Technology", "Industrials"],
        "IG":    ["Financials", "Utilities", "Technology", "Consumer", "Industrials"],
        "EM":    ["Sovereign", "Corporates", "Quasi-Sovereign", "Financials", "Energy"],
        "RATES": ["UST", "Agency", "Muni", "Supranational", "TIPS"],
        "MULTI": ["Energy", "Financials", "Technology", "Sovereign", "Healthcare"],
    }

    issuers_by_desk = {
        "HY":    ["Ford Motor Credit", "Sprint Corp", "Carnival Corp", "JC Penney", "Tenet Healthcare",
                  "Bausch Health", "Intelsat", "Windstream", "Altice USA", "Carvana"],
        "IG":    ["Apple Inc", "JPMorgan Chase", "Microsoft Corp", "Amazon.com", "Berkshire Hathaway",
                  "Verizon Comm", "AT&T Inc", "Bank of America", "Goldman Sachs", "Wells Fargo"],
        "EM":    ["Brazil 2030", "Mexico 2032", "Turkey 2028", "Indonesia 2035", "South Africa 2031",
                  "Petrobras", "Pemex", "PDVSA", "Gazprom", "Korea Dev Bank"],
        "RATES": ["US Treasury", "FNMA", "FHLB", "NY State GO", "IBRD",
                  "EIB", "ADB", "US TIPS", "Freddie Mac", "Ginnie Mae"],
        "MULTI": ["Ford Motor Credit", "Apple Inc", "Brazil 2030", "US Treasury", "JPMorgan Chase",
                  "Carnival Corp", "Microsoft Corp", "Turkey 2028", "FNMA", "Tenet Healthcare"],
    }

    spread_ranges = {
        "HY":    (200, 600),
        "IG":    (50,  180),
        "EM":    (150, 450),
        "RATES": (5,   60),
        "MULTI": (80,  350),
    }

    duration_ranges = {
        "HY":    (2.0, 6.0),
        "IG":    (3.0, 10.0),
        "EM":    (4.0, 12.0),
        "RATES": (1.0, 20.0),
        "MULTI": (2.0, 8.0),
    }

    rows = []
    isin_counter = 1000

    for pid, pname, desk, asset_class in portfolios:
        n_positions = 15
        issuers = issuers_by_desk[desk]
        sectors = sectors_by_desk[desk]
        s_min, s_max = spread_ranges[desk]
        d_min, d_max = duration_ranges[desk]

        total_mv = random.uniform(80e6, 300e6)
        weights = [random.uniform(1, 15) for _ in range(n_positions)]
        w_sum = sum(weights)
        weights = [w / w_sum for w in weights]

        for i in range(n_positions):
            isin = f"US{isin_counter:010d}"
            isin_counter += 1
            issuer = issuers[i % len(issuers)]
            sector = sectors[i % len(sectors)]
            mv = total_mv * weights[i]
            cost = mv * random.uniform(0.90, 1.10)
            qty = int(mv / random.uniform(80, 105) * 100)
            dur = round(random.uniform(d_min, d_max), 2)
            spd = round(random.uniform(s_min, s_max), 1)
            year = random.choice(["2026", "2027", "2028", "2029", "2030", "2032", "2035"])
            bond_name = f"{issuer[:20]} {year}"

            rows.append({
                "portfolio_id":     pid,
                "portfolio_name":   pname,
                "desk":             desk,
                "isin":             isin,
                "bond_name":        bond_name,
                "issuer":           issuer,
                "sector":           sector,
                "asset_class":      asset_class,
                "quantity":         qty,
                "cost_basis_usd":   round(cost, 2),
                "market_value_usd": round(mv, 2),
                "weight_pct":       round(weights[i] * 100, 4),
                "duration_years":   dur,
                "spread_bps":       spd,
            })

    return rows


_POSITIONS = _build_poc_data()


# ── Tool helpers ────────────────────────────────────────────────────────────

def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _portfolio_list() -> str:
    portfolios: dict = {}
    for row in _POSITIONS:
        pid = row["portfolio_id"]
        if pid not in portfolios:
            portfolios[pid] = {
                "portfolio_id":           pid,
                "portfolio_name":         row["portfolio_name"],
                "desk":                   row["desk"],
                "asset_class":            row["asset_class"],
                "positions":              0,
                "total_market_value_usd": 0.0,
                "avg_duration_years":     0.0,
                "avg_spread_bps":         0.0,
            }
        portfolios[pid]["positions"] += 1
        portfolios[pid]["total_market_value_usd"] += row["market_value_usd"]
        portfolios[pid]["avg_duration_years"] += row["duration_years"]
        portfolios[pid]["avg_spread_bps"] += row["spread_bps"]

    result = []
    for p in portfolios.values():
        n = p["positions"]
        p["avg_duration_years"] = round(p["avg_duration_years"] / n, 2)
        p["avg_spread_bps"] = round(p["avg_spread_bps"] / n, 1)
        p["total_market_value_usd"] = round(p["total_market_value_usd"], 2)
        result.append(p)

    return _fmt({"portfolios": result, "total_portfolios": len(result)})


def _portfolio_holdings(portfolio_id: str) -> str:
    rows = [r for r in _POSITIONS if r["portfolio_id"] == portfolio_id.upper()]
    if not rows:
        known = sorted({r["portfolio_id"] for r in _POSITIONS})
        return _fmt({"error": f"Portfolio '{portfolio_id}' not found", "known_portfolios": known})
    total_mv = sum(r["market_value_usd"] for r in rows)
    sorted_rows = sorted(rows, key=lambda x: x["market_value_usd"], reverse=True)
    return _fmt({
        "portfolio_id":             portfolio_id.upper(),
        "portfolio_name":           rows[0]["portfolio_name"],
        "positions":                len(rows),
        "total_market_value_usd":   round(total_mv, 2),
        "holdings":                 sorted_rows,
    })


def _portfolio_exposure(desk: str = "", asset_class: str = "") -> str:
    rows = _POSITIONS
    if desk:
        rows = [r for r in rows if r["desk"].upper() == desk.upper()]
    if asset_class:
        rows = [r for r in rows if r["asset_class"].lower() == asset_class.lower()]

    if not rows:
        return _fmt({"error": "No positions match filters", "desk": desk, "asset_class": asset_class})

    by_sector: dict = {}
    for row in rows:
        s = row["sector"]
        if s not in by_sector:
            by_sector[s] = {"sector": s, "market_value_usd": 0.0, "positions": 0,
                             "avg_duration": 0.0, "avg_spread": 0.0}
        by_sector[s]["market_value_usd"] += row["market_value_usd"]
        by_sector[s]["positions"] += 1
        by_sector[s]["avg_duration"] += row["duration_years"]
        by_sector[s]["avg_spread"] += row["spread_bps"]

    total_mv = sum(r["market_value_usd"] for r in rows)
    for s_data in by_sector.values():
        n = s_data["positions"]
        s_data["market_value_usd"] = round(s_data["market_value_usd"], 2)
        s_data["weight_pct"] = round(s_data["market_value_usd"] / total_mv * 100, 2)
        s_data["avg_duration"] = round(s_data["avg_duration"] / n, 2)
        s_data["avg_spread"] = round(s_data["avg_spread"] / n, 1)

    return _fmt({
        "filters": {"desk": desk or "all", "asset_class": asset_class or "all"},
        "total_market_value_usd": round(total_mv, 2),
        "total_positions": len(rows),
        "exposure_by_sector": sorted(by_sector.values(), key=lambda x: x["market_value_usd"], reverse=True),
    })


def _portfolio_concentration(portfolio_id: str, top_n: int = 10) -> str:
    rows = [r for r in _POSITIONS if r["portfolio_id"] == portfolio_id.upper()]
    if not rows:
        known = sorted({r["portfolio_id"] for r in _POSITIONS})
        return _fmt({"error": f"Portfolio '{portfolio_id}' not found", "known_portfolios": known})
    total_mv = sum(r["market_value_usd"] for r in rows)
    top = sorted(rows, key=lambda x: x["market_value_usd"], reverse=True)[:top_n]
    top_mv = sum(r["market_value_usd"] for r in top)
    return _fmt({
        "portfolio_id":             portfolio_id.upper(),
        "top_n":                    top_n,
        "top_positions_weight_pct": round(top_mv / total_mv * 100, 2),
        "positions":                top,
    })


# ── MCP Server ──────────────────────────────────────────────────────────────

server = Server("portfolio-mcp-server")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="portfolio_list",
            description=(
                "List all portfolios with summary statistics: market value, "
                "average duration, average spread, position count. "
                "Portfolios: HY_MAIN, IG_CORE, EM_BLEND, RATES_GOV, MULTI_STRAT."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="portfolio_holdings",
            description=(
                "Get full position list for a specific portfolio. "
                "Returns all bonds with ISIN, issuer, market value, weight, duration, spread. "
                "Use portfolio_list first to get valid portfolio IDs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {
                        "type": "string",
                        "description": "Portfolio ID (HY_MAIN, IG_CORE, EM_BLEND, RATES_GOV, MULTI_STRAT)",
                    },
                },
                "required": ["portfolio_id"],
            },
        ),
        types.Tool(
            name="portfolio_exposure",
            description=(
                "Aggregated exposure analytics grouped by sector. "
                "Filter by desk (HY/IG/EM/RATES/MULTI) and/or asset_class. "
                "Returns market value, weight %, average duration and spread per sector."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "desk": {
                        "type": "string",
                        "description": "Filter by desk: HY, IG, EM, RATES, MULTI. Leave empty for all.",
                        "default": "",
                    },
                    "asset_class": {
                        "type": "string",
                        "description": "Filter by asset class: HighYield, InvestGrade, EmergingMkt, Government, Mixed.",
                        "default": "",
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="portfolio_concentration",
            description=(
                "Top N positions by market value for a portfolio. "
                "Shows concentration risk: what % of NAV is in the top N bonds."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "portfolio_id": {
                        "type": "string",
                        "description": "Portfolio ID (HY_MAIN, IG_CORE, etc.)",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Number of top positions to return (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["portfolio_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _dispatch, name, arguments)
    except Exception as e:
        result = _fmt({"error": str(e), "tool": name})
    return [types.TextContent(type="text", text=result)]


def _dispatch(name: str, args: dict) -> str:
    if name == "portfolio_list":
        return _portfolio_list()
    if name == "portfolio_holdings":
        return _portfolio_holdings(args["portfolio_id"])
    if name == "portfolio_exposure":
        return _portfolio_exposure(
            desk=args.get("desk", ""),
            asset_class=args.get("asset_class", ""),
        )
    if name == "portfolio_concentration":
        return _portfolio_concentration(
            portfolio_id=args["portfolio_id"],
            top_n=int(args.get("top_n", 10)),
        )
    return _fmt({"error": f"Unknown tool: {name}"})


# ── Entry point ─────────────────────────────────────────────────────────────

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    asyncio.run(main())
