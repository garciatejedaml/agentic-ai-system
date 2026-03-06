# AMPS Topic: cds_spreads

## Purpose

The `cds_spreads` topic stores **live CDS (Credit Default Swap) spread ticks** for ~50 reference entities across HY, IG, and EM credit. Each message represents the latest spread quote for a single entity–tenor combination.

Use this topic to monitor real-time credit spread movements, detect widening/tightening trends, and screen entities by spread level, sector, or rating. The full term structure (1y, 3y, 5y, 7y, 10y) is available for each entity.

**SOW tool to use:** `amps_sow_query(topic="cds_spreads", filter=...)`

---

## Key

```
/entity_tenor_key
```

Composite key: `{entity_slug}_{tenor}y` — normalized entity name (spaces → underscores) + tenor.

Example key values:
- `Ford_Motor_Credit_5y`
- `JPMorgan_Chase_10y`
- `Brazil_3y`

---

## Fields

| Field | Type | Description | Example |
|---|---|---|---|
| `entity_tenor_key` | string | SOW key: `{entity_slug}_{tenor}y` | `"Ford_Motor_Credit_5y"` |
| `reference_entity` | string | Full entity name | `"Ford Motor Credit"` |
| `tenor_years` | integer | CDS tenor in years: 1, 3, 5, 7, 10 | `5` |
| `spread_bps` | float | Mid CDS spread in basis points | `287.5` |
| `spread_change_bps` | float | Change vs previous tick (signed) | `2.3` |
| `bid_bps` | float | Bid spread (lower = pay protection cheaper) | `285.0` |
| `ask_bps` | float | Ask spread (higher = receive protection) | `290.0` |
| `z_spread_bps` | float | Z-spread (spread over swap curve) | `292.1` |
| `sector` | string | Industry sector | `"Automotive"` |
| `rating` | string | Credit rating | `"BB+"` |
| `timestamp` | string | ISO 8601 UTC timestamp | `"2025-01-15T14:33:10Z"` |

---

## Sector Reference

| Sector | Typical Rating | Typical 5y Spread |
|---|---|---|
| Technology (Apple, Microsoft) | AA–AAA | 18–35 bps |
| Healthcare (J&J, Pfizer) | A+–AAA | 19–35 bps |
| Financials (JPM, GS) | A-–BBB+ | 52–75 bps |
| Energy–IG (ExxonMobil) | AA–A | 38–50 bps |
| Automotive–HY (Ford, GM) | BB–BB+ | 260–320 bps |
| Airlines (United, Delta) | B+–BB- | 280–500 bps |
| Gaming (MGM, Caesars) | B+–BB- | 290–370 bps |
| Sovereign–EM (Brazil, Mexico) | BB-–BBB | 100–200 bps |
| Distressed (Spirit, Argentina) | CCC–B | 900–1450 bps |

---

## AMPS Filter Examples

```
# All 5y spreads (full cross-section)
/tenor_years = 5

# HY universe (spread > 200bps)
/spread_bps > 200 AND /tenor_years = 5

# Specific entity full curve
/reference_entity = 'Ford Motor Credit'

# IG names only (tight spreads)
/spread_bps < 100 AND /tenor_years = 5

# Spreads widening today (positive change)
/spread_change_bps > 5

# EM sovereigns
/sector = 'Sovereign'

# Distressed (spread > 800bps)
/spread_bps > 800

# Specific sector + tenor
/sector = 'Airlines' AND /tenor_years = 5

# Investment grade ratings only
/rating = 'A+' OR /rating = 'AA' OR /rating = 'AA-' OR /rating = 'AA+'
```

---

## Example JSON Message

```json
{
  "entity_tenor_key": "Ford_Motor_Credit_5y",
  "reference_entity": "Ford Motor Credit",
  "tenor_years": 5,
  "spread_bps": 287.5,
  "spread_change_bps": 2.3,
  "bid_bps": 285.0,
  "ask_bps": 290.0,
  "z_spread_bps": 292.1,
  "sector": "Automotive",
  "rating": "BB+",
  "timestamp": "2025-01-15T14:33:10Z"
}
```

---

## Query Strategy

1. **Single entity term structure**: SOW query with `/reference_entity = 'Ford Motor Credit'` — 5 records (one per tenor)
2. **Cross-section at specific tenor**: Filter `/tenor_years = 5` — all ~50 entities at 5y
3. **Sector screener**: Filter by `/sector = 'Airlines'` to compare intra-sector spreads
4. **Wide-spread screen**: Filter `/spread_bps > 300 AND /tenor_years = 5` for high-beta names
5. **Real-time monitoring**: Subscribe to `cds_spreads` to capture spread widening events
6. **Key lookup**: Direct SOW key lookup with `entity_tenor_key` for known entity+tenor combos
