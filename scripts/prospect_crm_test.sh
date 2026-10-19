#!/usr/bin/env bash
# The prospect-marketing Phase 1 CRM change on crm-test, one word per step.
#
#   scripts/prospect_crm_test.sh sms        apply scripts/plans/contact-sms-opt-in.json  (fingerprint 0bc7219ab932)
#   scripts/prospect_crm_test.sh outreach   apply scripts/plans/coutreach-entities.json  (fingerprint 6b29c8928dcf)
#   scripts/prospect_crm_test.sh roles      scripts/migrate_outreach_roles.py --apply
#   scripts/prospect_crm_test.sh notes      COutreachCampaign.description text -> wysiwyg, on the droplet
#   scripts/prospect_crm_test.sh receipt    apply scripts/plans/cintake-submission-prospect-response.json (fingerprint cb685b7372b1)
#   scripts/prospect_crm_test.sh appfields  apply scripts/plans/coutreach-campaign-app-fields.json (fingerprint 965d932407f3; ruling 40)
#   scripts/prospect_crm_test.sh smstext    apply scripts/plans/coutreach-sms-message.json (fingerprint 7a68865149b4; Phase 4, ruling 39)
#   scripts/prospect_crm_test.sh leadmodel  apply scripts/plans/coutreach-lead-model.json (fingerprint 6e228dbb7d33; rulings 41-50)
#   scripts/prospect_crm_test.sh leadlabels scripts/relabel_outreach_lead.py --apply (ruling 50)
#   scripts/prospect_crm_test.sh touchpos   apply scripts/plans/coutreach-touch-positions.json (fingerprint 6c2e1d42af30; lead-model code release)
#   scripts/prospect_crm_test.sh leadlayouts scripts/apply_lead_layouts.py --apply (handoff § 7, with the code release)
#   scripts/prospect_crm_test.sh leadmove   scripts/migrate_lead_model_values.py --apply (handoff § 5, with the code release)
#
# Exists for the same reason as scripts/on_crm.sh and scripts/apply_plan.sh: each
# full invocation is far past the one-line limit a pasted command survives, and
# the fingerprints are pinned here so the apply is exactly the dry run that was
# reviewed (coutreach-entities-crm-handoff.md § 2, contact-sms-opt-in-crm-handoff.md
# § 2). crm-test only — production runs the applier from inside its web
# container, Boston through scripts/apply_plan.sh boston. The credential file is
# parsed by run_with_admin.py, never sourced by this shell.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  sms)      exec scripts/apply_plan.sh test scripts/plans/contact-sms-opt-in.json 0bc7219ab932 ;;
  outreach) exec scripts/apply_plan.sh test scripts/plans/coutreach-entities.json 6b29c8928dcf ;;
  roles)    exec uv run python scripts/run_with_admin.py scripts/migrate_outreach_roles.py --apply ;;
  notes)    exec scripts/on_crm.sh test scripts/convert_notes_wysiwyg.sh COutreachCampaign ;;
  receipt)  exec scripts/apply_plan.sh test scripts/plans/cintake-submission-prospect-response.json cb685b7372b1 ;;
  appfields) exec scripts/apply_plan.sh test scripts/plans/coutreach-campaign-app-fields.json 965d932407f3 ;;
  smstext)  exec scripts/apply_plan.sh test scripts/plans/coutreach-sms-message.json 7a68865149b4 ;;
  leadmodel) exec scripts/apply_plan.sh test scripts/plans/coutreach-lead-model.json 6e228dbb7d33 ;;
  leadlabels) exec uv run python scripts/run_with_admin.py scripts/relabel_outreach_lead.py --apply ;;
  touchpos) exec scripts/apply_plan.sh test scripts/plans/coutreach-touch-positions.json 6c2e1d42af30 ;;
  leadlayouts) exec uv run python scripts/run_with_admin.py scripts/apply_lead_layouts.py --apply ;;
  leadmove) exec uv run python scripts/migrate_lead_model_values.py --apply ;;
  *) echo "usage: scripts/prospect_crm_test.sh <sms|outreach|roles|notes|receipt|smstext|appfields|leadmodel|leadlabels|touchpos|leadlayouts|leadmove>" >&2; exit 64 ;;
esac
