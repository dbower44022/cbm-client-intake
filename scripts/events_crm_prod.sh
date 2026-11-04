#!/usr/bin/env bash
# The events CRM changes on PRODUCTION, one word per step (11-03-26).
# Runs INSIDE the deployed web container (doctl apps console <app-id> web),
# the only place production's administrator credential exists.
#
#   bash scripts/events_crm_prod.sh <step>                dry run (changes nothing)
#   bash scripts/events_crm_prod.sh <step> apply          apply exactly that step
#   bash scripts/events_crm_prod.sh confirm apply <fp>    the plan, pinned to its dry run
#
# Steps, in order:
#   sponsorship  scripts/migrate_event_sponsorship_schema.py --carry-host
#                (many partners per event, the notice-campaign fields, and every
#                event's old single partner host copied into the new link)
#   hostcheck    scripts/check_partner_host_removed.py as the org-wide key
#                (after the old partnerHost link is removed by hand; no apply form)
#   confirm      scripts/plans/cevent-confirmation.json (the Seat Offered option)
#   templates    scripts/seed_event_templates.py (the eight event email templates;
#                one that exists is never touched)
#
# Exists because each full invocation is past the length a pasted console
# line survives (the same reason as scripts/prospect_crm_prod.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
export ESPO_ADMIN_BASE="${ESPO_ADMIN_BASE:-${ESPO_BASE_URL:-}}"
export ESPO_ADMIN_USER="${ESPO_ADMIN_USER:-${ESPO_PROVISION_USERNAME:-}}"
export ESPO_ADMIN_PASS="${ESPO_ADMIN_PASS:-${ESPO_PROVISION_PASSWORD:-}}"
export PYTHONPATH="$PWD"
PY="${PY:-.venv/bin/python}"
step="${1:-}"; mode="${2:-dry}"; fp="${3:-}"
if [ "$mode" != "dry" ] && [ "$mode" != "apply" ]; then
  echo "the second word is 'apply' or nothing" >&2; exit 64
fi
flag=""; [ "$mode" = apply ] && flag="--apply"
case "$step" in
  sponsorship) exec "$PY" scripts/migrate_event_sponsorship_schema.py --carry-host $flag ;;
  hostcheck)   exec "$PY" scripts/check_partner_host_removed.py --base "$ESPO_BASE_URL" --key "$ESPO_API_KEY" ;;
  confirm)
    if [ "$mode" = apply ]; then
      [ -n "$fp" ] || { echo "give the 12-character fingerprint the dry run printed" >&2; exit 64; }
      exec "$PY" scripts/apply_crm_plan.py scripts/plans/cevent-confirmation.json --apply --production --expect "$fp"
    fi
    exec "$PY" scripts/apply_crm_plan.py scripts/plans/cevent-confirmation.json ;;
  templates)   exec "$PY" scripts/seed_event_templates.py $flag ;;
  *) echo "usage: bash scripts/events_crm_prod.sh <sponsorship|hostcheck|confirm|templates> [apply [fingerprint]]" >&2; exit 64 ;;
esac
