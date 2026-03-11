# ─────────────────────────────────────────────────────────────────────────────
# End-to-end test — Agentic AI System
# Sends queries to the API and prints responses.
# Run from any directory:
#   .\repo-local-dev\scripts\test-e2e.ps1
# ─────────────────────────────────────────────────────────────────────────────

$API = "http://localhost:8000/v1/chat/completions"
$Headers = @{ "Content-Type" = "application/json" }

function Ask($label, $question) {
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
    Write-Host "TEST: $label" -ForegroundColor Cyan
    Write-Host "Q: $question" -ForegroundColor Yellow
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray

    $body = @{
        model    = "x"
        messages = @(@{ role = "user"; content = $question })
    } | ConvertTo-Json -Depth 5

    try {
        $resp = Invoke-RestMethod -Uri $API -Method POST -Headers $Headers -Body $body -TimeoutSec 120
        $content = $resp.choices[0].message.content
        Write-Host $content -ForegroundColor White
    } catch {
        Write-Host "ERROR: $_" -ForegroundColor Red
    }
}

# ── Health check ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Checking API health..." -ForegroundColor Green
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/" -TimeoutSec 10
    Write-Host "API is UP" -ForegroundColor Green
} catch {
    Write-Host "API not reachable — is the stack running?" -ForegroundColor Red
    exit 1
}

# ── Tests ─────────────────────────────────────────────────────────────────────

Ask "AMPS live positions" `
    "show me current trader positions"

Ask "AMPS live market data" `
    "what are the current bond prices in market data?"

Ask "Portfolio NAV" `
    "show me portfolio NAV for all portfolios"

Ask "CDS spreads" `
    "what are the current CDS spreads?"

Ask "ETF flows" `
    "show me ETF NAV and flows"

Ask "Risk metrics" `
    "what are the VaR and DV01 risk metrics by portfolio?"

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host "Done." -ForegroundColor Green
