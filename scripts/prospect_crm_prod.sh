#!/usr/bin/env bash
# The prospect-marketing Phase 1 CRM change on PRODUCTION, one word per step.
# Runs INSIDE the deployed web container (doctl apps console <app-id> web),
# the only place production's administrator credential exists.
#
#   bash scripts/prospect_crm_prod.sh <step>            dry run (changes nothing)
#   bash scripts/prospect_crm_prod.sh <step> apply      apply exactly that step
#
# Steps, in order (coutreach-entities-crm-handoff.md § 7):
#   whoami     confirm the admin credential (no apply form)
#   sms        scripts/plans/contact-sms-opt-in.json                 fingerprint 0bc7219ab932
#   outreach   scripts/plans/coutreach-entities.json                 fingerprint 6b29c8928dcf
#   receipt    scripts/plans/cintake-submission-prospect-response.json fingerprint cb685b7372b1
#   roles      scripts/migrate_outreach_roles.py (seven grants, merge-only)
#   labels     scripts/relabel_outreach_campaign.py ("Outreach Campaign", ruling 35)
#   ui         scripts/apply_outreach_ui.py (tab list, detail and list layouts)
#   verify     scripts/apply_outreach_ui.py --verify (org-wide key; no apply form)
#
# Exists because each full invocation is past the length a pasted console line
# survives, and so the fingerprints are pinned: the applier refuses an apply
# whose plan moved since the dry run. The notes conversion is NOT here — it runs
# on the CRM droplet from the build computer (scripts/on_crm.sh production …).
set -euo pipefail
cd "$(dirname "$0")/.."
export ESPO_ADMIN_BASE="${ESPO_ADMIN_BASE:-${ESPO_BASE_URL:-}}"
export ESPO_ADMIN_USER="${ESPO_ADMIN_USER:-${ESPO_PROVISION_USERNAME:-}}"
export ESPO_ADMIN_PASS="${ESPO_ADMIN_PASS:-${ESPO_PROVISION_PASSWORD:-}}"
export PYTHONPATH="$PWD"
PY="${PY:-.venv/bin/python}"
step="${1:-}"; mode="${2:-dry}"
if [ "$mode" != "dry" ] && [ "$mode" != "apply" ]; then
  echo "the second word is 'apply' or nothing" >&2; exit 64
fi
plan() {
  if [ "$mode" = apply ]; then
    exec "$PY" scripts/apply_crm_plan.py "$1" --apply --production --expect "$2"
  fi
  exec "$PY" scripts/apply_crm_plan.py "$1"
}
flag=""; [ "$mode" = apply ] && flag="--apply"
case "$step" in
  whoami)   exec "$PY" scripts/espo_admin.py whoami ;;
  sms)      plan scripts/plans/contact-sms-opt-in.json 0bc7219ab932 ;;
  outreach) plan scripts/plans/coutreach-entities.json 6b29c8928dcf ;;
  receipt)  plan scripts/plans/cintake-submission-prospect-response.json cb685b7372b1 ;;
  roles)    exec "$PY" scripts/migrate_outreach_roles.py $flag ;;
  labels)   exec "$PY" scripts/relabel_outreach_campaign.py $flag ;;
  ui)       exec "$PY" scripts/apply_outreach_ui.py $flag ;;
  verify)   exec "$PY" scripts/apply_outreach_ui.py --verify ;;
  *) echo "usage: bash scripts/prospect_crm_prod.sh <whoami|sms|outreach|receipt|roles|labels|ui|verify> [apply]" >&2; exit 64 ;;
esac
