#!/usr/bin/env python3
"""
CDS MCP Server — Phase 3

Exposes Credit Default Swap market data as MCP tools.
POC data: ~50 reference entities × 5 tenors = 250 rows, generated in-memory.

Tools:
  - cds_list_entities   → all reference entities with summary stats
  - cds_get_spread      → spread for a specific entity + tenor
  - cds_curve           → full term structure (1/3/5/7/10y) for an entity
  - cds_screener        → filter entities by spread range / sector / rating

Schema (cds_market_data):
  reference_entity, issuer, sector, rating, tenor_years, spread_bps,
  z_spread_bps, upfront_pct, trade_date
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
    random.seed(123)

    entities = [
        # (reference_entity, sector, rating, base_5y_spread)
        ("Ford Motor Credit",    "Automotive",  "BB+",  285),
        ("Sprint Corp",          "Telecom",     "B+",   420),
        ("Carnival Corp",        "Leisure",     "BB-",  380),
        ("Tenet Healthcare",     "Healthcare",  "B+",   390),
        ("Bausch Health",        "Healthcare",  "B",    510),
        ("Altice USA",           "Telecom",     "B",    480),
        ("Carvana",              "Auto Retail", "B-",   680),
        ("Intelsat",             "Satellite",   "CCC",  920),
        ("Windstream",           "Telecom",     "B-",   640),
        ("Frontier Comm",        "Telecom",     "B",    550),
        ("Apple Inc",            "Technology",  "AA+",   28),
        ("JPMorgan Chase",       "Financials",  "A-",    55),
        ("Microsoft Corp",       "Technology",  "AAA",   18),
        ("Amazon.com",           "Technology",  "AA",    32),
        ("Bank of America",      "Financials",  "A-",    62),
        ("Goldman Sachs",        "Financials",  "BBB+",  78),
        ("Wells Fargo",          "Financials",  "A-",    68),
        ("Verizon Comm",         "Telecom",     "BBB+",  90),
        ("AT&T Inc",             "Telecom",     "BBB",  110),
        ("Boeing Co",            "Aerospace",   "BBB-", 145),
        ("Brazil",               "Sovereign",   "BB",   185),
        ("Mexico",               "Sovereign",   "BBB-", 130),
        ("Turkey",               "Sovereign",   "B+",   380),
        ("Indonesia",            "Sovereign",   "BBB",  120),
        ("South Africa",         "Sovereign",   "BB-",  250),
        ("Colombia",             "Sovereign",   "BB+",  215),
        ("Egypt",                "Sovereign",   "B+",   490),
        ("Nigeria",              "Sovereign",   "B",    580),
        ("Argentina",            "Sovereign",   "CCC+", 960),
        ("Ukraine",              "Sovereign",   "CCC",  1850),
        ("Petrobras",            "Energy EM",   "BB",   245),
        ("Pemex",                "Energy EM",   "BB-",  430),
        ("Vale SA",              "Mining EM",   "BB+",  165),
        ("Ecopetrol",            "Energy EM",   "BB+",  210),
        ("Cemex",                "Materials EM","BB-",  320),
        ("Exxon Mobil",          "Energy",      "AA-",   42),
        ("Chevron Corp",         "Energy",      "AA",    38),
        ("Shell PLC",            "Energy",      "A+",    52),
        ("BP PLC",               "Energy",      "A-",    72),
        ("Occidental Pete",      "Energy",      "BB+",  175),
        ("Walmart Inc",          "Retail",      "AA",    22),
        ("Target Corp",          "Retail",      "A",     58),
        ("Home Depot",           "Retail",      "A+",    45),
        ("Macy's Inc",           "Retail",      "BB",   265),
        ("JC Penney",            "Retail",      "CCC",  1200),
        ("UnitedHealth",         "Healthcare",  "A+",    40),
        ("HCA Healthcare",       "Healthcare",  "BB+",  185),
        ("Teva Pharma",          "Healthcare",  "B+",   450),
        ("Pfizer Inc",           "Healthcare",  "A+",    35),
        ("Rite Aid",             "Healthcare",  "CCC",  1100),
    ]

    tenors = [1, 3, 5, 7, 10]
    # Slope multipliers per tenor (relative to 5y)
    slope = {1: 0.55, 3: 0.80, 5: 1.00, 7: 1.12, 10: 1.22}

    rows = []
    trade_date = "2026-02-21"

    for ref_entity, sector, rating, base_5y in entities:
        for tenor in tenors:
            spread = round(base_5y * slope[tenor] * random.uniform(0.92, 1.08), 1)
            z_spread = round(spread * random.uniform(0.95, 1.05), 1)
            upfront = round((spread - 100) / 10000 * tenor * random.uniform(0.9, 1.1), 4) if spread > 100 else 0.0
            rows.append({
                "reference_entity": ref_entity,
                "issuer":           ref_entity,
                "sector":           sector,
                "rating":           rating,
                "tenor_years":      tenor,
                "spread_bps":       spread,
                "z_spread_bps":     z_spread,
                "upfront_pct":      upfront,
                "trade_date":       trade_date,
            })

    return rows


_CDS_DATA = _build_poc_data()


# ── Tool helpers ────────────────────────────────────────────────────────────

def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _cds_list_entities() -> str:
    seen = {}
    for row in _CDS_DATA:
        e = row["reference_entity"]
        if e not in seen:
            seen[e] = {
                "reference_entity": e,
                "sector":           row["sector"],
                "rating":           row["rating"],
                "spread_5y_bps":    None,
                "spread_1y_bps":    None,
                "spread_10y_bps":   None,
            }
        t = row["tenor_years"]
        if t == 5:
            seen[e]["spread_5y_bps"] = row["spread_bps"]
        elif t == 1:
            seen[e]["spread_1y_bps"] = row["spread_bps"]
        elif t == 10:
            seen[e]["spread_10y_bps"] = row["spread_bps"]

    entities = sorted(seen.values(), key=lambda x: x["spread_5y_bps"] or 0, reverse=True)
    return _fmt({"entities": entities, "total": len(entities)})


def _cds_get_spread(reference_entity: str, tenor_years: int) -> str:
    matches = [
        r for r in _CDS_DATA
        if r["reference_entity"].lower() == reference_entity.lower()
        and r["tenor_years"] == tenor_years
    ]
    if not matches:
        known = sorted({r["reference_entity"] for r in _CDS_DATA})
        return _fmt({
            "error": f"No data for '{reference_entity}' at {tenor_years}y tenor",
            "known_entities": known[:20],
            "valid_tenors": [1, 3, 5, 7, 10],
        })
    return _fmt(matches[0])


def _cds_curve(reference_entity: str) -> str:
    matches = [
        r for r in _CDS_DATA
        if r["reference_entity"].lower() == reference_entity.lower()
    ]
    if not matches:
        known = sorted({r["reference_entity"] for r in _CDS_DATA})
        return _fmt({
            "error": f"No data for '{reference_entity}'",
            "known_entities": known[:20],
        })
    curve = sorted(matches, key=lambda x: x["tenor_years"])
    return _fmt({
        "reference_entity": matches[0]["reference_entity"],
        "sector":           matches[0]["sector"],
        "rating":           matches[0]["rating"],
        "term_structure":   curve,
    })


def _cds_screener(
    min_spread: float = 0,
    max_spread: float = 9999,
    sector: str = "",
    rating: str = "",
) -> str:
    # Filter on 5y tenor only for screener
    rows = [r for r in _CDS_DATA if r["tenor_years"] == 5]
    rows = [r for r in rows if min_spread <= r["spread_bps"] <= max_spread]
    if sector:
        rows = [r for r in rows if sector.lower() in r["sector"].lower()]
    if rating:
        rows = [r for r in rows if r["rating"].upper() == rating.upper()]
    rows = sorted(rows, key=lambda x: x["spread_bps"])
    return _fmt({
        "filters": {
            "min_spread_bps": min_spread,
            "max_spread_bps": max_spread,
            "sector":         sector or "all",
            "rating":         rating or "all",
        },
        "results":       rows,
        "result_count":  len(rows),
    })


# ── MCP Server ──────────────────────────────────────────────────────────────

server = Server("cds-mcp-server")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="cds_list_entities",
            description=(
                "List all CDS reference entities with 1y/5y/10y spread summary. "
                "Covers ~50 corporates and sovereigns across HY, IG, and EM sectors. "
                "Use to discover available entities before calling cds_curve or cds_get_spread."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="cds_get_spread",
            description=(
                "Get CDS spread for a specific reference entity at a specific tenor. "
                "Returns spread_bps, z_spread_bps, and upfront_pct. "
                "Valid tenors: 1, 3, 5, 7, 10 (years)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "reference_entity": {
                        "type": "string",
                        "description": "Reference entity name (e.g. 'Ford Motor Credit', 'Brazil', 'Apple Inc')",
                    },
                    "tenor_years": {
                        "type": "integer",
                        "description": "Tenor in years: 1, 3, 5, 7, or 10",
                    },
                },
                "required": ["reference_entity", "tenor_years"],
            },
        ),
        types.Tool(
            name="cds_curve",
            description=(
                "Get the full CDS term structure (1/3/5/7/10y) for a reference entity. "
                "Shows the complete credit curve: spread_bps and z_spread_bps at each tenor. "
                "Use for credit curve shape analysis (inversion, steepness)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "reference_entity": {
                        "type": "string",
                        "description": "Reference entity name",
                    },
                },
                "required": ["reference_entity"],
            },
        ),
        types.Tool(
            name="cds_screener",
            description=(
                "Screen CDS entities by spread range, sector, or rating (5y tenor). "
                "Use to find distressed credits (high spread), investment grade (low spread), "
                "or sector-specific credit views."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "min_spread": {
                        "type": "number",
                        "description": "Minimum 5y spread in bps (default: 0)",
                        "default": 0,
                    },
                    "max_spread": {
                        "type": "number",
                        "description": "Maximum 5y spread in bps (default: 9999)",
                        "default": 9999,
                    },
                    "sector": {
                        "type": "string",
                        "description": "Sector filter (partial match): Energy, Financials, Healthcare, Sovereign, Telecom, etc.",
                        "default": "",
                    },
                    "rating": {
                        "type": "string",
                        "description": "Exact rating filter: AAA, AA, A, BBB, BB, B, CCC, etc.",
                        "default": "",
                    },
                },
                "required": [],
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
    if name == "cds_list_entities":
        return _cds_list_entities()
    if name == "cds_get_spread":
        return _cds_get_spread(
            reference_entity=args["reference_entity"],
            tenor_years=int(args["tenor_years"]),
        )
    if name == "cds_curve":
        return _cds_curve(args["reference_entity"])
    if name == "cds_screener":
        return _cds_screener(
            min_spread=float(args.get("min_spread", 0)),
            max_spread=float(args.get("max_spread", 9999)),
            sector=args.get("sector", ""),
            rating=args.get("rating", ""),
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
