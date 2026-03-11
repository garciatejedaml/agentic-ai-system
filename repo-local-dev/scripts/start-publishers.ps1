# ─────────────────────────────────────────────────────────────────────────────
# Start AMPS publishers via docker run (bypasses compose OCI issue on Windows VDI)
# Run from any directory:
#   .\repo-local-dev\scripts\start-publishers.ps1
# ─────────────────────────────────────────────────────────────────────────────

Write-Host "Stopping existing publisher containers..." -ForegroundColor Yellow
docker rm -f amps-publisher product-publisher 2>$null

Write-Host "Starting amps-publisher..." -ForegroundColor Cyan
docker run -d `
  --name amps-publisher `
  --network agentic-ai_default `
  -e AMPS_HOST=amps-core `
  -e AMPS_PORT=9007 `
  -e MODE=both `
  -e TICK_INTERVAL=2 `
  --restart on-failure `
  agentic-ai-publisher:latest `
  scripts/amps_publisher.py

Write-Host "Starting product-publisher..." -ForegroundColor Cyan
docker run -d `
  --name product-publisher `
  --network agentic-ai_default `
  -e AMPS_PORTFOLIO_HOST=amps-portfolio `
  -e AMPS_PORTFOLIO_PORT=9007 `
  -e AMPS_CDS_HOST=amps-cds `
  -e AMPS_CDS_PORT=9007 `
  -e AMPS_ETF_HOST=amps-etf `
  -e AMPS_ETF_PORT=9007 `
  -e AMPS_RISK_HOST=amps-risk `
  -e AMPS_RISK_PORT=9007 `
  -e MODE=both `
  -e TICK_INTERVAL=7 `
  --restart on-failure `
  agentic-ai-publisher:latest `
  scripts/product_publishers.py

Write-Host ""
Write-Host "Done. Checking status..." -ForegroundColor Green
docker ps --filter "name=amps-publisher" --filter "name=product-publisher" --format "table {{.Names}}\t{{.Status}}"
