#!/usr/bin/env bash
# Business Evaluation on the Business Mentors Association's test system
# (phase 5 check, Doug's choice 11-15-26: test there, not on crm-test).
#
#   ./scripts/evaluation_bma.sh check            # dry runs: both CRM plans and the role grants
#   ./scripts/evaluation_bma.sh apply            # apply them (changes the Association's CRM)
#   ./scripts/evaluation_bma.sh samples <engagement id>   # sample drafts, Finance and Marketing
#
# Credentials come from ~/.config/cbm-bma/bma.env, read by a parser and never
# echoed. "samples" uses this computer's database container
# (cbm-client-intake-db-1, migrated to head first) and the Anthropic key in .env.
# The fingerprints are the plans as reviewed on 11-15-26; a changed plan is refused.
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE="$HOME/.config/cbm-bma/bma.env"
RUN=(env PYTHONPATH=. uv run python)
BE_PLAN=crm-plans/business-evaluation.json
BE_PRINT=89d89d28b53b
AI_PLAN=crm-plans/action-item.json
AI_PRINT=5bf3e2de43a8

admin() { "${RUN[@]}" scripts/run_with_admin.py --env "$ENV_FILE" "$@"; }

case "${1:-}" in
  check)
    # Before "apply", the action item plan and the role grants report that
    # CBusinessEvaluation is missing: expected, the first plan adds it.
    admin scripts/apply_crm_plan.py "$BE_PLAN" || true
    admin scripts/apply_crm_plan.py "$AI_PLAN" || true
    admin scripts/migrate_evaluation_roles.py || true
    ;;
  apply)
    admin scripts/apply_crm_plan.py "$BE_PLAN" --apply --production --expect "$BE_PRINT"
    admin scripts/apply_crm_plan.py "$AI_PLAN" --apply --production --expect "$AI_PRINT"
    admin scripts/migrate_evaluation_roles.py --apply
    ;;
  samples)
    [ -n "${2:-}" ] || { echo "Give the engagement id." >&2; exit 2; }
    export DATABASE_URL="postgresql+asyncpg://cbm:cbm@localhost:5432/cbm_intake"
    uv run alembic upgrade head
    "${RUN[@]}" scripts/evaluation_sample_reports.py "$2" --env-file "$ENV_FILE"
    ;;
  *)
    sed -n '2,12p' "$0"; exit 2 ;;
esac
