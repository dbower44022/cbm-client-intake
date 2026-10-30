#!/usr/bin/env bash
# Marketing Management's CRM change on BOSTON (production parity: Phase 1-4),
# one word per step, from the build computer. Every step is a DRY RUN unless
# told to apply:
#
#   plan steps     scripts/prospect_crm_boston.sh <step>                dry run
#                  scripts/prospect_crm_boston.sh <step> <fingerprint>  apply exactly that dry run
#       sms        contact-sms-opt-in.json                   (Contact.cSmsOptIn)
#       outreach   coutreach-entities.json                   (the three outreach entities, 17 links)
#       receipt    cintake-submission-prospect-response.json (the receipt's form option)
#       appfields  coutreach-campaign-app-fields.json        (ruling 40; after outreach)
#       smstext    coutreach-sms-message.json                (ruling 39; after outreach)
#   script steps   scripts/prospect_crm_boston.sh <step>                dry run
#                  scripts/prospect_crm_boston.sh <step> apply          apply
#       ui         apply_outreach_ui.py                      (tab list and layouts)
#       labels     relabel_outreach_campaign.py              (ruling 35)
#       actionlog  migrate_actionlog_record_entities.py      (action-history record types)
#       roles      migrate_outreach_roles.py                 (the role grants; LAST)
#   droplet step   scripts/prospect_crm_boston.sh notes                 (no dry run: writes, keeps a backup)
#
# Order and reasons: the Boston step page and coutreach-entities-crm-handoff.md.
# The apply takes the fingerprint its own dry run printed, so it applies exactly
# the work that dry run showed; a step blocked on an earlier one prints the
# empty-plan fingerprint 4f53cda18c2b and a FAILED line — run that earlier step
# first. The credential (~/.config/cbm-boston/boston.env) is parsed by
# run_with_admin.py, never sourced by this shell.
set -euo pipefail
cd "$(dirname "$0")/.."
env_file="$HOME/.config/cbm-boston/boston.env"
[ -r "$env_file" ] || { echo "no credential file at $env_file" >&2; exit 66; }
step="${1:-}"; arg="${2:-}"

plan() {  # plan <file>: dry run, or apply with the given fingerprint
  if [ -n "$arg" ]; then exec scripts/apply_plan.sh boston "scripts/plans/$1" "$arg"
  else exec scripts/apply_plan.sh boston "scripts/plans/$1"; fi
}
script() {  # script <file>: dry run, or --apply when the second word is "apply"
  local flags=()
  if [ "$arg" = "apply" ]; then flags=(--apply)
  elif [ -n "$arg" ]; then echo "the second word may only be 'apply'" >&2; exit 64; fi
  PYTHONPATH=. exec uv run python scripts/run_with_admin.py --env "$env_file" "scripts/$1" "${flags[@]}"
}

case "$step" in
  sms)       plan contact-sms-opt-in.json ;;
  outreach)  plan coutreach-entities.json ;;
  receipt)   plan cintake-submission-prospect-response.json ;;
  appfields) plan coutreach-campaign-app-fields.json ;;
  smstext)   plan coutreach-sms-message.json ;;
  ui)        script apply_outreach_ui.py ;;
  labels)    script relabel_outreach_campaign.py ;;
  actionlog) script migrate_actionlog_record_entities.py ;;
  roles)     script migrate_outreach_roles.py ;;
  notes)     exec scripts/on_crm.sh boston scripts/convert_notes_wysiwyg.sh COutreachCampaign ;;
  *) sed -n '2,22p' "$0"; exit 2 ;;
esac
