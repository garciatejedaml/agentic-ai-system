# AMPS Topic: positions

## Purpose

The `positions` topic stores the **current live positions** of each trader across all desks (HY, IG, EM, RATES). Each message represents the latest mark for a single trader–bond pair. Use this topic when you need real-time book data, intraday P&L, or to understand a trader's current exposure.

**When to use `positions` vs KDB:**
- Use `positions` (AMPS SOW) for live, intraday state — what traders hold *right now*
- Use `kdb-agent` for historical end-of-day snapshots and time-series analytics

**SOW tool to use:** `amps_sow_query(topic="positions", filter=...)`

---

## Key

```
/id
```

The key is a composite identifier: `{trader_id}_{isin}`. This ensures exactly one record per trader per bond in the State of World.

Example key value: `T_HY_001_US345370CY87`

---

## Fields

| Field | Type | Description | Example |
|---|---|---|---|
| `id` | string | SOW key: `{trader_id}_{isin}` | `"T_HY_001_US345370CY87"` |
| `trader_id` | string | Trader identifier (desk-prefixed) | `"T_HY_001"` |
| `trader_name` | string | Human-readable trader name | `"Sarah Mitchell"` |
| `desk` | string | Trading desk: HY, IG, EM, RATES | `"HY"` |
| `isin` | string | 12-character ISIN of the bond | `"US345370CY87"` |
| `bond_name` | string | Descriptive bond name | `"Ford Motor 8.5% 2028"` |
| `issuer` | string | Bond issuer name | `"Ford Motor"` |
| `side` | string | Long or short: `"buy"` or `"sell"` | `"buy"` |
| `quantity` | integer | Notional in USD | `15000000` |
| `avg_cost` | float | Average cost basis (price, % of par) | `98.4500` |
| `market_price` | float | Current mark-to-market price (% of par) | `98.7200` |
| `market_value` | float | Market value in USD (quantity × price / 100) | `14808000.00` |
| `pnl` | float | Unrealized P&L in USD | `42000.00` |
| `spread_bps` | float | Current OAS/spread in basis points | `342.5` |
| `timestamp` | string | ISO 8601 UTC timestamp of last update | `"2025-01-15T14:32:01Z"` |

---

## AMPS Filter Examples

```
# All positions for a specific trader
/trader_id = 'T_HY_001'

# All HY desk positions
/desk = 'HY'

# Positions with positive P&L
/pnl > 0

# Positions with spread wider than 300bps (high yield focus)
/spread_bps > 300

# Positions for a specific bond
/isin = 'US345370CY87'

# Large positions (notional > $10M)
/quantity > 10000000
```

---

## Example JSON Message

```json
{
  "id": "T_HY_001_US345370CY87",
  "trader_id": "T_HY_001",
  "trader_name": "Sarah Mitchell",
  "desk": "HY",
  "isin": "US345370CY87",
  "bond_name": "Ford Motor 8.5% 2028",
  "issuer": "Ford Motor",
  "side": "buy",
  "quantity": 15000000,
  "avg_cost": 98.45,
  "market_price": 98.72,
  "market_value": 14808000.00,
  "pnl": 40500.00,
  "spread_bps": 344.2,
  "timestamp": "2025-01-15T14:32:01Z"
}
```

---

## Query Strategy

1. **Point lookup** (single trader, single bond): SOW query with key filter `/id = 'T_HY_001_US345370CY87'`
2. **Desk-wide exposure**: SOW query with `/desk = 'HY'` — returns all positions on that desk
3. **Real-time stream**: Subscribe to `positions` with filter `/desk = 'HY'` for live updates
4. **Cross-desk aggregation**: SOW query with no filter — all records, aggregate in-process
