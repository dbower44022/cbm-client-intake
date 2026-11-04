#!/usr/bin/env bash
# Re-encrypt every stored secret with the newest APP_ENCRYPTION_KEY, INSIDE the
# deployment's web container (OPEN-ITEMS #33):
#
#   scripts/rotate_encryption_key.sh          dry run: counts, changes nothing
#   scripts/rotate_encryption_key.sh apply    re-encrypt, one transaction
#
# APP_ENCRYPTION_KEY must hold NEW,OLD while this runs. Never prints a secret.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  "")    PYTHONPATH=. exec .venv/bin/python scripts/rotate_encryption_key.py ;;
  apply) PYTHONPATH=. exec .venv/bin/python scripts/rotate_encryption_key.py --apply ;;
  *) sed -n '2,8p' "$0"; exit 2 ;;
esac
