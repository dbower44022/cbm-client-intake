#!/usr/bin/env bash
# Create the event email templates on a chapter's CRM, by chapter name.
#
#   scripts/seed_templates.sh <chapter>            dry run: lists what is missing
#   scripts/seed_templates.sh <chapter> --apply    creates the missing ones
#
# Wraps scripts/seed_event_templates.py for the same reason scripts/apply_plan.sh
# wraps the plan applier: the full invocation is past the one-line limit a pasted
# command survives. A template that already exists is never touched, so staff
# edits survive a re-run. The credential file is PARSED by run_with_admin.py,
# never sourced by this shell.
#
# Chapters, as scripts/apply_plan.sh: test, boston, lakeside, bma. Production
# keeps its administrator credential inside its web container; run
# scripts/seed_event_templates.py there (see its docstring).
set -euo pipefail
cd "$(dirname "$0")/.."
chapter="${1:-}"; apply="${2:-}"
usage() { echo "usage: scripts/seed_templates.sh <test|boston|lakeside|bma> [--apply]" >&2; exit 64; }
[ -n "$chapter" ] || usage
case "$chapter" in
  test)     envfile=".env" ;;
  boston)   envfile="$HOME/.config/cbm-boston/boston.env" ;;
  lakeside) envfile="$HOME/.config/cbm-lakeside/lakeside.env" ;;
  bma)      envfile="$HOME/.config/cbm-bma/bma.env" ;;
  *)        echo "unknown chapter '$chapter'" >&2; usage ;;
esac
[ -r "$envfile" ] || { echo "no credential file at $envfile" >&2; exit 66; }
flags=()
case "$apply" in
  "")      ;;
  --apply) flags=(--apply) ;;
  *)       usage ;;
esac
echo "== $chapter: seed_event_templates.py ${flags[*]:-(dry run)}" >&2
PYTHONPATH=. exec uv run python scripts/run_with_admin.py --env "$envfile" \
  scripts/seed_event_templates.py "${flags[@]}"
