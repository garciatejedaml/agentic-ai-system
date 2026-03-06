# AMPS Topic: orders

## Purpose

The `orders` topic stores **live and recent RFQ (Request-for-Quote) orders** submitted by traders across all desks. Each message represents the latest state of a single order. Use this topic to monitor order flow, analyze execution quality, and track fill rates in real time.

**When to use `orders` vs KDB:**
- Use `orders` (AMPS SOW) for orders submitted today — live status, pending fills
- Use `kdb-agent` for historical order analysis, P&L attribution over days/weeks

**SOW tool to use:** `amps_sow_query(topic="orders", filter=...)`

---

## Key

```
/order_id
```

Each order has a unique identifier generated at submission time: `ORD-{timestamp_ms}-{sequence}`.

Example key value: `ORD-1705329121000-007`

---

## Fields

| Field | Type | Description | Example |
|---|---|---|---|
| `order_id` | string | Unique order identifier | `"ORD-1705329121000-007"` |
| `trader_id` | string | Trader who submitted the order | `"T_HY_002"` |
| `trader_name` | string | Human-readable trader name | `"James Thornton"` |
| `desk` | string | Trading desk: HY, IG, EM, RATES | `"HY"` |
| `isin` | string | Bond ISIN | `"US92336GAN41"` |
| `bond_name` | string | Bond description | `"Verizon 7.0% 2027"` |
| `issuer` | string | Bond issuer | `"Verizon"` |
| `side` | string | Direction: `"buy"` or `"sell"` | `"buy"` |
| `notional_usd` | integer | Order size in USD notional | `5000000` |
| `price` | float | Executed or quoted price (% of par) | `99.1500` |
| `spread_bps` | float | Spread at execution in basis points | `281.3` |
| `status` | string | Order status: `pending`, `filled`, `cancelled` | `"filled"` |
| `venue` | string | Execution venue | `"Bloomberg"` |
| `response_ms` | integer | Dealer response time in milliseconds | `1250` |
| `timestamp` | string | ISO 8601 UTC timestamp of order | `"2025-01-15T14:28:45Z"` |

**Possible venues:** Bloomberg, TradeWeb, MarketAxess, Voice, D2C

---

## AMPS Filter Examples

```
# All pending orders (unfilled)
/status = 'pending'

# All orders for a specific desk
/desk = 'HY'

# Large filled orders (>$10M)
/notional_usd > 10000000 AND /status = 'filled'

# Slow dealer responses (>2 seconds)
/response_ms > 2000

# Orders on a specific bond
/isin = 'US92336GAN41'

# Sell-side orders only
/side = 'sell'

# Orders via specific venue
/venue = 'TradeWeb'
```

---

## Example JSON Message

```json
{
  "order_id": "ORD-1705329121000-007",
  "trader_id": "T_HY_002",
  "trader_name": "James Thornton",
  "desk": "HY",
  "isin": "US92336GAN41",
  "bond_name": "Verizon 7.0% 2027",
  "issuer": "Verizon",
  "side": "buy",
  "notional_usd": 5000000,
  "price": 99.15,
  "spread_bps": 281.3,
  "status": "filled",
  "venue": "Bloomberg",
  "response_ms": 1250,
  "timestamp": "2025-01-15T14:28:45Z"
}
```

---

## Query Strategy

1. **Active order book**: SOW query with `/status = 'pending'` — all unfilled orders
2. **Desk activity**: SOW query with `/desk = 'HY'` — today's orders by desk
3. **Execution quality**: Query all, filter by `response_ms` and `venue` to analyze dealer performance
4. **Real-time monitoring**: Subscribe to `orders` — receive new orders and status updates as they happen
