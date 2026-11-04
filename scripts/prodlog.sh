#!/usr/bin/env bash
# Search production's recent runtime log from the build computer (11-03-26).
#
#   scripts/prodlog.sh <web|delivery-worker> "<text>"
#
# Prints the last five matching lines of the component's last 60,000 log lines
# (about an hour of the worker: its HTTP request lines run near 700 a
# minute, so 5,000 lines held only seven minutes — found 11-04-26),
# case-insensitive. Exists so a runbook step stays one short line.
set -euo pipefail
component="${1:-}"; text="${2:-}"
[ -n "$component" ] && [ -n "$text" ] || { echo 'usage: scripts/prodlog.sh <web|delivery-worker> "<text>"' >&2; exit 64; }
doctl apps logs aa1ddf69-f359-4b53-91ba-035cbed7bd53 "$component" --type run --tail 60000 \
  | grep -i -- "$text" | tail -5
