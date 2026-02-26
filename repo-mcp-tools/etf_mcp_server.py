#!/usr/bin/env python3
"""
ETF MCP Server — Phase 3

Exposes ETF analytics (NAV, AUM, flows, basket) as MCP tools.
POC data: 15 ETFs with ~30 holdings each, generated in-memory at startup.

Tools:
  - etf_list          → all ETFs with summary (NAV, AUM, premium/discount, YTD flow)
  - etf_details       → full detail for one ETF
  - etf_flows         → creation/redemption flow history
  - etf_top_holdings  → basket composition (top N by weight)

Schema:
  etf_summary:  ticker, name, asset_class, aum_usd, nav, market_price,
                premium_discount_bps, ytd_return_pct, ytd_flow_usd,
                expense_ratio_bps, num_holdings
  etf_holdings: ticker, rank, isin, bond_name, issuer, weight_pct,
                market_value_usd, sector, rating
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
    random.seed(77)

    etfs = [
        # (ticker, name, asset_class, approx_aum_bn, nav_base, expense_bps, ytd_return_pct, ytd_flow_bn)
        ("HYG",  "iShares iBoxx HY Corporate Bond ETF", "HighYield",   14.2,  76.50,  49,  2.1,  -1.4),
        ("JNK",  "SPDR Bloomberg HY Bond ETF",          "HighYield",    9.8,  92.30,  40,  2.0,  -0.9),
        ("LQD",  "iShares iBoxx IG Corporate Bond ETF", "InvestGrade", 28.5, 108.20,  14,  1.4,   2.1),
        ("EMB",  "iShares JP Morgan EM Bond ETF",       "EmergingMkt", 13.1,  87.60,  39,  1.8,   0.6),
        ("TLT",  "iShares 20+ Year Treasury Bond ETF",  "Government",  24.7,  91.40,  15, -3.2,   3.8),
        ("AGG",  "iShares Core US Aggregate Bond ETF",  "Aggregate",   98.3,  96.80,   3,  0.9,   4.2),
        ("BKLN", "Invesco Senior Loan ETF",             "HighYield",    6.4,  21.30,  65,  1.8,  -0.3),
        ("ANGL", "VanEck Fallen Angel HY Bond ETF",     "HighYield",    4.2,  29.10,  35,  2.8,   0.4),
        ("FALN", "iShares Fallen Angels HY Bond ETF",   "HighYield",    0.8,  26.80,  25,  2.6,   0.1),
        ("HYDB", "iShares HY Dynamic Alloc Bond ETF",   "HighYield",    0.5,  48.40,  35,  2.3,   0.0),
        ("VCSH", "Vanguard Short-Term Corp Bond ETF",   "InvestGrade", 40.1,  77.60,   4,  1.2,   1.8),
        ("VCIT", "Vanguard Interm-Term Corp Bond ETF",  "InvestGrade", 46.8,  81.40,   4,  1.6,   2.4),
        ("SHY",  "iShares 1-3 Year Treasury Bond ETF",  "Government",  20.5,  81.90,  15,  0.5,   0.8),
        ("IEF",  "iShares 7-10 Year Treasury Bond ETF", "Government",  18.7,  94.20,  15, -1.1,   1.2),
        ("IGIB", "iShares Interm-Term Corp Bond ETF",   "InvestGrade", 11.4,  52.80,   6,  1.7,   0.9),
    ]

    issuers_by_class = {
        "HighYield":   ["Ford Motor Credit", "Sprint Corp", "Carnival Corp", "Tenet Healthcare",
                        "Bausch Health", "Altice USA", "Carvana", "Frontier Comm",
                        "Windstream", "American Airlines", "JC Penney", "Rite Aid",
                        "Party City", "Bed Bath Beyond", "Revlon"],
        "InvestGrade": ["Apple Inc", "JPMorgan Chase", "Microsoft Corp", "Amazon.com",
                        "Bank of America", "Goldman Sachs", "Wells Fargo", "Verizon Comm",
                        "AT&T Inc", "Berkshire Hathaway", "UnitedHealth", "Home Depot",
                        "Walmart Inc", "Alphabet Inc", "Meta Platforms"],
        "EmergingMkt": ["Brazil 2030", "Mexico 2032", "Turkey 2028", "Indonesia 2035",
                        "South Africa 2031", "Petrobras", "Pemex", "Vale SA",
                        "Colombia 2029", "Egypt 2027", "Nigeria 2031", "Ecopetrol",
                        "Cemex", "Korea Dev Bank", "Export-Import China"],
        "Government":  ["US Treasury 2Y", "US Treasury 5Y", "US Treasury 10Y", "US Treasury 20Y",
                        "US Treasury 30Y", "FNMA 3Y", "FHLB 2Y", "Freddie Mac 5Y",
                        "Ginnie Mae 10Y", "US TIPS 5Y", "US TIPS 10Y", "IBRD 3Y",
                        "EIB 5Y", "ADB 3Y", "NY State GO 10Y"],
        "Aggregate":   ["US Treasury 10Y", "Apple Inc", "JPMorgan Chase", "FNMA 3Y",
                        "Microsoft Corp", "Bank of America", "Verizon Comm", "AT&T Inc",
                        "FHLB 2Y", "Amazon.com", "Goldman Sachs", "Walmart Inc",
                        "US Treasury 5Y", "Boeing Co", "UnitedHealth"],
        "Mixed":       ["Ford Motor Credit", "Apple Inc", "US Treasury 10Y", "Brazil 2030",
                        "JPMorgan Chase", "Sprint Corp", "FNMA 3Y", "Mexico 2032",
                        "Microsoft Corp", "Altice USA", "Amazon.com", "Turkey 2028",
                        "Bank of America", "Petrobras", "Carnival Corp"],
    }

    sectors_by_class = {
        "HighYield":   ["Automotive", "Telecom", "Leisure", "Healthcare", "Retail",
                        "Energy", "Technology", "Industrials", "Media", "Financials"],
        "InvestGrade": ["Technology", "Financials", "Consumer", "Utilities", "Telecom",
                        "Healthcare", "Retail", "Industrials", "Energy", "Media"],
        "EmergingMkt": ["Sovereign", "Energy", "Mining", "Materials", "Financials",
                        "Quasi-Sovereign", "Corporates", "Infrastructure", "Utilities", "Consumer"],
        "Government":  ["UST", "Agency", "Muni", "Supranational", "TIPS",
                        "Agency MBS", "CMBS", "ABS", "Covered", "Municipal"],
        "Aggregate":   ["UST", "Financials", "Technology", "Agency", "Consumer",
                        "Telecom", "Utilities", "Healthcare", "Energy", "Industrials"],
        "Mixed":       ["UST", "Technology", "Financials", "Sovereign", "Energy",
                        "Healthcare", "Telecom", "Consumer", "Industrials", "Materials"],
    }

    ratings_by_class = {
        "HighYield":   ["BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC", "BB+", "BB"],
        "InvestGrade": ["AA+", "AA", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "A+", "A"],
        "EmergingMkt": ["BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "BB", "BBB-", "BB+"],
        "Government":  ["AAA", "AAA", "AAA", "AAA", "AAA", "AA+", "AA+", "AAA", "AAA", "AAA"],
        "Aggregate":   ["AAA", "A", "A+", "AA+", "A-", "BBB+", "BBB", "AA", "AAA", "BBB-"],
        "Mixed":       ["AAA", "AA+", "BB+", "BB", "A+", "B", "AA+", "BBB-", "A", "BB+"],
    }

    etf_summaries = []
    etf_holdings_map: dict[str, list] = {}
    isin_counter = 9000

    for ticker, name, asset_class, aum_bn, nav_base, exp_bps, ytd_ret, ytd_flow_bn in etfs:
        # Small random noise on NAV
        nav = round(nav_base * random.uniform(0.998, 1.002), 2)
        mkt_price = round(nav * random.uniform(0.9985, 1.0015), 2)
        premium_disc = round((mkt_price / nav - 1) * 10000, 1)
        aum = round(aum_bn * 1e9, 0)
        ytd_flow = round(ytd_flow_bn * 1e9, 0)

        etf_summaries.append({
            "ticker":               ticker,
            "name":                 name,
            "asset_class":          asset_class,
            "aum_usd":              aum,
            "nav":                  nav,
            "market_price":         mkt_price,
            "premium_discount_bps": premium_disc,
            "ytd_return_pct":       ytd_ret,
            "ytd_flow_usd":         ytd_flow,
            "expense_ratio_bps":    exp_bps,
            "num_holdings":         30,
        })

        # Build holdings
        ac_key = asset_class if asset_class in issuers_by_class else "Mixed"
        issuers = issuers_by_class[ac_key]
        sectors = sectors_by_class[ac_key]
        ratings = ratings_by_class[ac_key]

        weights = [random.uniform(0.5, 8.0) for _ in range(30)]
        w_sum = sum(weights)
        weights = [w / w_sum for w in weights]

        holdings = []
        for rank in range(1, 31):
            issuer = issuers[(rank - 1) % len(issuers)]
            isin_counter += 1
            mv = aum * weights[rank - 1]
            holdings.append({
                "ticker":           ticker,
                "rank":             rank,
                "isin":             f"US{isin_counter:010d}",
                "bond_name":        f"{issuer[:20]} {random.choice(['2026','2027','2028','2029','2030'])}",
                "issuer":           issuer,
                "weight_pct":       round(weights[rank - 1] * 100, 4),
                "market_value_usd": round(mv, 2),
                "sector":           sectors[(rank - 1) % len(sectors)],
                "rating":           ratings[(rank - 1) % len(ratings)],
            })
        etf_holdings_map[ticker] = sorted(holdings, key=lambda x: x["weight_pct"], reverse=True)
        for i, h in enumerate(etf_holdings_map[ticker], 1):
            h["rank"] = i

    return etf_summaries, etf_holdings_map


_ETF_SUMMARIES, _ETF_HOLDINGS = _build_poc_data()

# Simulate weekly flow history (last 12 weeks)
def _build_flow_history(ticker: str, ytd_flow: float) -> list[dict]:
    import random
    random.seed(hash(ticker) % 1000)
    base_weekly = ytd_flow / 52
    rows = []
    for w in range(12, 0, -1):
        creation = max(0, base_weekly * random.uniform(0.0, 2.0))
        redemption = max(0, base_weekly * random.uniform(0.0, 2.0))
        net = creation - redemption
        rows.append({
            "week_end":    f"2026-W{10 - w + 12:02d}",
            "creation_usd": round(creation, 0),
            "redemption_usd": round(redemption, 0),
            "net_flow_usd": round(net, 0),
        })
    return rows


# ── Tool helpers ────────────────────────────────────────────────────────────

def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _etf_list() -> str:
    return _fmt({"etfs": _ETF_SUMMARIES, "total": len(_ETF_SUMMARIES)})


def _etf_details(ticker: str) -> str:
    ticker = ticker.upper()
    match = next((e for e in _ETF_SUMMARIES if e["ticker"] == ticker), None)
    if not match:
        known = [e["ticker"] for e in _ETF_SUMMARIES]
        return _fmt({"error": f"ETF '{ticker}' not found", "known_tickers": known})
    holdings = _ETF_HOLDINGS.get(ticker, [])
    return _fmt({**match, "top_10_holdings": holdings[:10]})


def _etf_flows(ticker: str, period: str = "12w") -> str:
    ticker = ticker.upper()
    match = next((e for e in _ETF_SUMMARIES if e["ticker"] == ticker), None)
    if not match:
        known = [e["ticker"] for e in _ETF_SUMMARIES]
        return _fmt({"error": f"ETF '{ticker}' not found", "known_tickers": known})
    history = _build_flow_history(ticker, match["ytd_flow_usd"])
    total_creation = sum(r["creation_usd"] for r in history)
    total_redemption = sum(r["redemption_usd"] for r in history)
    return _fmt({
        "ticker":            ticker,
        "period":            period,
        "total_creation_usd":    round(total_creation, 0),
        "total_redemption_usd":  round(total_redemption, 0),
        "net_flow_usd":          round(total_creation - total_redemption, 0),
        "weekly_flows":          history,
    })


def _etf_top_holdings(ticker: str, top_n: int = 10) -> str:
    ticker = ticker.upper()
    holdings = _ETF_HOLDINGS.get(ticker)
    if holdings is None:
        known = list(_ETF_HOLDINGS.keys())
        return _fmt({"error": f"ETF '{ticker}' not found", "known_tickers": known})
    top = holdings[:top_n]
    top_weight = sum(h["weight_pct"] for h in top)
    return _fmt({
        "ticker":                ticker,
        "top_n":                 top_n,
        "top_holdings_weight_pct": round(top_weight, 2),
        "holdings":              top,
    })


# ── MCP Server ──────────────────────────────────────────────────────────────

server = Server("etf-mcp-server")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="etf_list",
            description=(
                "List all ETFs with summary stats: NAV, AUM, market price, "
                "premium/discount to NAV (bps), YTD return, YTD net flows, expense ratio. "
                "Covers 15 fixed income ETFs across HY, IG, EM, Government, and Aggregate."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="etf_details",
            description=(
                "Full detail for one ETF: NAV, AUM, premium/discount, flows, plus top 10 holdings. "
                "Use etf_list first to see available tickers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "ETF ticker symbol (e.g. HYG, JNK, LQD, EMB, TLT, AGG)",
                    },
                },
                "required": ["ticker"],
            },
        ),
        types.Tool(
            name="etf_flows",
            description=(
                "Weekly creation/redemption flow history for an ETF (last 12 weeks). "
                "Use to identify if institutional investors are buying or selling the ETF. "
                "Positive net flows = creation (buying pressure), negative = redemption (selling)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "ETF ticker (e.g. HYG, LQD)",
                    },
                    "period": {
                        "type": "string",
                        "description": "Period (informational, data always shows last 12 weeks)",
                        "default": "12w",
                    },
                },
                "required": ["ticker"],
            },
        ),
        types.Tool(
            name="etf_top_holdings",
            description=(
                "Basket composition: top N holdings by weight for an ETF. "
                "Shows ISIN, bond name, issuer, weight %, market value, sector, rating."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "ETF ticker (e.g. HYG, LQD, EMB)",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Number of top holdings to return (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["ticker"],
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
    if name == "etf_list":
        return _etf_list()
    if name == "etf_details":
        return _etf_details(args["ticker"])
    if name == "etf_flows":
        return _etf_flows(args["ticker"], args.get("period", "12w"))
    if name == "etf_top_holdings":
        return _etf_top_holdings(args["ticker"], int(args.get("top_n", 10)))
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
