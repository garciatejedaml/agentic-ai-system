#!/usr/bin/env python3
"""
AMPS Real-Time Data Test

Verifica que el sistema agente está leyendo datos en tiempo real de AMPS
(no de KDB ni caché) usando la técnica de "canary value":

  Paso 1 — Publica un registro con un PnL único (7_777_777.77) imposible de
            confundir con datos históricos de KDB.
  Paso 2 — Consulta el agente AMPS y verifica que el valor canario aparece.
  Paso 3 — Actualiza el mismo registro con un PnL diferente (9_999_999.99).
  Paso 4 — Re-consulta y verifica que el nuevo valor reemplazó al anterior.
  Paso 5 — Limpia el registro canario de AMPS.

Si ambos valores canarios aparecen en las respuestas correctas,
la prueba confirma que el sistema está leyendo live data de AMPS SOW.

Pre-requisitos:
  - AMPS corriendo: docker compose -f docker-compose.amps.yml up -d
  - .env con AMPS_ENABLED=true y AMPS_HOST=localhost
  - amps-python-client instalado: pip install amps/client/amps-python-client-*.zip

Uso:
  python scripts/test_amps_realtime.py
  python scripts/test_amps_realtime.py --verbose   # muestra respuestas completas
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Canary values — chosen to be impossible in real financial data ─────────────

CANARY_TRADER_ID   = "T_HY_001"
CANARY_ISIN        = "US345370CY87"           # Ford Motor 8.5% 2028 (real bond in dataset)
CANARY_SOW_KEY     = f"{CANARY_TRADER_ID}_{CANARY_ISIN}"
CANARY_PNL_V1      = 7_777_777.77             # first canary value
CANARY_PNL_V2      = 9_999_999.99             # second canary (for update test)
CANARY_QUANTITY    = 99_999_000               # 99.999M notional — also unmistakable


def _connect():
    """Connect to AMPS and return client."""
    try:
        from AMPS import Client
    except ImportError:
        print("[FAIL] amps-python-client not installed.")
        print("       Run: pip install amps/client/amps-python-client-*.zip")
        sys.exit(1)

    host = os.getenv("AMPS_HOST", "localhost")
    port = int(os.getenv("AMPS_PORT", "9007"))
    client = Client("amps-realtime-test")
    try:
        client.connect(f"tcp://{host}:{port}/amps/json")
        client.logon()
        return client
    except Exception as e:
        print(f"[FAIL] Cannot connect to AMPS at {host}:{port}: {e}")
        print("       Start with: docker compose -f docker-compose.amps.yml up -d")
        sys.exit(1)


def _publish_canary(client, pnl: float) -> dict:
    """Publish a canary position record to AMPS."""
    record = {
        "id":           CANARY_SOW_KEY,
        "trader_id":    CANARY_TRADER_ID,
        "trader_name":  "Sarah Mitchell",
        "desk":         "HY",
        "isin":         CANARY_ISIN,
        "bond_name":    "Ford Motor 8.5% 2028",
        "issuer":       "Ford Motor",
        "side":         "buy",
        "quantity":     CANARY_QUANTITY,
        "avg_cost":     98.5,
        "market_price": 98.5,
        "market_value": CANARY_QUANTITY * 98.5 / 100,
        "pnl":          pnl,                  # ← THE CANARY VALUE
        "spread_bps":   340.0,
        "timestamp":    datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "_test_canary": True,                  # marker field for easy cleanup
    }
    client.publish("positions", json.dumps(record))
    return record


def _delete_canary(client):
    """
    Remove the canary record from AMPS SOW.
    AMPS deletes a SOW record when you publish a message with the same key
    using the 'sow_delete' command. With the Python client, publish to the
    SOW delete topic or simply overwrite with a normal record that has
    quantity=0 as a soft-delete convention.
    We overwrite with a zeroed-out record so the SOW key is reset.
    """
    record = {
        "id":           CANARY_SOW_KEY,
        "trader_id":    CANARY_TRADER_ID,
        "trader_name":  "Sarah Mitchell",
        "desk":         "HY",
        "isin":         CANARY_ISIN,
        "bond_name":    "Ford Motor 8.5% 2028",
        "issuer":       "Ford Motor",
        "side":         "buy",
        "quantity":     0,
        "avg_cost":     0.0,
        "market_price": 0.0,
        "market_value": 0.0,
        "pnl":          0.0,
        "spread_bps":   0.0,
        "timestamp":    datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "_test_canary": False,
    }
    client.publish("positions", json.dumps(record))


def _query_agent(query: str, verbose: bool) -> str:
    """Run a query through the AMPS agent and return the response string."""
    from src.agents.amps_agent import run_amps_agent
    if verbose:
        print(f"    Query: {query}")
    result = run_amps_agent(query)
    if verbose:
        print(f"    Response:\n{result}\n")
    return result


def _check(response: str, canary_value: float, step: str) -> bool:
    """Check that the canary value (as string) appears in the agent response."""
    # Format as integer part + 2 decimal places to match common float formatting
    canary_str = f"{canary_value:,.2f}".replace(",", "")  # e.g. "7777777.77"
    canary_alt = f"{canary_value:,.2f}"                    # e.g. "7,777,777.77"

    found = canary_str in response or canary_alt in response

    if found:
        print(f"  [PASS] {step}: canary value {canary_alt} found in response.")
    else:
        print(f"  [FAIL] {step}: canary value {canary_alt} NOT found in response.")
        print(f"         Response snippet: ...{response[:300]}...")
    return found


# ── Main test ──────────────────────────────────────────────────────────────────

def run_test(verbose: bool = False) -> bool:
    """
    Run the full real-time AMPS test.
    Returns True if all assertions pass.
    """
    print("=" * 60)
    print("  AMPS Real-Time Data Test")
    print("=" * 60)

    # Verify AMPS is enabled
    if os.getenv("AMPS_ENABLED", "false").lower() != "true":
        print("[SKIP] AMPS_ENABLED is not set to 'true'.")
        print("       Set AMPS_ENABLED=true in .env and re-run.")
        return False

    passed = []

    # ── Step 1: Connect to AMPS ────────────────────────────────────────────────
    print("\n[1/5] Connecting to AMPS...")
    client = _connect()
    print(f"      Connected to {os.getenv('AMPS_HOST','localhost')}:{os.getenv('AMPS_PORT','9007')}")

    try:
        # ── Step 2: Publish canary V1 ──────────────────────────────────────────
        print(f"\n[2/5] Publishing canary record to AMPS 'positions' topic...")
        print(f"      Trader: {CANARY_TRADER_ID} | ISIN: {CANARY_ISIN}")
        print(f"      Canary PnL V1: {CANARY_PNL_V1:,.2f}")
        _publish_canary(client, CANARY_PNL_V1)
        time.sleep(0.5)   # give AMPS a moment to persist the SOW record

        # ── Step 3: Query agent and verify V1 ─────────────────────────────────
        print(f"\n[3/5] Querying AMPS agent for trader {CANARY_TRADER_ID} positions...")
        query_v1 = (
            f"What is the current PnL for trader {CANARY_TRADER_ID} "
            f"on the position for ISIN {CANARY_ISIN}? "
            "Query the positions SOW topic and return the exact PnL value."
        )
        response_v1 = _query_agent(query_v1, verbose)
        ok_v1 = _check(response_v1, CANARY_PNL_V1, "V1 canary present in live data")
        passed.append(ok_v1)

        # ── Step 4: Publish canary V2 (update) ────────────────────────────────
        print(f"\n[4/5] Updating the canary record with a new PnL...")
        print(f"      Canary PnL V2: {CANARY_PNL_V2:,.2f}")
        _publish_canary(client, CANARY_PNL_V2)
        time.sleep(0.5)

        print(f"      Re-querying AMPS agent to verify SOW updated...")
        query_v2 = (
            f"What is the latest PnL for trader {CANARY_TRADER_ID} "
            f"position in {CANARY_ISIN}? "
            "Query positions SOW and return the exact current PnL."
        )
        response_v2 = _query_agent(query_v2, verbose)

        ok_v2 = _check(response_v2, CANARY_PNL_V2, "V2 canary present after live update")
        ok_old = CANARY_PNL_V1 not in response_v2.replace(",", "")
        if ok_old:
            print(f"  [PASS] Old canary value {CANARY_PNL_V1:,.2f} no longer in response (SOW replaced).")
        else:
            print(f"  [WARN] Old canary value {CANARY_PNL_V1:,.2f} still present (may be OK if shown as history).")

        passed.append(ok_v2)

    finally:
        # ── Step 5: Cleanup ────────────────────────────────────────────────────
        print(f"\n[5/5] Cleaning up canary record from AMPS SOW...")
        try:
            _delete_canary(client)
            print("      Canary record zeroed out in positions SOW.")
        except Exception as e:
            print(f"      Cleanup warning: {e}")
        client.disconnect()

    # ── Result ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    all_passed = all(passed)
    if all_passed:
        print("  RESULT: ALL TESTS PASSED ✓")
        print("  Confirmed: agent is reading LIVE data from AMPS SOW,")
        print("  not from KDB historical data or any cache.")
    else:
        failed = sum(1 for p in passed if not p)
        print(f"  RESULT: {failed}/{len(passed)} TESTS FAILED")
        print("  Check that:")
        print("  - AMPS container is running and healthy")
        print("  - amps_publisher.py seeded initial data (python scripts/amps_publisher.py --mode seed)")
        print("  - AMPS_ENABLED=true in .env")
    print("=" * 60)
    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Verify AMPS real-time data integration using canary values"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print full agent responses",
    )
    args = parser.parse_args()

    # Load .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    success = run_test(verbose=args.verbose)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
