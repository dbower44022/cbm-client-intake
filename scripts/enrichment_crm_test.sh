#!/usr/bin/env bash
# The lead enrichment CRM changes on crm-test, one word per step.
#
#   scripts/enrichment_crm_test.sh fitscore   apply scripts/plans/cprospect-fit-score.json (fingerprint 8e57af53eef5)
#
# Exists because the full invocation is past the one-line limit a pasted
# command survives, and the fingerprint is pinned here so the apply is exactly
# the dry run that was reviewed (lead-fit-score-crm-handoff.md § 2). crm-test
# only: production runs the applier from inside its web container, Boston
# through scripts/apply_plan.sh boston.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  fitscore) exec scripts/apply_plan.sh test scripts/plans/cprospect-fit-score.json 8e57af53eef5 ;;
  *) sed -n '2,5p' "$0"; exit 2 ;;
esac
