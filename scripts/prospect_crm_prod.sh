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
#   appfields  scripts/plans/coutreach-campaign-app-fields.json      fingerprint 965d932407f3 (ruling 40)
#   smstext    scripts/plans/coutreach-sms-message.json              fingerprint 7a68865149b4 (Phase 4, ruling 39)
#   roles      scripts/migrate_outreach_roles.py (merge-only; Phase 3 added the Mentor Role's two; ruling 69 the stream grant)
#   actionlog  scripts/migrate_actionlog_record_entities.py (CActionLog.record may point at campaigns, leads, call records)
#   labels     scripts/relabel_outreach_campaign.py ("Outreach Campaign", ruling 35)
#   ui         scripts/apply_outreach_ui.py (tab list, detail and list layouts)
#   verify     scripts/apply_outreach_ui.py --verify (org-wide key; no apply form)
#
# The go-live words (11-01-26; fingerprints read on crm-test — a production
# dry run that differs makes the apply refuse, and nothing changes):
#   leadmodel   scripts/plans/coutreach-lead-model.json         fingerprint 6e228dbb7d33
#   touchpos    scripts/plans/coutreach-touch-positions.json    fingerprint 6c2e1d42af30
#   leadlabels  scripts/relabel_outreach_lead.py ("Outreach Lead", ruling 50)
#   leadlayouts scripts/apply_lead_layouts.py (needs leadmodel first)
#   leadmove    scripts/migrate_lead_model_values.py (org-wide key; ruling 45)
#   funders     scripts/plans/coutreach-funders.json            fingerprint 4658d1450804
#   industry    scripts/plans/cprospect-industry.json           fingerprint 82ec87c36dce
#   industryopts  prints Account.cIndustrySector to compare with that plan
#   funderstatus  scripts/plans/csponsor-funder-status.json     fingerprint 84636d15191f
#   closedate   scripts/plans/cengagement-close-date-writable.json fingerprint c80d9070da1d
#   leadcode    scripts/plans/lead-code.json                    fingerprint bec909277859
#   redesign    scripts/plans/marketing-redesign.json           fingerprint 6bb03652454a
#   opens       scripts/plans/coutreach-touch-opens.json        fingerprint 50cae75c1274
#   fitscore    scripts/plans/cprospect-fit-score.json          fingerprint 8e57af53eef5
#   relabelco   scripts/relabel_info_request_companies.py (org-wide key; ruling 34)
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
  appfields) plan scripts/plans/coutreach-campaign-app-fields.json 965d932407f3 ;;
  smstext)  plan scripts/plans/coutreach-sms-message.json 7a68865149b4 ;;
  roles)    exec "$PY" scripts/migrate_outreach_roles.py $flag ;;
  actionlog) exec "$PY" scripts/migrate_actionlog_record_entities.py $flag ;;
  labels)   exec "$PY" scripts/relabel_outreach_campaign.py $flag ;;
  ui)       exec "$PY" scripts/apply_outreach_ui.py $flag ;;
  verify)   exec "$PY" scripts/apply_outreach_ui.py --verify ;;
  leadmodel) plan scripts/plans/coutreach-lead-model.json 6e228dbb7d33 ;;
  touchpos) plan scripts/plans/coutreach-touch-positions.json 6c2e1d42af30 ;;
  leadlabels) exec "$PY" scripts/relabel_outreach_lead.py $flag ;;
  leadlayouts) exec "$PY" scripts/apply_lead_layouts.py $flag ;;
  leadmove) exec "$PY" scripts/migrate_lead_model_values.py $flag ;;
  funders)  plan scripts/plans/coutreach-funders.json 4658d1450804 ;;
  industry) plan scripts/plans/cprospect-industry.json 82ec87c36dce ;;
  industryopts) exec "$PY" scripts/espo_admin.py metadata entityDefs.Account.fields.cIndustrySector.options ;;
  funderstatus) plan scripts/plans/csponsor-funder-status.json 84636d15191f ;;
  closedate) plan scripts/plans/cengagement-close-date-writable.json c80d9070da1d ;;
  leadcode) plan scripts/plans/lead-code.json bec909277859 ;;
  redesign) plan scripts/plans/marketing-redesign.json 6bb03652454a ;;
  opens)    plan scripts/plans/coutreach-touch-opens.json 50cae75c1274 ;;
  fitscore) plan scripts/plans/cprospect-fit-score.json 8e57af53eef5 ;;
  relabelco) exec "$PY" scripts/relabel_info_request_companies.py $flag ;;
  *) echo "usage: bash scripts/prospect_crm_prod.sh <step> [apply] — the steps are listed at the top of this file" >&2; exit 64 ;;
esac
