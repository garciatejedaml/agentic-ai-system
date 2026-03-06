#!/usr/bin/env python3
"""
Synthetic Bond RFQ data generator for KDB POC.

Generates realistic Bond RFQ data that mirrors what would come from a real
KDB+ historical store (HY/IG/EM/RATES desks, multiple traders, 6 months history).

Output: data/kdb/bond_rfq.parquet

Usage:
    python scripts/generate_synthetic_rfq.py              # 100K rows (default)
    python scripts/generate_synthetic_rfq.py --rows 500000
"""
import argparse
import os
import random
from datetime import date, timedelta, time
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

# ── Desks & traders ───────────────────────────────────────────────────────────

DESKS = {
    "HY": {
        "spread_range": (180, 620),   # basis points over UST
        "rating_pool": ["BB+", "BB", "BB-", "B+", "B", "B-", "CCC+"],
        "traders": [
            ("T_HY_001", "Sarah Mitchell",   0.72),
            ("T_HY_002", "James Thornton",   0.58),
            ("T_HY_003", "Maria Gonzalez",   0.65),
            ("T_HY_004", "David Chen",       0.41),
            ("T_HY_005", "Emma Rodriguez",   0.69),
        ],
    },
    "IG": {
        "spread_range": (40, 220),
        "rating_pool": ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-"],
        "traders": [
            ("T_IG_001", "Robert Walsh",     0.68),
            ("T_IG_002", "Priya Sharma",     0.74),
            ("T_IG_003", "Michael O'Brien",  0.55),
            ("T_IG_004", "Lisa Park",        0.62),
            ("T_IG_005", "Carlos Mendez",    0.48),
        ],
    },
    "EM": {
        "spread_range": (120, 480),
        "rating_pool": ["BB+", "BB", "BB-", "B+", "B", "BBB-", "BBB"],
        "traders": [
            ("T_EM_001", "Yuki Tanaka",      0.61),
            ("T_EM_002", "Aisha Okonkwo",    0.67),
            ("T_EM_003", "Pavel Novikov",    0.53),
            ("T_EM_004", "Sofia Andersen",   0.70),
            ("T_EM_005", "Hassan Al-Rashid", 0.44),
        ],
    },
    "RATES": {
        "spread_range": (5, 80),
        "rating_pool": ["AAA", "AA+", "AA"],
        "traders": [
            ("T_RT_001", "Benjamin Clarke",  0.76),
            ("T_RT_002", "Natalie Dubois",   0.63),
            ("T_RT_003", "Andreas Mueller",  0.57),
            ("T_RT_004", "Jin Wei",          0.71),
            ("T_RT_005", "Isabella Ferrari", 0.49),
        ],
    },
}

ISSUERS = {
    "HY":    ["Ford Motor Co", "Sprint Corp", "Caesars Entertainment", "Bausch Health",
              "Intelsat", "Frontier Communications", "Revlon", "WeWork", "Rite Aid",
              "Bed Bath & Beyond", "Carvana", "Envision Healthcare"],
    "IG":    ["Apple Inc", "Microsoft Corp", "JPMorgan Chase", "Amazon.com",
              "Berkshire Hathaway", "Exxon Mobil", "Johnson & Johnson", "Visa Inc",
              "Procter & Gamble", "UnitedHealth Group"],
    "EM":    ["Petrobras", "Vale SA", "Pemex", "Saudi Aramco", "Alibaba Group",
              "Tencent Holdings", "CNOOC Ltd", "Turkish Airlines", "MTN Group"],
    "RATES": ["US Treasury", "German Bund", "UK Gilt", "Japan JGB",
              "French OAT", "Italian BTP"],
}

SECTORS = {
    "HY":    ["Automotive", "Telecom", "Gaming/Leisure", "Healthcare", "Retail",
              "Technology", "Energy", "Media"],
    "IG":    ["Technology", "Financial", "Healthcare", "Consumer", "Industrial",
              "Energy", "Utilities"],
    "EM":    ["Energy", "Metals/Mining", "Financial", "Telecom", "Sovereign"],
    "RATES": ["Government"],
}

VENUES = ["Bloomberg", "TradeWeb", "MarketAxess", "Voice", "D2C"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _random_isin(desk: str) -> str:
    prefix = {"HY": "US", "IG": "US", "EM": "XS", "RATES": "US"}[desk]
    return prefix + "".join(random.choices("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=10))


def _random_time() -> str:
    """Trading hours: 08:00–17:30 NY time."""
    h = random.randint(8, 17)
    m = random.randint(0, 59)
    s = random.randint(0, 59)
    ms = random.randint(0, 999)
    if h == 17 and m > 30:
        m = random.randint(0, 30)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _generate_rows(n_rows: int, desk: str) -> pd.DataFrame:
    cfg = DESKS[desk]
    traders = cfg["traders"]
    spread_lo, spread_hi = cfg["spread_range"]
    issuers = ISSUERS[desk]
    sectors = SECTORS[desk]

    # Date range: last 6 months
    end_date = date.today()
    start_date = end_date - timedelta(days=182)
    date_range = pd.date_range(start_date, end_date, freq="D")
    # Exclude weekends
    biz_days = [d for d in date_range if d.weekday() < 5]

    rows = []
    for i in range(n_rows):
        trader_id, trader_name, base_hit_rate = random.choice(traders)
        # Slight per-row jitter on hit rate
        hit_rate = min(0.95, max(0.10, base_hit_rate + np.random.normal(0, 0.05)))
        won = random.random() < hit_rate

        issuer = random.choice(issuers)
        coupon = round(random.uniform(2.5, 9.5), 3)
        maturity_year = random.randint(2026, 2034)
        bond_name = f"{issuer.split()[0].upper()} {coupon:.3f} {maturity_year}"
        isin = _random_isin(desk)
        spread = round(random.uniform(spread_lo, spread_hi), 1)
        notional = round(random.choice([1, 2, 3, 5, 7, 10, 15, 20, 25, 50]) * 1_000_000, 0)
        price = round(100 - spread / 100 + random.uniform(-2, 2), 4)
        rfq_date = random.choice(biz_days)

        rows.append({
            "rfq_id":            f"RFQ_{rfq_date.strftime('%Y%m%d')}_{i:07d}",
            "desk":              desk,
            "trader_id":         trader_id,
            "trader_name":       trader_name,
            "isin":              isin,
            "bond_name":         bond_name,
            "issuer":            issuer,
            "sector":            random.choice(sectors),
            "rating":            random.choice(cfg["rating_pool"]),
            "side":              random.choice(["buy", "sell"]),
            "notional_usd":      notional,
            "price":             price,
            "spread_bps":        spread,
            "coupon":            coupon,
            "rfq_date":          rfq_date.date(),
            "rfq_time":          _random_time(),
            "response_time_ms":  random.randint(80, 3000),
            "won":               won,
            "hit_rate":          round(hit_rate, 4),
            "venue":             random.choice(VENUES),
        })

    return pd.DataFrame(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def generate(n_rows: int = 100_000, output_path: str = "data/kdb/bond_rfq.parquet") -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    desk_weights = {"HY": 0.35, "IG": 0.30, "EM": 0.20, "RATES": 0.15}
    frames = []
    for desk, weight in desk_weights.items():
        desk_rows = max(1, int(n_rows * weight))
        print(f"  Generating {desk_rows:,} {desk} RFQs...")
        frames.append(_generate_rows(desk_rows, desk))

    df = pd.concat(frames, ignore_index=True)
    df = df.sample(frac=1, random_state=SEED).reset_index(drop=True)  # shuffle

    df.to_parquet(output, index=False, compression="snappy")
    print(f"\nWrote {len(df):,} rows → {output}")
    print(f"File size: {output.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"\nDesk breakdown:\n{df.groupby('desk').size().to_string()}")
    print(f"\nTop traders by hit_rate (HY):")
    hy = df[df.desk == "HY"].groupby(["trader_id", "trader_name"])["hit_rate"].mean().sort_values(ascending=False)
    print(hy.to_string())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic Bond RFQ data")
    parser.add_argument("--rows", type=int, default=100_000, help="Total rows to generate")
    parser.add_argument("--output", type=str, default="data/kdb/bond_rfq.parquet", help="Output Parquet path")
    args = parser.parse_args()

    print(f"Generating {args.rows:,} synthetic Bond RFQ rows...")
    generate(args.rows, args.output)
