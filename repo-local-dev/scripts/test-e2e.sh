#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# End-to-end test — Agentic AI System
# Copy and paste individual curl commands or run the whole script.
# ─────────────────────────────────────────────────────────────────────────────

API="http://localhost:8000/v1/chat/completions"

ask() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "TEST: $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    curl -s -X POST "$API" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"x\",\"messages\":[{\"role\":\"user\",\"content\":\"$2\"}]}"
}

# Health check
echo "Checking API..."
curl -sf http://localhost:8000/ > /dev/null && echo "API is UP" || { echo "API not reachable"; exit 1; }

# ── Tests ─────────────────────────────────────────────────────────────────────

ask "AMPS live positions"    "show me current trader positions"
ask "AMPS market data"       "what are the current bond prices in market data?"
ask "Portfolio NAV"          "show me portfolio NAV for all portfolios"
ask "CDS spreads"            "what are the current CDS spreads?"
ask "ETF flows"              "show me ETF NAV and flows"
ask "Risk metrics"           "what are the VaR and DV01 risk metrics by portfolio?"

echo ""
echo "Done."
