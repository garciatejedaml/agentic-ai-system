# AMPS Topic: risk_metrics

## Purpose

The `risk_metrics` topic stores **live VaR, DV01, and CS01 risk metrics** computed for each of the 5 fixed income portfolios. Each message represents the latest risk snapshot, recomputed whenever the pricing engine runs (approximately every 5–10 seconds).

Use this topic to monitor real-time portfolio risk exposure, track VaR limit utilization, and compare sensitivity profiles (DV01 = rate risk, CS01 = credit spread risk) across portfolios.

**Risk metrics computed:**
- **VaR 95%/99%**: Historical simulation Value at Risk (1-day, 95% and 99% confidence)
- **DV01**: Dollar value of a 1 basis point parallel shift in interest rates
- **CS01**: Dollar value of a 1 basis point parallel shift in credit spreads

**SOW tool to use:** `amps_sow_query(topic="risk_metrics", filter=...)`

---

## Key

```
/portfolio_id
```

One record per portfolio. Same key space as `portfolio_nav`.

Example key value: `HY_MAIN`

---

## Fields

| Field | Type | Description | Example |
|---|---|---|---|
| `portfolio_id` | string | Portfolio identifier (SOW key) | `"HY_MAIN"` |
| `var_95_usd` | float | VaR at 95% confidence in USD (negative = loss) | `-1823456.78` |
| `var_99_usd` | float | VaR at 99% confidence in USD (negative = loss) | `-2987654.32` |
| `var_95_pct` | float | VaR 95% as % of NAV | `-0.984` |
| `var_99_pct` | float | VaR 99% as % of NAV | `-1.612` |
| `dv01_usd` | float | DV01 in USD per 1bp rate move (negative = long duration) | `-18456.23` |
| `cs01_usd` | float | CS01 in USD per 1bp spread move (negative = long credit) | `-15234.56` |
| `total_nav_usd` | float | Portfolio NAV at time of computation | `185234567.89` |
| `avg_duration` | float | Weighted average modified duration used | `4.8` |
| `avg_spread_bps` | float | Weighted average OAS used | `342.5` |
| `computed_at` | string | ISO 8601 UTC timestamp of computation | `"2025-01-15T14:30:00Z"` |
| `timestamp` | string | ISO 8601 UTC message timestamp | `"2025-01-15T14:30:00Z"` |

---

## Metric Interpretation

| Metric | Sign | Meaning |
|---|---|---|
| `var_95_usd` | Always negative | Expected max 1-day loss at 95% confidence |
| `dv01_usd` | Negative = long rates | P&L impact of 1bp rate increase |
| `cs01_usd` | Negative = long credit | P&L impact of 1bp spread widening |
| `var_95_pct` | Always negative | VaR as % of NAV (e.g., -0.984 = -98bps) |

**Typical ranges by portfolio:**

| Portfolio | VaR 95% / NAV | DV01 (approx) | CS01 (approx) |
|---|---|---|---|
| HY_MAIN | -80 to -120 bps | -$15k to -$22k | -$12k to -$18k |
| IG_CORE | -40 to -70 bps | -$32k to -$45k | -$8k to -$15k |
| EM_BLEND | -90 to -130 bps | -$14k to -$20k | -$11k to -$17k |
| RATES_GOV | -35 to -60 bps | -$46k to -$58k | -$2k to -$5k |
| MULTI_STRAT | -60 to -100 bps | -$37k to -$52k | -$18k to -$28k |

---

## AMPS Filter Examples

```
# Specific portfolio risk
/portfolio_id = 'HY_MAIN'

# Portfolios with VaR exceeding $2M (95%)
/var_95_usd < -2000000

# Portfolios with large rate sensitivity (DV01 > $30k)
/dv01_usd < -30000

# Portfolios with large credit sensitivity (CS01 > $15k)
/cs01_usd < -15000

# High VaR as % of NAV (>100bps)
/var_95_pct < -1.0

# Long duration portfolios
/avg_duration > 7.0
```

---

## Example JSON Message

```json
{
  "portfolio_id": "HY_MAIN",
  "var_95_usd": -1823456.78,
  "var_99_usd": -2987654.32,
  "var_95_pct": -0.984,
  "var_99_pct": -1.612,
  "dv01_usd": -18456.23,
  "cs01_usd": -15234.56,
  "total_nav_usd": 185234567.89,
  "avg_duration": 4.8,
  "avg_spread_bps": 342.5,
  "computed_at": "2025-01-15T14:30:00Z",
  "timestamp": "2025-01-15T14:30:00Z"
}
```

---

## Query Strategy

1. **All portfolios risk**: SOW query with no filter — 5 records, full risk picture
2. **Risk limit check**: Filter `/var_95_usd < -2000000` — portfolios breaching VaR limits
3. **Rate sensitivity**: Sort all by `dv01_usd` to rank rate exposure
4. **Credit sensitivity**: Sort all by `cs01_usd` to rank credit spread exposure
5. **Real-time stream**: Subscribe to `risk_metrics` — recomputed every ~7 seconds
6. **Cross-topic join**: Combine with `portfolio_nav` (same key space) for P&L + risk together
