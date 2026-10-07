#!/usr/bin/env bash
# Short front door for the HubSpot load, so a command never wraps in a terminal.
#   scripts/hubspot/run.sh lakeside plan      dry run (real reads, fake writes)
#   scripts/hubspot/run.sh lakeside write     apply, resuming from the ledger
#   scripts/hubspot/run.sh lakeside rebuild   apply after recovering the ledger from the CRM
#   scripts/hubspot/run.sh lakeside repair    stamp every imported session with its mentor team
#   scripts/hubspot/run.sh boston <mode>      the same against Boston
set -euo pipefail
cd "$(dirname "$0")/../.."
case "${1:-}" in
  lakeside) env="$HOME/.config/cbm-lakeside/lakeside.env" ;;
  boston)   env="$HOME/.config/cbm-boston/boston.env" ;;
  *) echo "usage: $0 {lakeside|boston} {plan|write|rebuild|repair}" >&2; exit 2 ;;
esac
case "${2:-}" in
  plan)    flags="" ;;
  write)   flags="--write" ;;
  rebuild) flags="--write --rebuild-ledger" ;;
  repair)  flags="--write --repair-session-stamps" ;;
  *) echo "usage: $0 {lakeside|boston} {plan|write|rebuild|repair}" >&2; exit 2 ;;
esac
# shellcheck disable=SC2086
uv run --with tenacity python scripts/hubspot/load_boston.py --target "$env" $flags 2>&1 \
  | grep -v ' - DEBUG - ' | grep -v 'dropping unrecognized'
