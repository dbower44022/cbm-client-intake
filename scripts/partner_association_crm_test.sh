#!/usr/bin/env bash
# The partner and funder association CRM change on crm-test, one word per step.
#
#   scripts/partner_association_crm_test.sh plan    apply scripts/plans/cpartner-association.json (fingerprint 8dd9d9264170)
#   scripts/partner_association_crm_test.sh roles   scripts/migrate_partner_association_roles.py --apply
#
# Exists because the full invocation is past the one-line limit a pasted
# command survives, and the fingerprint is pinned here so the apply is exactly
# the dry run that was reviewed (partner-association-crm-handoff.md § 2).
# crm-test only: production runs the applier from inside its web container,
# Boston through scripts/apply_plan.sh boston.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  plan)  exec scripts/apply_plan.sh test scripts/plans/cpartner-association.json 8dd9d9264170 ;;
  roles) exec uv run python scripts/run_with_admin.py scripts/migrate_partner_association_roles.py --apply ;;
  *) sed -n '2,6p' "$0"; exit 2 ;;
esac
