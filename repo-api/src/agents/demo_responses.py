"""
Demo Mode — Pre-scripted financial responses for presentations.

Activated via DEMO_MODE_ENABLED=true in .env.
Queries are matched by keyword (case-insensitive). First match wins.
Unmatched queries fall through to the normal agent pipeline
(LLM_PROVIDER=ollama or mock as fallback).

Usage:
    from src.agents.demo_responses import get_demo_response

    content = get_demo_response(user_query)
    if content:
        return pre_scripted_response(content)
    # else: run normal agent flow
"""

from __future__ import annotations


def get_demo_response(query: str) -> str | None:
    """
    Return a pre-scripted response if the query matches a demo scenario.
    Returns None if no match — caller should run normal agent flow.
    """
    q = query.lower()
    for scenario in _DEMO_SCENARIOS:
        if any(kw in q for kw in scenario["patterns"]):
            return scenario["response"]
    return None


# ── Demo Scenarios ────────────────────────────────────────────────────────────
# Order matters: more specific patterns first.

_DEMO_SCENARIOS = [

    # ── 1. HY Portfolio Holdings ─────────────────────────────────────────────
    {
        "patterns": ["hy_main", "high yield", "hy holding", "hy portfolio"],
        "response": """\
## HY_MAIN — High Yield Portfolio Holdings

**Portfolio Summary**
| Metric | Value |
|--------|-------|
| NAV | $185.4M |
| Positions | 15 |
| Avg Duration | 4.2 yrs |
| Avg Spread | 312 bps |
| Desk | HY |

**Top 10 Holdings (by Market Value)**

| Rank | Bond | ISIN | MV (USD) | Weight | Duration | Spread |
|------|------|------|----------|--------|----------|--------|
| 1 | Ford Motor Credit 2028 | US1000001002 | $18.2M | 9.8% | 3.1y | 287 bps |
| 2 | Sprint Corp 2029 | US1000001003 | $15.1M | 8.2% | 4.5y | 421 bps |
| 3 | Carnival Corp 2027 | US1000001004 | $13.8M | 7.4% | 2.8y | 375 bps |
| 4 | Tenet Healthcare 2030 | US1000001005 | $12.9M | 7.0% | 5.1y | 394 bps |
| 5 | Bausch Health 2028 | US1000001006 | $11.5M | 6.2% | 3.7y | 511 bps |
| 6 | Altice USA 2029 | US1000001007 | $10.8M | 5.8% | 4.2y | 478 bps |
| 7 | Carvana 2027 | US1000001008 | $10.2M | 5.5% | 2.9y | 682 bps |
| 8 | Windstream 2028 | US1000001009 | $9.6M | 5.2% | 3.5y | 638 bps |
| 9 | Intelsat 2026 | US1000001010 | $8.9M | 4.8% | 1.9y | 923 bps |
| 10 | Ford Motor Credit 2030 | US1000001011 | $8.3M | 4.5% | 5.2y | 291 bps |

**Key Observations**
- Top 5 positions = 38.6% of NAV (moderate concentration)
- Telecom overweight: Altice, Windstream, Sprint = 19.2% combined
- 2 distressed names: Intelsat (923 bps) and Carvana (682 bps)
- Average spread has tightened 18 bps vs. prior month

**Confidence: HIGH** — data sourced from portfolio MCP server (live positions).

---
*Sources: portfolio_holdings_tool | portfolio_mcp_server*""",
    },

    # ── 2. IG Portfolio Holdings ──────────────────────────────────────────────
    {
        "patterns": ["ig_core", "investment grade", "ig holding", "ig portfolio"],
        "response": """\
## IG_CORE — Investment Grade Portfolio Holdings

**Portfolio Summary**
| Metric | Value |
|--------|-------|
| NAV | $312.1M |
| Positions | 15 |
| Avg Duration | 6.8 yrs |
| Avg Spread | 89 bps |
| Desk | IG |

**Top 10 Holdings (by Market Value)**

| Rank | Bond | ISIN | MV (USD) | Weight | Duration | Spread |
|------|------|------|----------|--------|----------|--------|
| 1 | Apple Inc 2032 | US1000001020 | $32.5M | 10.4% | 7.2y | 28 bps |
| 2 | JPMorgan Chase 2031 | US1000001021 | $28.3M | 9.1% | 6.5y | 56 bps |
| 3 | Microsoft Corp 2033 | US1000001022 | $24.8M | 7.9% | 8.1y | 19 bps |
| 4 | Amazon.com 2030 | US1000001023 | $22.1M | 7.1% | 5.8y | 33 bps |
| 5 | Bank of America 2029 | US1000001024 | $19.6M | 6.3% | 4.9y | 63 bps |
| 6 | Goldman Sachs 2031 | US1000001025 | $18.4M | 5.9% | 6.7y | 79 bps |
| 7 | Verizon Comm 2032 | US1000001026 | $17.2M | 5.5% | 7.4y | 91 bps |
| 8 | AT&T Inc 2030 | US1000001027 | $15.9M | 5.1% | 5.9y | 112 bps |
| 9 | Wells Fargo 2029 | US1000001028 | $14.7M | 4.7% | 4.8y | 69 bps |
| 10 | Berkshire Hathaway 2035 | US1000001029 | $13.5M | 4.3% | 10.2y | 42 bps |

**Key Observations**
- Tech names (Apple, MSFT, Amazon) = 25.4% of NAV — significant overweight
- Portfolio duration 6.8y is above benchmark (5.5y) — long bias
- Spreads very tight across the board; limited room for further compression
- No distressed names; lowest-rated holding is AT&T (BBB, 112 bps)

**Confidence: HIGH** — data sourced from portfolio MCP server.

---
*Sources: portfolio_holdings_tool | portfolio_mcp_server*""",
    },

    # ── 3. EM Portfolio ───────────────────────────────────────────────────────
    {
        "patterns": ["em_blend", "emerging market", "em portfolio", "em exposure"],
        "response": """\
## EM_BLEND — Emerging Markets Exposure Analysis

**Portfolio Summary**
| Metric | Value |
|--------|-------|
| NAV | $146.2M |
| Positions | 15 |
| Avg Duration | 7.9 yrs |
| Avg Spread | 218 bps |
| Desk | EM |

**Exposure by Sector**

| Sector | MV (USD) | Weight | Avg Spread | Avg Duration |
|--------|----------|--------|------------|--------------|
| Sovereign | $58.4M | 39.9% | 185 bps | 8.4y |
| Corporates | $35.1M | 24.0% | 231 bps | 6.9y |
| Quasi-Sovereign | $24.6M | 16.8% | 198 bps | 8.1y |
| Financials | $16.8M | 11.5% | 242 bps | 6.2y |
| Energy | $11.3M | 7.7% | 278 bps | 7.5y |

**Top Sovereign Exposures**

| Country | MV (USD) | Weight | Rating | 5y CDS |
|---------|----------|--------|--------|--------|
| Brazil | $18.2M | 12.4% | BB | 188 bps |
| Mexico | $14.5M | 9.9% | BBB- | 133 bps |
| Indonesia | $12.1M | 8.3% | BBB | 122 bps |
| South Africa | $8.9M | 6.1% | BB- | 252 bps |
| Colombia | $4.7M | 3.2% | BB+ | 217 bps |

**Key Observations**
- Brazil + Mexico = 22.3% of NAV — key EM beta exposure
- Underweight EM corporate vs. benchmark (24% vs. 31%)
- South Africa spread has widened 35 bps this week — monitor closely
- Duration at 7.9y is high relative to credit quality (BB avg)

**Confidence: HIGH** — sourced from portfolio + CDS MCP servers.

---
*Sources: portfolio_exposure_tool | cds_screener_tool*""",
    },

    # ── 4. Portfolio List (general overview) ─────────────────────────────────
    {
        "patterns": ["list portfolio", "all portfolio", "show portfolio", "portfolio overview",
                     "portfolios", "how many portfolio"],
        "response": """\
## Portfolio Overview — All Desks

There are **5 portfolios** across 4 trading desks with a combined NAV of **$1.34B**.

| # | Portfolio ID | Name | Desk | NAV | Positions | Avg Spread | Avg Duration |
|---|---|---|---|---|---|---|---|
| 1 | HY_MAIN | High Yield Main | HY | $185.4M | 15 | 312 bps | 4.2y |
| 2 | IG_CORE | Investment Grade Core | IG | $312.1M | 15 | 89 bps | 6.8y |
| 3 | EM_BLEND | Emerging Markets Blend | EM | $146.2M | 15 | 218 bps | 7.9y |
| 4 | RATES_GOV | Rates Government | RATES | $278.5M | 15 | 22 bps | 9.3y |
| 5 | MULTI_STRAT | Multi-Strategy | MULTI | $423.0M | 15 | 167 bps | 5.1y |

**Quick Highlights**
- **Largest portfolio**: MULTI_STRAT ($423M) — cross-desk vehicle with mixed exposure
- **Highest yield**: HY_MAIN (avg spread 312 bps) — sub-investment grade, BB/B rated
- **Lowest risk**: RATES_GOV (avg spread 22 bps, 9.3y duration) — UST/Agency heavy
- **IG_CORE** is the second largest ($312M) with tech-heavy concentration
- **EM_BLEND** offers emerging markets beta with BB avg rating

**Use cases for each portfolio:**
- `HY_MAIN` → credit selection, distressed analysis, CDS hedging
- `IG_CORE` → rates sensitivity, duration management, IG credit
- `EM_BLEND` → EM sovereign/corporate, cross-asset correlation
- `RATES_GOV` → macro rates, curve positioning, repo
- `MULTI_STRAT` → cross-asset strategies, relative value

**Confidence: HIGH** — real-time data from portfolio MCP server.

---
*Sources: portfolio_list_tool | portfolio_mcp_server*""",
    },

    # ── 5. CDS Spreads ────────────────────────────────────────────────────────
    {
        "patterns": ["cds", "credit default swap", "spread", "credit spread"],
        "response": """\
## CDS Market — Credit Spread Snapshot

**Market Overview** *(as of 2026-02-21)*

**Distressed / High Yield (5y CDS > 300 bps)**

| Entity | Sector | Rating | 1y | 5y | 10y | MoM Change |
|--------|--------|--------|----|----|-----|------------|
| Ukraine | Sovereign | CCC | 1,020 | 1,854 | 2,102 | +142 bps |
| Argentina | Sovereign | CCC+ | 528 | 964 | 1,088 | -87 bps |
| JC Penney | Retail | CCC | 660 | 1,203 | 1,381 | +51 bps |
| Rite Aid | Healthcare | CCC | 605 | 1,104 | 1,272 | +28 bps |
| Intelsat | Satellite | CCC | 506 | 923 | 1,058 | -15 bps |
| Carvana | Auto Retail | B- | 374 | 682 | 784 | +63 bps |

**Investment Grade (5y CDS < 100 bps)**

| Entity | Sector | Rating | 1y | 5y | 10y | MoM Change |
|--------|--------|--------|----|----|-----|------------|
| Microsoft Corp | Technology | AAA | 10 | 18 | 22 | -2 bps |
| Walmart Inc | Retail | AA | 12 | 22 | 27 | 0 bps |
| Apple Inc | Technology | AA+ | 15 | 28 | 34 | -1 bps |
| Exxon Mobil | Energy | AA- | 23 | 42 | 51 | +3 bps |
| JPMorgan Chase | Financials | A- | 30 | 55 | 67 | +5 bps |

**Key Observations**
- Argentina tightening sharply (-87 bps) on debt restructuring progress
- Carvana widening (+63 bps) on deteriorating auto credit fundamentals
- IG names remain well-anchored; tech (MSFT, Apple) near historical tights
- Ukraine spread elevated but stable; monitoring geopolitical developments

**CDS Curve Shape Analysis — Ford Motor Credit**
| Tenor | Spread | Z-Spread |
|-------|--------|----------|
| 1y | 157 bps | 163 bps |
| 3y | 228 bps | 235 bps |
| 5y | 285 bps | 292 bps |
| 7y | 320 bps | 328 bps |
| 10y | 348 bps | 356 bps |
*Upward sloping curve — no inversion, market not pricing near-term default*

**Confidence: HIGH** — live data from CDS MCP server.

---
*Sources: cds_screener_tool | cds_curve_tool | cds_mcp_server*""",
    },

    # ── 6. KDB / RFQ Analytics ────────────────────────────────────────────────
    {
        "patterns": ["rfq", "trader", "hit rate", "kdb", "bond rfq", "trading performance"],
        "response": """\
## Bond RFQ Analytics — Trading Performance

**Query Parameters:** All desks | Last 6 months | Top 20 traders by hit rate

**Top Traders by Hit Rate**

| Rank | Trader | Desk | RFQs | Hit Rate | Avg Spread | Total Notional | Wins |
|------|--------|------|------|----------|------------|----------------|------|
| 1 | Sarah Chen | IG | 1,847 | 68.4% | 87 bps | $4.2B | 1,263 |
| 2 | Marcus Webb | RATES | 2,103 | 65.1% | 18 bps | $8.9B | 1,369 |
| 3 | Priya Sharma | IG | 1,562 | 63.8% | 91 bps | $3.1B | 997 |
| 4 | Tom Keller | HY | 2,891 | 61.2% | 318 bps | $2.8B | 1,769 |
| 5 | Ana Ruiz | EM | 1,204 | 58.9% | 224 bps | $1.9B | 709 |
| 6 | James Liu | HY | 3,102 | 57.4% | 295 bps | $3.3B | 1,781 |
| 7 | Maria Santos | EM | 987 | 55.3% | 241 bps | $1.4B | 546 |
| 8 | David Park | RATES | 1,789 | 54.8% | 21 bps | $6.7B | 980 |
| 9 | Lena Fischer | IG | 1,103 | 53.1% | 96 bps | $2.4B | 586 |
| 10 | Omar Hassan | HY | 2,456 | 51.7% | 342 bps | $2.1B | 1,270 |

**Desk-Level Summary**

| Desk | Total RFQs | Avg Hit Rate | Total Notional | Avg Spread |
|------|------------|--------------|----------------|------------|
| RATES | 12,408 | 63.1% | $48.2B | 19 bps |
| IG | 9,847 | 61.8% | $22.4B | 89 bps |
| EM | 6,203 | 57.2% | $9.8B | 231 bps |
| HY | 14,521 | 55.6% | $18.9B | 308 bps |

**Key Observations**
- **Sarah Chen (IG)** is top performer by hit rate (68.4%) — 2nd year running
- **RATES desk** has highest win rate due to tighter bid-ask spreads and market structure
- **HY desk** leads by volume (14,521 RFQs) but lower hit rate — more competitive market
- **Tom Keller** top HY trader with 61.2% — significantly above desk average (55.6%)
- EM hit rates declining vs. prior quarter (-2.3%) — increasing competition from algo dealers

**Confidence: HIGH** — aggregated from 6 months of historical RFQ data (KDB/Parquet store).

---
*Sources: kdb_rfq_analytics_tool | kdb_mcp_server*""",
    },

    # ── 7. ETF Flows ──────────────────────────────────────────────────────────
    {
        "patterns": ["etf", "exchange traded fund", "etf flow", "etf holding", "etf list"],
        "response": """\
## ETF Market — Fixed Income Flow Analysis

**Top Fixed Income ETFs by AUM**

| Ticker | Name | Category | AUM | 1W Flow | 1M Flow | YTD Flow |
|--------|------|----------|-----|---------|---------|----------|
| LQD | iShares IG Corp Bond | IG Corp | $38.2B | +$412M | +$1.2B | +$3.8B |
| HYG | iShares HY Corp Bond | HY Corp | $19.8B | -$287M | -$890M | -$2.1B |
| AGG | iShares Core US Agg | Broad Mkt | $102.4B | +$1.1B | +$3.4B | +$8.9B |
| TLT | iShares 20+ Year Treasury | Long Rates | $52.1B | +$890M | +$2.8B | +$6.2B |
| EMB | iShares JPM USD EM Bond | EM Debt | $14.6B | +$156M | +$420M | +$980M |
| JNK | SPDR Barclays HY | HY Corp | $9.2B | -$198M | -$612M | -$1.4B |
| VCIT | Vanguard Interm-Term Corp | IG Corp | $46.8B | +$320M | +$987M | +$2.7B |

**Flow Signals (Last 4 Weeks)**
- ✅ **IG Credit (LQD, VCIT):** Consistent inflows — risk-on with credit quality preference
- ✅ **Duration (TLT):** Strong inflows — rate cut expectations supporting long-end
- ✅ **EM Debt (EMB):** Modest but steady inflows — selective EM recovery
- ⚠️ **HY Credit (HYG, JNK):** Sustained outflows — caution on leveraged credit
- ✅ **Broad Market (AGG):** Largest absolute inflows — core allocation demand

**Top ETF Holdings Snapshot — LQD (IG Corporate)**

| Rank | Issuer | Weight | MV | Sector |
|------|--------|--------|-----|--------|
| 1 | Apple Inc | 3.2% | $1.22B | Technology |
| 2 | Microsoft Corp | 2.9% | $1.11B | Technology |
| 3 | JPMorgan Chase | 2.4% | $917M | Financials |
| 4 | Amazon.com | 2.1% | $802M | Technology |
| 5 | Bank of America | 1.9% | $726M | Financials |

**Portfolio Implications**
- HY outflows suggest pressure on HY desk spreads — monitor HY_MAIN hedges
- LQD inflows supportive of IG_CORE marks; IG spreads likely to hold
- TLT inflows reduce pressure on RATES_GOV duration positioning

**Confidence: HIGH** — ETF flow data from ETF MCP server.

---
*Sources: etf_flows_tool | etf_top_holdings_tool | etf_mcp_server*""",
    },

    # ── 8. Risk / VaR ─────────────────────────────────────────────────────────
    {
        "patterns": ["var", "value at risk", "risk metric", "dv01", "cs01", "duration risk",
                     "pnl", "p&l", "profit and loss"],
        "response": """\
## Risk & P&L Dashboard — HY Desk

**Daily P&L Summary** *(as of market close)*

| Portfolio | Daily P&L | MTD P&L | YTD P&L | Unrealized |
|-----------|-----------|---------|---------|------------|
| HY_MAIN | +$142K | +$1.8M | +$4.2M | +$3.1M |
| IG_CORE | +$88K | +$2.1M | +$6.8M | +$5.4M |
| EM_BLEND | -$203K | +$0.9M | +$2.1M | +$1.6M |
| RATES_GOV | +$312K | +$3.4M | +$9.1M | +$8.2M |
| MULTI_STRAT | +$521K | +$4.2M | +$11.8M | +$9.7M |
| **TOTAL** | **+$860K** | **+$12.4M** | **+$34.0M** | **+$28.0M** |

**Risk Metrics — HY_MAIN Portfolio**

| Metric | Value | Limit | Utilization |
|--------|-------|-------|-------------|
| VaR (95%, 1-day) | $3.2M | $8.0M | 40% ✅ |
| VaR (99%, 1-day) | $5.1M | $12.0M | 43% ✅ |
| DV01 | $18,500/bp | $50,000/bp | 37% ✅ |
| CS01 | $2.1M/100bp | $5.0M/100bp | 42% ✅ |
| Spread Duration | 1.2y | 2.0y | 60% ⚠️ |
| Max Position | 9.8% (Ford) | 10.0% | 98% ⚠️ |

**Stress Scenarios**

| Scenario | P&L Impact |
|----------|------------|
| Spreads +100 bps across HY | -$12.4M |
| 10y Treasury +50 bps | -$3.2M |
| EM sovereign crisis (spreads +200 bps) | -$8.1M |
| HY default wave (10% of book) | -$18.5M |
| Combined market stress | -$28.3M |

**Key Risk Alerts**
- ⚠️ Ford Motor Credit position approaching 10% concentration limit (currently 9.8%)
- ⚠️ Spread duration at 60% of limit — elevated after recent additions
- ✅ VaR well within limits across all portfolios
- ℹ️ EM_BLEND showing -$203K today — South Africa spread widening (see CDS desk)

**Confidence: HIGH** — risk metrics from Risk PnL agent + portfolio MCP server.

---
*Sources: risk_pnl_agent | portfolio_exposure_tool*""",
    },

    # ── 9. Rates / Government ─────────────────────────────────────────────────
    {
        "patterns": ["rates_gov", "rates portfolio", "government bond", "treasury", "rates desk"],
        "response": """\
## RATES_GOV — Government Rates Portfolio

**Portfolio Summary**
| Metric | Value |
|--------|-------|
| NAV | $278.5M |
| Positions | 15 |
| Avg Duration | 9.3 yrs |
| Avg Spread | 22 bps |
| Desk | RATES |
| Hit Rate (RFQ) | 63.1% — best desk |

**Holdings by Sub-Sector**

| Sub-Sector | MV (USD) | Weight | Avg Duration | Avg Spread |
|------------|----------|--------|--------------|------------|
| US Treasury | $98.4M | 35.3% | 8.2y | 0 bps |
| Agency (FNMA/FHLB) | $72.1M | 25.9% | 6.8y | 28 bps |
| Supranational (IBRD/EIB) | $48.2M | 17.3% | 10.1y | 35 bps |
| TIPS | $31.9M | 11.5% | 7.4y | 42 bps |
| Municipal | $27.9M | 10.0% | 12.8y | 48 bps |

**US Treasury Curve Positioning**

| Tenor | Notional | DV01 | Position vs. Benchmark |
|-------|----------|------|------------------------|
| 2y | $18.2M | $3,640 | -$2.1M (short) |
| 5y | $28.4M | $14,200 | +$4.3M (long) |
| 10y | $31.5M | $31,500 | +$6.8M (long) |
| 30y | $20.3M | $60,900 | +$2.1M (long) |
*Net: Long duration vs. benchmark by 3.2 years — bullish rates view*

**Key Observations**
- Significant duration extension vs. benchmark — PM has conviction on rate cuts
- TIPS overweight (11.5%) as inflation hedge given elevated CPI uncertainty
- Municipal underweight vs. index — tax efficiency less relevant in portfolio context
- RFQ hit rate 63.1% — best desk in the firm (tight spreads, high liquidity)

**Confidence: HIGH** — portfolio + KDB data.

---
*Sources: portfolio_holdings_tool | kdb_rfq_analytics_tool*""",
    },

    # ── 10. System capabilities / general help ───────────────────────────────
    {
        "patterns": ["what can you do", "help", "capabilities", "what do you know",
                     "what is this", "show me what", "demo", "introduce"],
        "response": """\
## Agentic AI System — Financial Intelligence Platform

I'm a multi-agent AI system purpose-built for fixed income and credit markets.
I orchestrate specialized agents and real-time data tools to answer complex financial queries.

---

### What I Can Do

**Portfolio Analytics**
- Holdings, weights, and exposure breakdowns for 5 portfolios (HY, IG, EM, Rates, Multi)
- Concentration risk, duration positioning, sector allocation
- *Try: "show me HY portfolio holdings" or "what's the EM exposure?"*

**Credit Markets (CDS)**
- Live CDS spreads for ~50 reference entities (corporates + sovereigns)
- Full term structure (1y/3y/5y/7y/10y), curve shape analysis
- Screener by spread range, sector, or rating
- *Try: "show CDS spreads for Ford" or "screen distressed credits above 500 bps"*

**RFQ & Trading Analytics (KDB)**
- Historical bond RFQ data — hit rates, notional, spread analytics
- Trader performance ranking, desk comparison, time-series trends
- *Try: "who are the top traders in HY by hit rate?" or "show me KDB desk analytics"*

**ETF Flow Intelligence**
- AUM and fund flows for major fixed income ETFs (LQD, HYG, TLT, AGG, EMB, etc.)
- Top holdings with weights
- *Try: "show ETF flows" or "what are LQD top holdings?"*

**Risk & P&L**
- VaR, DV01, CS01, spread duration across portfolios
- Daily/MTD/YTD P&L, stress scenarios
- Limit utilization and alerts
- *Try: "show me risk metrics" or "what's the VaR for HY?"*

---

### Architecture

```
You → API Gateway (FastAPI)
        ↓ LLM Router (Claude Haiku) classifies intent
        ↓ Parallel Specialist Agents
   ┌────┬────┬──────┬─────┬──────┐
   KDB  AMPS Portfolio CDS  ETF
   └────┴────┴──────┴─────┴──────┘
        ↓ MCP Tools (HTTP/SSE)
      DynamoDB  OpenSearch  LocalStack
```

**Infrastructure**: AWS ECS Fargate | DynamoDB | OpenSearch | MCP Gateway | Langfuse

---

*This system is running in demo mode. Ask me about any of the topics above!*""",
    },
]
