#!/usr/bin/env python3
"""
AMPS Data Publisher Simulator

Publishes realistic financial data to AMPS SOW topics to simulate live market
activity. Uses the same traders and bonds as the KDB synthetic dataset so that
the agentic system can correlate historical (KDB) vs live (AMPS) data.

Topics:
  positions   → current trader positions, one record per (trader_id + isin)
  orders      → live/recent bond orders, one record per order_id
  market-data → live bond prices, one record per ISIN symbol

Usage:
  python scripts/amps_publisher.py                     # seed + continuous ticks
  python scripts/amps_publisher.py --mode seed         # initial load only
  python scripts/amps_publisher.py --mode tick         # updates only (no seed)
  python scripts/amps_publisher.py --interval 2        # seconds between ticks (default: 2)
  python scripts/amps_publisher.py --host localhost --port 9007

AWS / Lambda invocation:
  MODE=seed python scripts/amps_publisher.py
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

# ── Reference data (consistent with generate_synthetic_rfq.py) ────────────────

_TRADERS = [
    {"id": "T_HY_001", "name": "Sarah Mitchell",  "desk": "HY"},
    {"id": "T_HY_002", "name": "James Thornton",  "desk": "HY"},
    {"id": "T_HY_003", "name": "Maria Gonzalez",  "desk": "HY"},
    {"id": "T_HY_004", "name": "David Chen",       "desk": "HY"},
    {"id": "T_HY_005", "name": "Emma Rodriguez",   "desk": "HY"},
    {"id": "T_IG_001", "name": "Michael Foster",   "desk": "IG"},
    {"id": "T_IG_002", "name": "Jennifer Park",    "desk": "IG"},
    {"id": "T_IG_003", "name": "Robert Kim",       "desk": "IG"},
    {"id": "T_EM_001", "name": "Carlos Rivera",    "desk": "EM"},
    {"id": "T_EM_002", "name": "Priya Sharma",     "desk": "EM"},
    {"id": "T_RATES_001", "name": "Thomas Hughes", "desk": "RATES"},
    {"id": "T_RATES_002", "name": "Sophie Laurent","desk": "RATES"},
]

_BONDS = [
    # HY bonds (high spread, lower ratings)
    {"isin": "US345370CY87", "name": "Ford Motor 8.5% 2028",     "issuer": "Ford Motor",       "desk": "HY",    "coupon": 8.5,  "base_spread": 340, "base_price": 98.5},
    {"isin": "US92336GAN41", "name": "Verizon 7.0% 2027",        "issuer": "Verizon",          "desk": "HY",    "coupon": 7.0,  "base_spread": 280, "base_price": 99.1},
    {"isin": "US38141GXG96", "name": "Goldman Sachs 6.75% 2029", "issuer": "Goldman Sachs",    "desk": "HY",    "coupon": 6.75, "base_spread": 310, "base_price": 97.8},
    {"isin": "US037833DV79", "name": "Apple 5.25% 2028",         "issuer": "Apple",            "desk": "HY",    "coupon": 5.25, "base_spread": 260, "base_price": 100.2},
    {"isin": "US594918BW80", "name": "Microsoft 4.75% 2030",     "issuer": "Microsoft",        "desk": "HY",    "coupon": 4.75, "base_spread": 230, "base_price": 99.6},
    # IG bonds (tighter spread)
    {"isin": "US166764BG78", "name": "Chevron 3.5% 2029",        "issuer": "Chevron",          "desk": "IG",    "coupon": 3.5,  "base_spread": 85,  "base_price": 101.2},
    {"isin": "US931142EK26", "name": "Walmart 2.85% 2031",       "issuer": "Walmart",          "desk": "IG",    "coupon": 2.85, "base_spread": 60,  "base_price": 102.1},
    {"isin": "US037833AK68", "name": "Apple 2.4% 2023",          "issuer": "Apple",            "desk": "IG",    "coupon": 2.4,  "base_spread": 45,  "base_price": 100.8},
    # EM bonds
    {"isin": "US105756BQ96", "name": "Brazil 5.625% 2041",       "issuer": "Brazil",           "desk": "EM",    "coupon": 5.625,"base_spread": 195, "base_price": 96.3},
    {"isin": "US4MEXSOV001", "name": "Mexico 4.75% 2032",        "issuer": "Mexico",           "desk": "EM",    "coupon": 4.75, "base_spread": 165, "base_price": 98.7},
    # RATES (gov bonds)
    {"isin": "US912797HS68", "name": "UST 4.25% 2026",           "issuer": "US Treasury",      "desk": "RATES", "coupon": 4.25, "base_spread": 0,   "base_price": 100.1},
    {"isin": "US912810TM57", "name": "UST 4.5% 2033",            "issuer": "US Treasury",      "desk": "RATES", "coupon": 4.5,  "base_spread": 0,   "base_price": 99.8},
]

_VENUES = ["Bloomberg", "TradeWeb", "MarketAxess", "Voice", "D2C"]
_SIDES   = ["buy", "sell"]

_running = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _jitter(base: float, pct: float = 0.02) -> float:
    """Apply ±pct% random noise to a base value."""
    return round(base * (1 + random.uniform(-pct, pct)), 4)


# ── Record generators ──────────────────────────────────────────────────────────

def _make_market_data_record(bond: dict) -> dict:
    mid    = _jitter(bond["base_price"], 0.005)
    half   = round(random.uniform(0.1, 0.4), 3)
    spread = _jitter(bond["base_spread"], 0.03) if bond["base_spread"] > 0 else 0.0
    return {
        "symbol":     bond["isin"],
        "isin":       bond["isin"],
        "bond_name":  bond["name"],
        "issuer":     bond["issuer"],
        "desk":       bond["desk"],
        "coupon":     bond["coupon"],
        "bid":        round(mid - half, 3),
        "ask":        round(mid + half, 3),
        "mid":        round(mid, 3),
        "spread_bps": round(spread, 1),
        "yield_pct":  round(bond["coupon"] / mid * 100 + random.uniform(-0.1, 0.1), 4),
        "benchmark":  "UST10Y" if bond["desk"] in ("IG", "RATES") else "UST5Y",
        "volume_usd": random.randint(5, 150) * 1_000_000,
        "timestamp":  _now(),
    }


def _make_position_record(trader: dict, bond: dict) -> dict:
    qty       = random.randint(1, 50) * 1_000_000   # notional in USD
    avg_cost  = _jitter(bond["base_price"], 0.01)
    mkt_price = _jitter(avg_cost, 0.005)
    mkt_value = round(qty * mkt_price / 100, 2)
    pnl       = round(qty * (mkt_price - avg_cost) / 100, 2)
    return {
        "id":          f"{trader['id']}_{bond['isin']}",
        "trader_id":   trader["id"],
        "trader_name": trader["name"],
        "desk":        trader["desk"],
        "isin":        bond["isin"],
        "bond_name":   bond["name"],
        "issuer":      bond["issuer"],
        "side":        random.choice(_SIDES),
        "quantity":    qty,
        "avg_cost":    round(avg_cost, 4),
        "market_price":round(mkt_price, 4),
        "market_value":mkt_value,
        "pnl":         pnl,
        "spread_bps":  round(_jitter(bond["base_spread"], 0.05), 1),
        "timestamp":   _now(),
    }


def _make_order_record(trader: dict, bond: dict, order_id: str) -> dict:
    price  = _jitter(bond["base_price"], 0.005)
    spread = _jitter(bond["base_spread"], 0.04) if bond["base_spread"] > 0 else 0.0
    return {
        "order_id":    order_id,
        "trader_id":   trader["id"],
        "trader_name": trader["name"],
        "desk":        trader["desk"],
        "isin":        bond["isin"],
        "bond_name":   bond["name"],
        "issuer":      bond["issuer"],
        "side":        random.choice(_SIDES),
        "notional_usd":random.randint(1, 30) * 1_000_000,
        "price":       round(price, 4),
        "spread_bps":  round(spread, 1),
        "status":      random.choice(["pending", "filled", "filled", "filled", "cancelled"]),
        "venue":       random.choice(_VENUES),
        "response_ms": random.randint(400, 3000),
        "timestamp":   _now(),
    }


# ── Publish helpers ────────────────────────────────────────────────────────────

def _publish(client, topic: str, record: dict) -> None:
    client.publish(topic, json.dumps(record))


def _connect(host: str, port: int) -> "AMPS.Client":
    from AMPS import Client
    client = Client("amps-publisher-sim")
    client.connect(f"tcp://{host}:{port}/amps/json")
    client.logon()
    return client


# ── Seed: publish a full snapshot of all topics ───────────────────────────────

def seed(client, verbose: bool = True) -> dict:
    """Publish initial records for all topics. Returns counts per topic."""
    counts = {"positions": 0, "orders": 0, "market-data": 0}

    # market-data: one record per bond
    for bond in _BONDS:
        _publish(client, "market-data", _make_market_data_record(bond))
        counts["market-data"] += 1

    # positions: each trader holds a subset of bonds from their desk
    desk_bonds = {}
    for bond in _BONDS:
        desk_bonds.setdefault(bond["desk"], []).append(bond)

    for trader in _TRADERS:
        bonds_for_desk = desk_bonds.get(trader["desk"], _BONDS[:3])
        # Each trader has 2–4 positions
        for bond in random.sample(bonds_for_desk, min(len(bonds_for_desk), random.randint(2, 4))):
            _publish(client, "positions", _make_position_record(trader, bond))
            counts["positions"] += 1

    # orders: 20 recent orders across all traders
    ts = int(time.time() * 1000)
    for i in range(20):
        trader = random.choice(_TRADERS)
        bonds_for_desk = desk_bonds.get(trader["desk"], _BONDS)
        bond = random.choice(bonds_for_desk)
        order_id = f"ORD-{ts}-{i:03d}"
        _publish(client, "orders", _make_order_record(trader, bond, order_id))
        counts["orders"] += 1

    if verbose:
        print(f"  [seed] market-data: {counts['market-data']} records")
        print(f"  [seed] positions:   {counts['positions']} records")
        print(f"  [seed] orders:      {counts['orders']} records")

    return counts


# ── Tick: publish a random subset of updates ─────────────────────────────────

def tick(client, tick_num: int) -> None:
    """Publish a small random batch of updates to simulate live activity."""
    desk_bonds = {}
    for bond in _BONDS:
        desk_bonds.setdefault(bond["desk"], []).append(bond)

    updates = []

    # 3–6 market-data ticks (prices move constantly)
    for bond in random.sample(_BONDS, random.randint(3, 6)):
        _publish(client, "market-data", _make_market_data_record(bond))
        updates.append(f"market-data/{bond['isin'][:12]}")

    # 1–3 position updates (traders re-mark their books)
    for _ in range(random.randint(1, 3)):
        trader = random.choice(_TRADERS)
        bonds_for_desk = desk_bonds.get(trader["desk"], _BONDS)
        bond = random.choice(bonds_for_desk)
        _publish(client, "positions", _make_position_record(trader, bond))
        updates.append(f"positions/{trader['id']}")

    # 0–2 new orders (not every tick has a new order)
    ts = int(time.time() * 1000)
    for i in range(random.randint(0, 2)):
        trader = random.choice(_TRADERS)
        bonds_for_desk = desk_bonds.get(trader["desk"], _BONDS)
        bond = random.choice(bonds_for_desk)
        order_id = f"ORD-{ts}-T{tick_num:04d}-{i}"
        _publish(client, "orders", _make_order_record(trader, bond, order_id))
        updates.append(f"orders/{order_id}")

    ts_str = datetime.now().strftime("%H:%M:%S")
    print(f"  [tick #{tick_num:04d} @ {ts_str}] {len(updates)} updates: {', '.join(updates[:5])}{'...' if len(updates) > 5 else ''}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="AMPS live data publisher simulator")
    parser.add_argument("--host",     default=os.getenv("AMPS_HOST", "localhost"))
    parser.add_argument("--port",     type=int, default=int(os.getenv("AMPS_PORT", "9007")))
    parser.add_argument(
        "--mode",
        choices=["seed", "tick", "both"],
        default=os.getenv("MODE", "both"),
        help="seed=initial load only | tick=updates only | both=seed then continuous ticks",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("TICK_INTERVAL", "2")),
        help="Seconds between ticks (default: 2)",
    )
    args = parser.parse_args()

    def _stop(sig, frame):
        global _running
        _running = False
        print("\n[publisher] Stopping gracefully...")

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    print(f"[publisher] Connecting to AMPS at {args.host}:{args.port}...")
    try:
        client = _connect(args.host, args.port)
    except Exception as e:
        print(f"[publisher] ERROR: Cannot connect to AMPS: {e}")
        print("  Make sure the AMPS container is running:")
        print("  docker compose -f docker-compose.amps.yml up -d")
        sys.exit(1)

    print(f"[publisher] Connected. Mode={args.mode}, interval={args.interval}s")
    print(f"[publisher] Publishing to topics: positions, orders, market-data")
    print(f"[publisher] Press Ctrl+C to stop\n")

    if args.mode in ("seed", "both"):
        print("[publisher] Seeding initial data...")
        seed(client)
        print("[publisher] Seed complete.\n")

    if args.mode == "seed":
        client.disconnect()
        print("[publisher] Done.")
        return

    # Continuous tick loop
    tick_num = 0
    while _running:
        tick_num += 1
        try:
            tick(client, tick_num)
        except Exception as e:
            print(f"  [tick #{tick_num}] ERROR: {e} — reconnecting...")
            try:
                client = _connect(args.host, args.port)
            except Exception:
                print("  Reconnect failed. Waiting before retry...")

        time.sleep(args.interval)

    client.disconnect()
    print(f"[publisher] Stopped after {tick_num} ticks.")


if __name__ == "__main__":
    main()
