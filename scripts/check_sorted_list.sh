#!/usr/bin/env bash
# Check a CRM's multi-column sorted list endpoint (read-only), one word:
#
#   scripts/check_sorted_list.sh test        crm-test, from the build computer
#   scripts/check_sorted_list.sh lakeside    Lakeside, from the build computer
#   scripts/check_sorted_list.sh boston      Boston, from the build computer
#   scripts/check_sorted_list.sh production  INSIDE the production web container
#
# The administrator credential is parsed from the chapter's file (never
# sourced) or, in a container, taken from its own environment; never printed.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  test)       exec uv run python scripts/run_with_admin.py scripts/check_sorted_list.py ;;
  lakeside)   exec uv run python scripts/run_with_admin.py --env "$HOME/.config/cbm-lakeside/lakeside.env" scripts/check_sorted_list.py ;;
  boston)     exec uv run python scripts/run_with_admin.py --env "$HOME/.config/cbm-boston/boston.env" scripts/check_sorted_list.py ;;
  production)
    export ESPO_ADMIN_BASE="${ESPO_BASE_URL:?run this in the production web container}"
    export ESPO_ADMIN_USER="${ESPO_PROVISION_USERNAME:?run this in the production web container}"
    export ESPO_ADMIN_PASS="${ESPO_PROVISION_PASSWORD:?run this in the production web container}"
    PYTHONPATH=. exec .venv/bin/python scripts/check_sorted_list.py ;;
  *) sed -n '2,8p' "$0"; exit 2 ;;
esac
