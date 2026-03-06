# AMPS Topic: market-data

## Purpose

The `market-data` topic stores **live bid/ask/mid prices and spreads** for each bond in the universe. Each message represents the latest price tick for a single bond. This is the primary source for real-time bond pricing — updated continuously as dealers quote new levels.

**When to use `market-data` vs KDB:**
- Use `market-data` (AMPS SOW) for current intraday prices, live spread levels
- Use `kdb-agent` for end-of-day close prices, historical price series, or VWAP

**SOW tool to use:** `amps_sow_query(topic="market-data", filter=...)`

---

## Key

```
/symbol
```

The key is the ISIN of the bond. Each bond has exactly one record in the SOW (the latest price tick).

Example key value: `US345370CY87`

---

## Fields

| Field | Type | Description | Example |
|---|---|---|---|
| `symbol` | string | ISIN (SOW key) | `"US345370CY87"` |
| `isin` | string | Same as symbol — bond ISIN | `"US345370CY87"` |
| `bond_name` | string | Bond description | `"Ford Motor 8.5% 2028"` |
| `issuer` | string | Issuer name | `"Ford Motor"` |
| `desk` | string | Primary trading desk for this bond | `"HY"` |
| `coupon` | float | Annual coupon rate (%) | `8.5` |
| `bid` | float | Best bid price (% of par) | `98.10` |
| `ask` | float | Best ask price (% of par) | `98.90` |
| `mid` | float | Mid-market price (% of par) | `98.50` |
| `spread_bps` | float | OAS / G-spread in basis points | `344.2` |
| `yield_pct` | float | Current yield to maturity (%) | `8.78` |
| `benchmark` | string | Treasury benchmark used for spread | `"UST5Y"` |
| `volume_usd` | integer | Estimated intraday volume in USD | `45000000` |
| `timestamp` | string | ISO 8601 UTC timestamp of price tick | `"2025-01-15T14:35:22Z"` |

---

## AMPS Filter Examples

```
# All HY desk bonds
/desk = 'HY'

# Bonds with spread wider than 300bps
/spread_bps > 300

# Bonds trading below par (distressed)
/mid < 95

# Bonds with tight bid-ask spread (liquid names)
/ask - /bid < 0.5

# Specific bond lookup
/symbol = 'US345370CY87'

# High coupon bonds
/coupon > 7.0

# IG bonds (spread < 150bps typically)
/spread_bps < 150
```

---

## Example JSON Message

```json
{
  "symbol": "US345370CY87",
  "isin": "US345370CY87",
  "bond_name": "Ford Motor 8.5% 2028",
  "issuer": "Ford Motor",
  "desk": "HY",
  "coupon": 8.5,
  "bid": 98.10,
  "ask": 98.90,
  "mid": 98.50,
  "spread_bps": 344.2,
  "yield_pct": 8.78,
  "benchmark": "UST5Y",
  "volume_usd": 45000000,
  "timestamp": "2025-01-15T14:35:22Z"
}
```

---

## Query Strategy

1. **Universe snapshot**: SOW query with no filter — full bond universe, latest prices
2. **Desk prices**: Filter by `/desk = 'HY'` for all HY bond prices
3. **Wide spread screener**: Filter by `/spread_bps > 300` to find potential value/risk
4. **Real-time stream**: Subscribe to `market-data` for live price feed (high frequency)
5. **Spread-duration**: Retrieve all, compute spread × duration product for risk sorting
