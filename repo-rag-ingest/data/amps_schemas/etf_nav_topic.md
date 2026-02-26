# AMPS Topic: etf_nav

## Purpose

The `etf_nav` topic stores **live NAV, market price, premium/discount, and intraday flow data** for 15 fixed income ETFs. Each message represents the latest computed metrics for a single ETF, updated every few seconds.

Use this topic to monitor real-time ETF pricing efficiency (premium/discount to NAV), track intraday creation/redemption flows, and understand which asset classes are experiencing net inflows or outflows.

**ETFs covered:** HYG, JNK, LQD, EMB, TLT, AGG, BKLN, ANGL, FALN, HYDB, VCSH, VCIT, SHY, IEF, IGIB

**SOW tool to use:** `amps_sow_query(topic="etf_nav", filter=...)`

---

## Key

```
/ticker
```

The ETF ticker symbol. One record per ETF in the SOW.

Example key values: `HYG`, `LQD`, `TLT`

---

## Fields

| Field | Type | Description | Example |
|---|---|---|---|
| `ticker` | string | ETF ticker (SOW key) | `"HYG"` |
| `name` | string | Full ETF name | `"iShares iBoxx HY Corporate Bond ETF"` |
| `nav` | float | Net Asset Value per share (USD) | `76.52` |
| `market_price` | float | Last traded market price (USD) | `76.48` |
| `premium_discount_bps` | float | Premium(+)/discount(-) to NAV in bps | `-5.2` |
| `aum_usd` | integer | Assets under management in USD | `14200000000` |
| `intraday_flow_usd` | integer | Net creation/redemption flow today in USD (positive = inflow) | `-23450000` |
| `volume_shares` | integer | Intraday share volume | `4521000` |
| `asset_class` | string | Broad asset class category | `"HighYield"` |
| `timestamp` | string | ISO 8601 UTC timestamp | `"2025-01-15T14:34:05Z"` |

---

## ETF Reference

| Ticker | Name | Asset Class | Approx AUM |
|---|---|---|---|
| HYG | iShares iBoxx HY Corporate Bond | HighYield | $14.2B |
| JNK | SPDR Bloomberg HY Bond | HighYield | $8.1B |
| LQD | iShares iBoxx IG Corporate Bond | InvestmentGrade | $32.4B |
| EMB | iShares JPM USD EM Bond | EmergingMarkets | $15.7B |
| TLT | iShares 20+ Year Treasury Bond | Rates | $43.2B |
| AGG | iShares Core US Aggregate Bond | Aggregate | $89.1B |
| BKLN | Invesco Senior Loan | HighYield | $3.8B |
| ANGL | VanEck Fallen Angel HY Bond | HighYield | $2.1B |
| FALN | iShares Fallen Angels USD Bond | HighYield | $1.4B |
| HYDB | iShares HY Systematic Bond | HighYield | $0.8B |
| VCSH | Vanguard Short-Term Corporate Bond | InvestmentGrade | $18.3B |
| VCIT | Vanguard Intermediate-Term Corp Bond | InvestmentGrade | $24.5B |
| SHY | iShares 1-3 Year Treasury Bond | Rates | $23.1B |
| IEF | iShares 7-10 Year Treasury Bond | Rates | $28.7B |
| IGIB | iShares Intermediate-Term Corp Bond | InvestmentGrade | $12.4B |

---

## AMPS Filter Examples

```
# Specific ETF lookup
/ticker = 'HYG'

# All high yield ETFs
/asset_class = 'HighYield'

# All rates/treasury ETFs
/asset_class = 'Rates'

# ETFs trading at a discount (market price < NAV)
/premium_discount_bps < 0

# ETFs with significant discount (> 15bps cheap to NAV)
/premium_discount_bps < -15

# ETFs with net inflows today
/intraday_flow_usd > 0

# Large ETFs only (AUM > $10B)
/aum_usd > 10000000000

# High volume ETFs
/volume_shares > 2000000
```

---

## Example JSON Message

```json
{
  "ticker": "HYG",
  "name": "iShares iBoxx HY Corporate Bond ETF",
  "nav": 76.52,
  "market_price": 76.48,
  "premium_discount_bps": -5.2,
  "aum_usd": 14200000000,
  "intraday_flow_usd": -23450000,
  "volume_shares": 4521000,
  "asset_class": "HighYield",
  "timestamp": "2025-01-15T14:34:05Z"
}
```

---

## Query Strategy

1. **All ETFs snapshot**: SOW query with no filter — 15 records, full ETF universe
2. **Specific ETF**: Direct key lookup by `ticker`
3. **Asset class view**: Filter by `/asset_class = 'HighYield'` for HY ETF comparison
4. **Pricing efficiency**: Filter `/premium_discount_bps < -10` to find ETFs trading cheap to NAV
5. **Flow analysis**: Sort all ETFs by `intraday_flow_usd` — identifies risk-on/risk-off signal
6. **Real-time stream**: Subscribe to `etf_nav` — 15 ETFs updated every ~7 seconds
