#!/usr/bin/env python3
"""
AMPS Product Publisher Simulator (Phase 3)

Publishes to 4 independent AMPS instances — one per product:
  amps-portfolio  → portfolio_nav    (key: /portfolio_id)      host: AMPS_PORTFOLIO_HOST:AMPS_PORTFOLIO_PORT
  amps-cds        → cds_spreads      (key: /entity_tenor_key)  host: AMPS_CDS_HOST:AMPS_CDS_PORT
  amps-etf        → etf_nav          (key: /ticker)             host: AMPS_ETF_HOST:AMPS_ETF_PORT
  amps-risk       → risk_metrics     (key: /portfolio_id)       host: AMPS_RISK_HOST:AMPS_RISK_PORT

Each product has its own AMPS process and config.xml.  Connections are
independent — if one AMPS instance is down, the others keep publishing.

Reference data is consistent with portfolio_mcp_server.py, cds_mcp_server.py,
and etf_mcp_server.py so agents can correlate SOW (live) vs MCP (static) data.

Usage:
  python scripts/product_publishers.py                      # seed + continuous ticks
  python scripts/product_publishers.py --mode seed          # initial load only
  python scripts/product_publishers.py --mode tick          # updates only (no seed)
  python scripts/product_publishers.py --interval 7         # base seconds (default: 7, ±30% jitter)

Environment variables (Docker internal defaults — port 9007 on each container):
  AMPS_PORTFOLIO_HOST / AMPS_PORTFOLIO_PORT  (default: amps-portfolio / 9007)
  AMPS_CDS_HOST       / AMPS_CDS_PORT        (default: amps-cds       / 9007)
  AMPS_ETF_HOST       / AMPS_ETF_PORT        (default: amps-etf       / 9007)
  AMPS_RISK_HOST      / AMPS_RISK_PORT       (default: amps-risk      / 9007)
  MODE                                        (default: both)
  TICK_INTERVAL                               (default: 7)

For local testing (host ports from docker-compose.amps.yml):
  AMPS_PORTFOLIO_HOST=localhost AMPS_PORTFOLIO_PORT=9008
  AMPS_CDS_HOST=localhost       AMPS_CDS_PORT=9009
  AMPS_ETF_HOST=localhost       AMPS_ETF_PORT=9010
  AMPS_RISK_HOST=localhost      AMPS_RISK_PORT=9011
"""
import argparse
import json
import os
import random
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

random.seed(42)  # reproducible base values — jitter applied at runtime

# ── AMPS instance configuration ────────────────────────────────────────────────

_AMPS_INSTANCES = {
    "portfolio_nav": {
        "host": os.getenv("AMPS_PORTFOLIO_HOST", "amps-portfolio"),
        "port": int(os.getenv("AMPS_PORTFOLIO_PORT", "9007")),
        "topic": "portfolio_nav",
    },
    "cds_spreads": {
        "host": os.getenv("AMPS_CDS_HOST", "amps-cds"),
        "port": int(os.getenv("AMPS_CDS_PORT", "9007")),
        "topic": "cds_spreads",
    },
    "etf_nav": {
        "host": os.getenv("AMPS_ETF_HOST", "amps-etf"),
        "port": int(os.getenv("AMPS_ETF_PORT", "9007")),
        "topic": "etf_nav",
    },
    "risk_metrics": {
        "host": os.getenv("AMPS_RISK_HOST", "amps-risk"),
        "port": int(os.getenv("AMPS_RISK_PORT", "9007")),
        "topic": "risk_metrics",
    },
}

# ── Reference data ─────────────────────────────────────────────────────────────

_PORTFOLIOS = [
    {"portfolio_id": "HY_MAIN",     "portfolio_name": "High Yield Main",           "desk": "HY",    "base_nav": 185_234_567.89, "base_spread": 342.5, "base_duration": 4.8, "positions_count": 15},
    {"portfolio_id": "IG_CORE",     "portfolio_name": "Investment Grade Core",      "desk": "IG",    "base_nav": 312_456_789.01, "base_spread":  95.2, "base_duration": 6.4, "positions_count": 12},
    {"portfolio_id": "EM_BLEND",    "portfolio_name": "Emerging Markets Blend",     "desk": "EM",    "base_nav": 145_678_901.23, "base_spread": 218.7, "base_duration": 5.9, "positions_count": 18},
    {"portfolio_id": "RATES_GOV",   "portfolio_name": "Rates Government",           "desk": "RATES", "base_nav": 278_345_678.90, "base_spread":  12.3, "base_duration": 8.2, "positions_count":  8},
    {"portfolio_id": "MULTI_STRAT", "portfolio_name": "Multi Strategy",             "desk": "MULTI", "base_nav": 423_123_456.78, "base_spread": 187.4, "base_duration": 5.5, "positions_count": 25},
]

_CDS_ENTITIES = [
    {"entity": "Ford Motor Credit",       "sector": "Automotive",   "rating": "BB+",  "base_5y": 287.5},
    {"entity": "General Motors",          "sector": "Automotive",   "rating": "BB+",  "base_5y": 265.0},
    {"entity": "Stellantis",              "sector": "Automotive",   "rating": "BB",   "base_5y": 312.0},
    {"entity": "Netflix",                 "sector": "Media",        "rating": "BB+",  "base_5y": 198.5},
    {"entity": "Charter Communications",  "sector": "Telecom",      "rating": "BB",   "base_5y": 278.3},
    {"entity": "Dish Network",            "sector": "Telecom",      "rating": "B+",   "base_5y": 625.0},
    {"entity": "Altice USA",              "sector": "Telecom",      "rating": "B",    "base_5y": 798.0},
    {"entity": "United Airlines",         "sector": "Airlines",     "rating": "B+",   "base_5y": 345.0},
    {"entity": "Delta Air Lines",         "sector": "Airlines",     "rating": "BB-",  "base_5y": 302.5},
    {"entity": "American Airlines",       "sector": "Airlines",     "rating": "B",    "base_5y": 498.0},
    {"entity": "Spirit Airlines",         "sector": "Airlines",     "rating": "CCC",  "base_5y": 1250.0},
    {"entity": "MGM Resorts",             "sector": "Gaming",       "rating": "BB-",  "base_5y": 298.0},
    {"entity": "Caesars Entertainment",   "sector": "Gaming",       "rating": "B+",   "base_5y": 367.5},
    {"entity": "Wynn Resorts",            "sector": "Gaming",       "rating": "B+",   "base_5y": 378.0},
    {"entity": "Carnival Corp",           "sector": "Leisure",      "rating": "B+",   "base_5y": 320.0},
    {"entity": "Transocean",              "sector": "Energy",       "rating": "CCC+", "base_5y": 876.0},
    {"entity": "Occidental Petroleum",    "sector": "Energy",       "rating": "BB+",  "base_5y": 187.5},
    {"entity": "Callon Petroleum",        "sector": "Energy",       "rating": "B",    "base_5y": 412.0},
    {"entity": "JPMorgan Chase",          "sector": "Financials",   "rating": "A-",   "base_5y":  52.5},
    {"entity": "Bank of America",         "sector": "Financials",   "rating": "A-",   "base_5y":  58.0},
    {"entity": "Goldman Sachs",           "sector": "Financials",   "rating": "BBB+", "base_5y":  68.0},
    {"entity": "Wells Fargo",             "sector": "Financials",   "rating": "A-",   "base_5y":  61.5},
    {"entity": "Citigroup",               "sector": "Financials",   "rating": "BBB+", "base_5y":  72.0},
    {"entity": "Morgan Stanley",          "sector": "Financials",   "rating": "A-",   "base_5y":  56.5},
    {"entity": "Apple",                   "sector": "Technology",   "rating": "AA+",  "base_5y":  22.5},
    {"entity": "Microsoft",               "sector": "Technology",   "rating": "AAA",  "base_5y":  18.0},
    {"entity": "Amazon",                  "sector": "Technology",   "rating": "AA",   "base_5y":  28.5},
    {"entity": "Alphabet",                "sector": "Technology",   "rating": "AA+",  "base_5y":  21.0},
    {"entity": "Meta Platforms",          "sector": "Technology",   "rating": "A+",   "base_5y":  35.5},
    {"entity": "Johnson & Johnson",       "sector": "Healthcare",   "rating": "AAA",  "base_5y":  19.5},
    {"entity": "Pfizer",                  "sector": "Healthcare",   "rating": "A+",   "base_5y":  32.0},
    {"entity": "Merck & Co",              "sector": "Healthcare",   "rating": "A+",   "base_5y":  29.5},
    {"entity": "ExxonMobil",              "sector": "Energy",       "rating": "AA-",  "base_5y":  42.0},
    {"entity": "Chevron",                 "sector": "Energy",       "rating": "AA",   "base_5y":  38.5},
    {"entity": "NextEra Energy",          "sector": "Utilities",    "rating": "A-",   "base_5y":  48.0},
    {"entity": "Duke Energy",             "sector": "Utilities",    "rating": "BBB+", "base_5y":  62.0},
    {"entity": "Brazil",                  "sector": "Sovereign",    "rating": "BB-",  "base_5y": 198.5},
    {"entity": "Mexico",                  "sector": "Sovereign",    "rating": "BBB",  "base_5y": 142.0},
    {"entity": "Colombia",                "sector": "Sovereign",    "rating": "BB+",  "base_5y": 187.5},
    {"entity": "Peru",                    "sector": "Sovereign",    "rating": "BBB",  "base_5y": 112.0},
    {"entity": "Chile",                   "sector": "Sovereign",    "rating": "A-",   "base_5y":  78.5},
    {"entity": "Indonesia",               "sector": "Sovereign",    "rating": "BBB",  "base_5y":  98.0},
    {"entity": "Philippines",             "sector": "Sovereign",    "rating": "BBB+", "base_5y":  82.5},
    {"entity": "Turkey",                  "sector": "Sovereign",    "rating": "B+",   "base_5y": 387.5},
    {"entity": "South Africa",            "sector": "Sovereign",    "rating": "BB-",  "base_5y": 245.0},
    {"entity": "Argentina",               "sector": "Sovereign",    "rating": "CCC",  "base_5y": 1450.0},
    {"entity": "Dominican Republic",      "sector": "Sovereign",    "rating": "BB-",  "base_5y": 312.0},
    {"entity": "Jamaica",                 "sector": "Sovereign",    "rating": "BB",   "base_5y": 278.0},
    {"entity": "Petrobras",               "sector": "Energy",       "rating": "BB-",  "base_5y": 225.0},
    {"entity": "PEMEX",                   "sector": "Energy",       "rating": "BB-",  "base_5y": 348.5},
]

_CDS_TENORS   = [1, 3, 5, 7, 10]
_TENOR_MULT   = {1: 0.45, 3: 0.75, 5: 1.00, 7: 1.15, 10: 1.30}

_ETFS = [
    {"ticker": "HYG",  "name": "iShares iBoxx HY Corporate Bond ETF",         "asset_class": "HighYield",       "base_nav":  76.52, "base_aum": 14_200_000_000},
    {"ticker": "JNK",  "name": "SPDR Bloomberg HY Bond ETF",                  "asset_class": "HighYield",       "base_nav":  93.45, "base_aum":  8_100_000_000},
    {"ticker": "LQD",  "name": "iShares iBoxx IG Corporate Bond ETF",         "asset_class": "InvestmentGrade", "base_nav": 108.23, "base_aum": 32_400_000_000},
    {"ticker": "EMB",  "name": "iShares JPM USD EM Bond ETF",                 "asset_class": "EmergingMarkets", "base_nav":  87.65, "base_aum": 15_700_000_000},
    {"ticker": "TLT",  "name": "iShares 20+ Year Treasury Bond ETF",          "asset_class": "Rates",           "base_nav":  94.32, "base_aum": 43_200_000_000},
    {"ticker": "AGG",  "name": "iShares Core US Aggregate Bond ETF",          "asset_class": "Aggregate",       "base_nav":  96.78, "base_aum": 89_100_000_000},
    {"ticker": "BKLN", "name": "Invesco Senior Loan ETF",                     "asset_class": "HighYield",       "base_nav":  21.43, "base_aum":  3_800_000_000},
    {"ticker": "ANGL", "name": "VanEck Fallen Angel HY Bond ETF",             "asset_class": "HighYield",       "base_nav":  28.67, "base_aum":  2_100_000_000},
    {"ticker": "FALN", "name": "iShares Fallen Angels USD Bond ETF",          "asset_class": "HighYield",       "base_nav":  25.34, "base_aum":  1_400_000_000},
    {"ticker": "HYDB", "name": "iShares HY Systematic Bond ETF",              "asset_class": "HighYield",       "base_nav":  42.87, "base_aum":    800_000_000},
    {"ticker": "VCSH", "name": "Vanguard Short-Term Corporate Bond ETF",      "asset_class": "InvestmentGrade", "base_nav":  76.54, "base_aum": 18_300_000_000},
    {"ticker": "VCIT", "name": "Vanguard Intermediate-Term Corp Bond ETF",    "asset_class": "InvestmentGrade", "base_nav":  83.21, "base_aum": 24_500_000_000},
    {"ticker": "SHY",  "name": "iShares 1-3 Year Treasury Bond ETF",          "asset_class": "Rates",           "base_nav":  82.45, "base_aum": 23_100_000_000},
    {"ticker": "IEF",  "name": "iShares 7-10 Year Treasury Bond ETF",         "asset_class": "Rates",           "base_nav":  96.32, "base_aum": 28_700_000_000},
    {"ticker": "IGIB", "name": "iShares Intermediate-Term Corp Bond ETF",     "asset_class": "InvestmentGrade", "base_nav":  52.43, "base_aum": 12_400_000_000},
]

_running = True


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def _jitter(base: float, pct: float = 0.02) -> float:
    return round(base * (1 + random.uniform(-pct, pct)), 4)

def _entity_key(entity_name: str, tenor: int) -> str:
    slug = entity_name.replace(" ", "_").replace("&", "and").replace("/", "_")
    return f"{slug}_{tenor}y"


# ── Record generators ──────────────────────────────────────────────────────────

def _make_portfolio_nav_record(p: dict) -> dict:
    nav      = _jitter(p["base_nav"], 0.02)
    prev_nav = _jitter(p["base_nav"], 0.015)
    pnl_usd  = round(nav - prev_nav, 2)
    pnl_bps  = round(pnl_usd / prev_nav * 10_000, 1) if prev_nav else 0.0
    return {
        "portfolio_id":   p["portfolio_id"],
        "portfolio_name": p["portfolio_name"],
        "desk":           p["desk"],
        "total_nav_usd":  round(nav, 2),
        "daily_pnl_usd":  pnl_usd,
        "daily_pnl_bps":  pnl_bps,
        "nav_change_pct": round(pnl_bps / 100, 3),
        "positions_count":p["positions_count"],
        "avg_spread_bps": round(_jitter(p["base_spread"],   0.03), 1),
        "avg_duration":   round(_jitter(p["base_duration"], 0.01), 2),
        "timestamp":      _now(),
    }

def _make_cds_spread_record(entity: dict, tenor: int) -> dict:
    mult      = _TENOR_MULT[tenor]
    base_sprd = entity["base_5y"] * mult
    spread    = _jitter(base_sprd, 0.03)
    half_tick = round(spread * random.uniform(0.005, 0.015), 1)
    z_spread  = round(spread + random.uniform(1.5, 8.5), 1)
    prev_sprd = _jitter(base_sprd, 0.025)
    return {
        "entity_tenor_key":  _entity_key(entity["entity"], tenor),
        "reference_entity":  entity["entity"],
        "tenor_years":       tenor,
        "spread_bps":        round(spread, 1),
        "spread_change_bps": round(spread - prev_sprd, 2),
        "bid_bps":           round(spread - half_tick, 1),
        "ask_bps":           round(spread + half_tick, 1),
        "z_spread_bps":      z_spread,
        "sector":            entity["sector"],
        "rating":            entity["rating"],
        "timestamp":         _now(),
    }

def _make_etf_nav_record(etf: dict) -> dict:
    nav            = _jitter(etf["base_nav"], 0.005)
    price_dev      = random.uniform(-0.0015, 0.0015)
    market_price   = round(nav * (1 + price_dev), 4)
    aum            = round(_jitter(etf["base_aum"], 0.01))
    shares         = int(aum / nav)
    flow_usd       = round(random.uniform(-0.03, 0.03) * etf["base_aum"])
    volume         = int(random.uniform(0.003, 0.015) * shares)
    return {
        "ticker":               etf["ticker"],
        "name":                 etf["name"],
        "nav":                  round(nav, 4),
        "market_price":         market_price,
        "premium_discount_bps": round(price_dev * 10_000, 1),
        "aum_usd":              aum,
        "intraday_flow_usd":    flow_usd,
        "volume_shares":        volume,
        "asset_class":          etf["asset_class"],
        "timestamp":            _now(),
    }

def _make_risk_metrics_record(p: dict) -> dict:
    nav      = _jitter(p["base_nav"],      0.02)
    duration = _jitter(p["base_duration"], 0.01)
    spread   = _jitter(p["base_spread"],   0.03)
    sigma    = 0.004 if spread > 150 else 0.002
    var95p   = round(-1.645 * sigma * 100, 3)
    var99p   = round(-2.326 * sigma * 100, 3)
    now      = _now()
    return {
        "portfolio_id":   p["portfolio_id"],
        "var_95_usd":     round(var95p / 100 * nav, 2),
        "var_99_usd":     round(var99p / 100 * nav, 2),
        "var_95_pct":     var95p,
        "var_99_pct":     var99p,
        "dv01_usd":       round(-nav * duration * 0.0001, 2),
        "cs01_usd":       round(-nav * duration * 0.85 * 0.0001, 2),
        "total_nav_usd":  round(nav, 2),
        "avg_duration":   round(duration, 2),
        "avg_spread_bps": round(spread, 1),
        "computed_at":    now,
        "timestamp":      now,
    }


# ── AMPS connection helpers ────────────────────────────────────────────────────

def _connect_one(instance_key: str, host: str, port: int):
    """Connect to a single AMPS instance. Returns client or None on failure."""
    from AMPS import Client
    try:
        client = Client(f"product-publisher-{instance_key}")
        client.connect(f"tcp://{host}:{port}/amps/json")
        client.logon()
        print(f"  [connect] {instance_key:<15} → {host}:{port}  OK")
        return client
    except Exception as e:
        print(f"  [connect] {instance_key:<15} → {host}:{port}  FAILED: {e}")
        return None

def _reconnect(clients: dict, instance_key: str) -> bool:
    """Try to reconnect a specific AMPS instance. Returns True if successful."""
    cfg = _AMPS_INSTANCES[instance_key]
    client = _connect_one(instance_key, cfg["host"], cfg["port"])
    if client:
        clients[instance_key] = client
        return True
    return False

def _publish(clients: dict, instance_key: str, topic: str, record: dict) -> bool:
    """Publish one record to the appropriate AMPS instance. Returns False on error."""
    client = clients.get(instance_key)
    if client is None:
        return False
    try:
        client.publish(topic, json.dumps(record))
        return True
    except Exception:
        return False


# ── Seed ──────────────────────────────────────────────────────────────────────

def seed(clients: dict, verbose: bool = True) -> dict:
    """Publish full initial snapshot to all 4 AMPS instances."""
    counts = {"portfolio_nav": 0, "cds_spreads": 0, "etf_nav": 0, "risk_metrics": 0}

    for p in _PORTFOLIOS:
        if _publish(clients, "portfolio_nav", "portfolio_nav", _make_portfolio_nav_record(p)):
            counts["portfolio_nav"] += 1

    for entity in _CDS_ENTITIES:
        for tenor in _CDS_TENORS:
            if _publish(clients, "cds_spreads", "cds_spreads", _make_cds_spread_record(entity, tenor)):
                counts["cds_spreads"] += 1

    for etf in _ETFS:
        if _publish(clients, "etf_nav", "etf_nav", _make_etf_nav_record(etf)):
            counts["etf_nav"] += 1

    for p in _PORTFOLIOS:
        if _publish(clients, "risk_metrics", "risk_metrics", _make_risk_metrics_record(p)):
            counts["risk_metrics"] += 1

    if verbose:
        total = sum(counts.values())
        print(f"  [seed] amps-portfolio → portfolio_nav:  {counts['portfolio_nav']:>4} records")
        print(f"  [seed] amps-cds       → cds_spreads:    {counts['cds_spreads']:>4} records")
        print(f"  [seed] amps-etf       → etf_nav:        {counts['etf_nav']:>4} records")
        print(f"  [seed] amps-risk      → risk_metrics:   {counts['risk_metrics']:>4} records")
        print(f"  [seed] total:                            {total:>4} records")
    return counts


# ── Tick ──────────────────────────────────────────────────────────────────────

def tick(clients: dict, tick_num: int) -> None:
    """Publish a random batch of updates across all 4 AMPS instances."""
    updates = []

    for p in random.sample(_PORTFOLIOS, random.randint(2, 3)):
        if _publish(clients, "portfolio_nav", "portfolio_nav", _make_portfolio_nav_record(p)):
            updates.append(f"portfolio/{p['portfolio_id']}")

    for entity in random.sample(_CDS_ENTITIES, random.randint(5, 10)):
        for tenor in random.sample(_CDS_TENORS, random.randint(2, 4)):
            if _publish(clients, "cds_spreads", "cds_spreads", _make_cds_spread_record(entity, tenor)):
                updates.append(f"cds/{_entity_key(entity['entity'], tenor)}")

    for etf in random.sample(_ETFS, random.randint(3, 6)):
        if _publish(clients, "etf_nav", "etf_nav", _make_etf_nav_record(etf)):
            updates.append(f"etf/{etf['ticker']}")

    for p in random.sample(_PORTFOLIOS, random.randint(1, 2)):
        if _publish(clients, "risk_metrics", "risk_metrics", _make_risk_metrics_record(p)):
            updates.append(f"risk/{p['portfolio_id']}")

    ts_str  = datetime.now().strftime("%H:%M:%S")
    preview = ", ".join(updates[:6])
    suffix  = f"... (+{len(updates)-6} more)" if len(updates) > 6 else ""
    print(f"  [tick #{tick_num:04d} @ {ts_str}] {len(updates)} updates: {preview}{suffix}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AMPS product publisher — publishes to 4 independent AMPS instances"
    )
    parser.add_argument(
        "--mode",
        choices=["seed", "tick", "both"],
        default=os.getenv("MODE", "both"),
        help="seed=initial load only | tick=updates only | both=seed then continuous ticks",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("TICK_INTERVAL", "7")),
        help="Base seconds between ticks — actual interval is jittered ±30%% (default: 7)",
    )
    args = parser.parse_args()

    def _stop(sig, frame):
        global _running
        _running = False
        print("\n[product-publisher] Stopping gracefully...")

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    print("[product-publisher] Connecting to 4 AMPS instances...")
    for key, cfg in _AMPS_INSTANCES.items():
        print(f"  {key:<15} → {cfg['host']}:{cfg['port']}")

    clients: dict = {}
    for key, cfg in _AMPS_INSTANCES.items():
        clients[key] = _connect_one(key, cfg["host"], cfg["port"])

    active = sum(1 for c in clients.values() if c is not None)
    if active == 0:
        print("[product-publisher] ERROR: Could not connect to any AMPS instance. Exiting.")
        print("  Make sure the AMPS containers are running:")
        print("  docker compose -f docker-compose.amps.yml up -d")
        sys.exit(1)

    print(f"\n[product-publisher] Connected to {active}/4 instances. Mode={args.mode}, base_interval={args.interval}s")
    print(f"[product-publisher] Press Ctrl+C to stop\n")

    if args.mode in ("seed", "both"):
        print("[product-publisher] Seeding initial data...")
        seed(clients)
        print("[product-publisher] Seed complete.\n")

    if args.mode == "seed":
        for c in clients.values():
            if c:
                try:
                    c.disconnect()
                except Exception:
                    pass
        print("[product-publisher] Done.")
        return

    tick_num = 0
    while _running:
        tick_num += 1
        try:
            tick(clients, tick_num)
        except Exception as e:
            print(f"  [tick #{tick_num}] ERROR: {e}")
            # Try to reconnect failed instances
            for key, client in list(clients.items()):
                if client is None:
                    _reconnect(clients, key)

        time.sleep(args.interval * random.uniform(0.7, 1.3))

    for c in clients.values():
        if c:
            try:
                c.disconnect()
            except Exception:
                pass
    print(f"[product-publisher] Stopped after {tick_num} ticks.")


if __name__ == "__main__":
    main()
