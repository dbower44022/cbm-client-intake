#!/usr/bin/env bash
# Run the read-only Zoom probe (scripts/probe_zoom.py) from the build computer
# without putting the credentials on a command line or in shell history
# (11-04-26). Asks for the three values; the secret is not echoed.
#
#   scripts/zoom_probe.sh
set -euo pipefail
cd "$(dirname "$0")/.."
read -r -p "Zoom Account ID: " ZOOM_ACCOUNT_ID
read -r -p "Zoom Client ID: " ZOOM_CLIENT_ID
read -r -s -p "Zoom Client Secret (not shown): " ZOOM_CLIENT_SECRET; echo
export ZOOM_ACCOUNT_ID ZOOM_CLIENT_ID ZOOM_CLIENT_SECRET
export ZOOM_HOST_EMAIL="${ZOOM_HOST_EMAIL:-zweb@cbmentors.org}"
PYTHONPATH=. exec uv run python scripts/probe_zoom.py
