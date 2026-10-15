#!/usr/bin/env bash
# Apply a CRM plan to a chapter's CRM from this computer, by chapter name.
#
#   scripts/apply_plan.sh <chapter> <plan.json>                 dry run
#   scripts/apply_plan.sh <chapter> <plan.json> <fingerprint>   apply exactly that plan
#
#   scripts/apply_plan.sh boston scripts/plans/additional-managers.json
#   scripts/apply_plan.sh boston scripts/plans/additional-managers.json f2d6a41ea16c
#
# Exists for the same reason as scripts/on_crm.sh: the full invocation
# (run_with_admin.py --env <file> apply_crm_plan.py <plan> --apply --production
# --expect <fingerprint>) is far past the one-line limit a pasted command can
# survive. The credential file is PARSED by run_with_admin.py, never sourced by
# this shell, so a password's punctuation is never interpreted or echoed.
#
# Chapters (the administrator credential each one keeps on this computer):
#   test        the repository's .env (crm-test)
#   boston      ~/.config/cbm-boston/boston.env
#   lakeside    ~/.config/cbm-lakeside/lakeside.env
#   production  no credential here — run the applier from inside its web
#               console instead (scripts/apply_crm_plan.py, top of file).
set -euo pipefail
cd "$(dirname "$0")/.."
chapter="${1:-}"; plan="${2:-}"; fingerprint="${3:-}"
usage() { echo "usage: scripts/apply_plan.sh <test|boston|lakeside> <plan.json> [fingerprint]" >&2; exit 64; }
[ -n "$chapter" ] && [ -n "$plan" ] || usage
case "$chapter" in
  test)       envfile=".env" ;;
  boston)     envfile="$HOME/.config/cbm-boston/boston.env" ;;
  lakeside)   envfile="$HOME/.config/cbm-lakeside/lakeside.env" ;;
  production) echo "production keeps its administrator credential only inside its web container;" >&2
              echo "run scripts/apply_crm_plan.py from 'doctl apps console <app-id> web' (see its docstring)." >&2; exit 64 ;;
  *)          echo "unknown chapter '$chapter'" >&2; usage ;;
esac
[ -r "$envfile" ] || { echo "no credential file at $envfile" >&2; exit 66; }
[ -r "$plan" ]    || { echo "no such plan: $plan" >&2; exit 66; }
flags=()
if [ -n "$fingerprint" ]; then
  flags=(--apply --expect "$fingerprint")
  [ "$chapter" != test ] && flags+=(--production)
fi
echo "== $chapter: apply_crm_plan.py $(basename "$plan") ${flags[*]:-(dry run)}" >&2
exec uv run python scripts/run_with_admin.py --env "$envfile" scripts/apply_crm_plan.py "$plan" "${flags[@]}"
