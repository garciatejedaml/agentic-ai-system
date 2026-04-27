#!/bin/bash
# Double-click this file to launch the Carson dashboard.
# Closes when you press Ctrl+C in the Terminal window that opens.

set -e
cd "$(dirname "$0")/.."

if command -v python3 &> /dev/null; then PY=python3
elif command -v python &> /dev/null; then PY=python
else
  echo "Python 3 not found. Install it from https://www.python.org/downloads/ and try again."
  read -p "Press enter to close..."
  exit 1
fi

echo "==> using $($PY --version)"
echo "==> installing dependencies (one-time, ~10s)"
$PY -m pip install --user --quiet -r carson_dashboard/requirements.txt 2>/dev/null \
  || $PY -m pip install --user --break-system-packages --quiet -r carson_dashboard/requirements.txt 2>/dev/null \
  || $PY -m pip install --quiet -r carson_dashboard/requirements.txt

echo ""
echo "==> Carson dashboard running"
echo "==> open  http://127.0.0.1:8765/  in your browser"
echo "==> Ctrl+C here to stop"
echo ""

exec $PY -m carson_dashboard
