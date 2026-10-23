#!/bin/sh
# Run scripts/migrate_outreach_roles.py with admin credentials (crm-test from
# .env by default). A short wrapper so the command fits one terminal line.
#   scripts/outreach_roles.sh                  # crm-test, dry run
#   scripts/outreach_roles.sh --apply          # crm-test, apply
#   scripts/outreach_roles.sh boston           # Boston, dry run
#   scripts/outreach_roles.sh boston --apply   # Boston, apply
# Production runs inside its web container: scripts/prospect_crm_prod.sh roles.
cd "$(dirname "$0")/.." || exit 1
if [ "${1:-}" = "boston" ]; then
  shift
  set -- --env "$HOME/.config/cbm-boston/boston.env" scripts/migrate_outreach_roles.py "$@"
else
  set -- scripts/migrate_outreach_roles.py "$@"
fi
PYTHONPATH=. exec uv run python scripts/run_with_admin.py "$@"
