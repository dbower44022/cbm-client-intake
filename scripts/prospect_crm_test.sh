#!/usr/bin/env bash
# The prospect-marketing Phase 1 CRM change on crm-test, one word per step.
#
#   scripts/prospect_crm_test.sh sms        apply scripts/plans/contact-sms-opt-in.json  (fingerprint 0bc7219ab932)
#   scripts/prospect_crm_test.sh outreach   apply scripts/plans/coutreach-entities.json  (fingerprint 6b29c8928dcf)
#   scripts/prospect_crm_test.sh roles      scripts/migrate_outreach_roles.py --apply
#   scripts/prospect_crm_test.sh notes      COutreachCampaign.description text -> wysiwyg, on the droplet
#   scripts/prospect_crm_test.sh receipt    apply scripts/plans/cintake-submission-prospect-response.json (fingerprint cb685b7372b1)
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
  *) echo "usage: scripts/prospect_crm_test.sh <sms|outreach|roles|notes|receipt>" >&2; exit 64 ;;
esac
