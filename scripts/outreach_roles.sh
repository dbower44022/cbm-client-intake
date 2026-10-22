#!/bin/sh
# Run scripts/migrate_outreach_roles.py with the admin credentials from .env
# (crm-test by default). A short wrapper so the command fits one terminal line.
#   scripts/outreach_roles.sh           # dry run
#   scripts/outreach_roles.sh --apply   # apply
cd "$(dirname "$0")/.." || exit 1
PYTHONPATH=. exec uv run python scripts/run_with_admin.py \
  scripts/migrate_outreach_roles.py "$@"
