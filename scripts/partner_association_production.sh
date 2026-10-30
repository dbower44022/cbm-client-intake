#!/usr/bin/env bash
# The partner and funder association CRM change on PRODUCTION, run from
# INSIDE the production web container (the only place its administrator
# credential exists), one word per step:
#
#   scripts/partner_association_production.sh plan          dry run of the plan
#   scripts/partner_association_production.sh plan-apply F  apply it; F = the fingerprint the dry run printed
#   scripts/partner_association_production.sh roles         dry run of the five role grants
#   scripts/partner_association_production.sh roles-apply   apply them and rebuild
#
# Exists because the full invocations are past the one-line limit a console
# paste survives. The apply takes the fingerprint its own dry run printed, so
# it applies exactly the work that dry run showed (partner-association-crm-handoff.md).
# The credential is read from the container's own environment and never
# printed.
set -euo pipefail
cd "$(dirname "$0")/.."
export ESPO_ADMIN_BASE="${ESPO_BASE_URL:?ESPO_BASE_URL is not set — run this in the web container}"
export ESPO_ADMIN_USER="${ESPO_PROVISION_USERNAME:?ESPO_PROVISION_USERNAME is not set — run this in the web container}"
export ESPO_ADMIN_PASS="${ESPO_PROVISION_PASSWORD:?ESPO_PROVISION_PASSWORD is not set — run this in the web container}"
export PYTHONPATH=.
py=.venv/bin/python
plan=scripts/plans/cpartner-association.json
case "${1:-}" in
  plan)        exec "$py" scripts/apply_crm_plan.py "$plan" ;;
  plan-apply)  exec "$py" scripts/apply_crm_plan.py "$plan" --apply --production --expect "${2:?give the fingerprint the dry run printed}" ;;
  roles)       exec "$py" scripts/migrate_partner_association_roles.py ;;
  roles-apply) exec "$py" scripts/migrate_partner_association_roles.py --apply ;;
  *) sed -n '2,10p' "$0"; exit 2 ;;
esac
