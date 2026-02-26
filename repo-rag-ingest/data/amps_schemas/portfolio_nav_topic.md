# AMPS Topic: portfolio_nav

## Purpose

The `portfolio_nav` topic stores **live NAV and daily P&L snapshots** for each of the 5 fixed income portfolios. Each message represents the latest computed NAV for a portfolio, updated whenever the pricing engine reruns (typically every 5–10 seconds).

Use this topic when you need real-time portfolio-level P&L, aggregate spread/duration profiles, or to monitor NAV changes intraday.

**Portfolios covered:** HY_MAIN, IG_CORE, EM_BLEND, RATES_GOV, MULTI_STRAT

**SOW tool to use:** `amps_sow_query(topic="portfolio_nav", filter=...)`

---

## Key

```
/portfolio_id
```

One record per portfolio. The key is the portfolio identifier string.

Example key value: `HY_MAIN`

---

## Fields

| Field | Type | Description | Example |
|---|---|---|---|
| `portfolio_id` | string | Portfolio identifier (SOW key) | `"HY_MAIN"` |
| `portfolio_name` | string | Human-readable portfolio name | `"High Yield Main"` |
| `desk` | string | Primary desk: HY, IG, EM, RATES, MULTI | `"HY"` |
| `total_nav_usd` | float | Total NAV in USD | `185234567.89` |
| `daily_pnl_usd` | float | Intraday P&L in USD (positive = gain) | `-234567.12` |
| `daily_pnl_bps` | float | Daily P&L as basis points of NAV | `-12.6` |
| `nav_change_pct` | float | NAV change percentage (pnl_bps / 100) | `-0.126` |
| `positions_count` | integer | Number of positions in the portfolio | `15` |
| `avg_spread_bps` | float | Weighted average OAS/spread (bps) | `342.5` |
| `avg_duration` | float | Weighted average modified duration (years) | `4.8` |
| `timestamp` | string | ISO 8601 UTC timestamp of computation | `"2025-01-15T14:30:00Z"` |

---

## Portfolio Reference

| portfolio_id | portfolio_name | desk | Approx NAV | Expected Spread Range |
|---|---|---|---|---|
| HY_MAIN | High Yield Main | HY | ~$185M | 280–420 bps |
| IG_CORE | Investment Grade Core | IG | ~$312M | 60–130 bps |
| EM_BLEND | Emerging Markets Blend | EM | ~$146M | 150–280 bps |
| RATES_GOV | Rates Government | RATES | ~$278M | 0–30 bps |
| MULTI_STRAT | Multi Strategy | MULTI | ~$423M | 120–220 bps |

---

## AMPS Filter Examples

```
# Specific portfolio lookup
/portfolio_id = 'HY_MAIN'

# Portfolios with positive P&L today
/daily_pnl_usd > 0

# Portfolios down more than 20bps today
/daily_pnl_bps < -20

# High spread portfolios (HY / EM)
/avg_spread_bps > 200

# Portfolios with short duration (< 5 years)
/avg_duration < 5.0

# Large NAV portfolios (> $200M)
/total_nav_usd > 200000000
```

---

## Example JSON Message

```json
{
  "portfolio_id": "HY_MAIN",
  "portfolio_name": "High Yield Main",
  "desk": "HY",
  "total_nav_usd": 185234567.89,
  "daily_pnl_usd": -234567.12,
  "daily_pnl_bps": -12.6,
  "nav_change_pct": -0.126,
  "positions_count": 15,
  "avg_spread_bps": 342.5,
  "avg_duration": 4.8,
  "timestamp": "2025-01-15T14:30:00Z"
}
```

---

## Query Strategy

1. **All portfolios snapshot**: SOW query with no filter — 5 records, latest NAV per portfolio
2. **Specific portfolio**: Filter `/portfolio_id = 'HY_MAIN'` — single record
3. **P&L leaderboard**: Retrieve all, sort by `daily_pnl_bps` in-process
4. **Real-time stream**: Subscribe to `portfolio_nav` — receive updates every ~7 seconds
5. **Desk drill-down**: Filter by `/desk = 'HY'` then call `portfolio-agent` for position detail
