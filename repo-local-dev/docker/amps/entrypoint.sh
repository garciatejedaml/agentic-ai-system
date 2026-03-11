#!/bin/sh
# Select AMPS config based on AMPS_CONFIG env var (default: core)
# This avoids bind-mounting individual files, which fails on Windows VDI.
CONFIG="${AMPS_CONFIG:-core}"
CONFIG_FILE="/configs/config-${CONFIG}.xml"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Config not found: $CONFIG_FILE"
    echo "Valid values: core, portfolio, cds, etf, risk"
    exit 1
fi

echo "Starting AMPS with config: $CONFIG_FILE"
exec /AMPS/bin/ampServer "$CONFIG_FILE"
