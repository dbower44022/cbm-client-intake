#!/usr/bin/env bash
# Search production's recent runtime log from the build computer (11-03-26).
#
#   scripts/prodlog.sh <web|delivery-worker> "<text>"
#
# Prints the last five matching lines of the component's last 5,000 log lines,
# case-insensitive. Exists so a runbook step stays one short line.
set -euo pipefail
component="${1:-}"; text="${2:-}"
[ -n "$component" ] && [ -n "$text" ] || { echo 'usage: scripts/prodlog.sh <web|delivery-worker> "<text>"' >&2; exit 64; }
doctl apps logs aa1ddf69-f359-4b53-91ba-035cbed7bd53 "$component" --type run --tail 5000 \
  | grep -i -- "$text" | tail -5
