#!/usr/bin/env bash
# The partner and funder association CRM change on BOSTON, from the build
# computer, one word per step:
#
#   scripts/partner_association_boston.sh plan          dry run of the plan
#   scripts/partner_association_boston.sh plan-apply F  apply it; F = the fingerprint the dry run printed
#   scripts/partner_association_boston.sh roles         dry run of the five role grants
#   scripts/partner_association_boston.sh roles-apply   apply them and rebuild
#
# The administrator credential is ~/.config/cbm-boston/boston.env, PARSED by
# run_with_admin.py, never sourced, so a password's punctuation is never
# interpreted or echoed. Additive and safe ahead of Boston's release: the
# application feature-detects the entity. (partner-association-crm-handoff.md)
# NOT YET: Boston has no CProspect (the outreach CRM change is owed there),
# so the plan's lead link cannot be built — the dry run says so (10-29-26).
set -euo pipefail
cd "$(dirname "$0")/.."
env_file="$HOME/.config/cbm-boston/boston.env"
[ -r "$env_file" ] || { echo "no credential file at $env_file" >&2; exit 66; }
plan=scripts/plans/cpartner-association.json
roles=(uv run python scripts/run_with_admin.py --env "$env_file" scripts/migrate_partner_association_roles.py)
case "${1:-}" in
  plan)        exec scripts/apply_plan.sh boston "$plan" ;;
  plan-apply)  exec scripts/apply_plan.sh boston "$plan" "${2:?give the fingerprint the dry run printed}" ;;
  roles)       exec "${roles[@]}" ;;
  roles-apply) exec "${roles[@]}" --apply ;;
  *) sed -n '2,8p' "$0"; exit 2 ;;
esac
