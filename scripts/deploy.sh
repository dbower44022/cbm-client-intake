#!/usr/bin/env bash
#
# Deploy cbm-client-intake to DigitalOcean App Platform from .do/app.yaml.
#
# Idempotent: creates the App if one named "$APP_NAME" does not exist, otherwise
# updates it in place. Deploys in DRY-RUN by default (ESPO_DRY_RUN=true in the
# spec) — no EspoCRM writes. To go live, set the EspoCRM env vars as encrypted
# App-level variables (see DEPLOYMENT.md "Going live"); this script never
# handles secrets.
#
# Prerequisites: doctl installed + authenticated, and the GitHub repo connected
# to your DO account once via the console (see DEPLOYMENT.md "Prerequisites").
#
# Usage:  ./scripts/deploy.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC="$REPO_ROOT/.do/app.yaml"
APP_NAME="cbm-client-intake"

die() { echo "ERROR: $*" >&2; exit 1; }

# --- Prerequisites ---------------------------------------------------------
command -v doctl >/dev/null 2>&1 \
  || die "doctl not installed. See DEPLOYMENT.md (Prerequisites)."
doctl account get >/dev/null 2>&1 \
  || die "doctl not authenticated. Run: doctl auth init"
[ -f "$SPEC" ] || die "App spec not found at $SPEC"

echo "==> Validating app spec"
doctl apps spec validate "$SPEC" >/dev/null \
  || die "Spec validation failed for $SPEC"

# --- Find existing app by name --------------------------------------------
echo "==> Looking for an existing app named '$APP_NAME'"
APP_ID="$(doctl apps list --no-header --format ID,Spec.Name \
  | awk -v n="$APP_NAME" '$2 == n { print $1 }' | head -n1)"

# --- Create or update ------------------------------------------------------
if [ -z "$APP_ID" ]; then
  echo "==> No existing app — creating (this also runs the first deploy)"
  # If this fails with a GitHub error, connect the repo once in the DO console:
  # Apps -> Create App -> GitHub -> authorize dbower44022/cbm-client-intake.
  APP_ID="$(doctl apps create --spec "$SPEC" --no-header --format ID --wait)"
  echo "==> Created app: $APP_ID"
else
  echo "==> Found app $APP_ID — updating from spec and redeploying"
  doctl apps update "$APP_ID" --spec "$SPEC" --wait >/dev/null
fi

# --- Report + verify -------------------------------------------------------
URL="$(doctl apps get "$APP_ID" --no-header --format DefaultIngress)"
[ -n "$URL" ] || die "Deployed, but could not read the app URL. Check the DO console."

echo "==> App URL: $URL"
echo "==> Verifying /healthz"
if curl -fsS --max-time 20 "$URL/healthz"; then
  echo
  echo "==> Deploy OK."
  echo "    Forms:  $URL/client-intake/   $URL/volunteer/"
  echo "    (Confirm \"dryRun\" above: true = no EspoCRM writes; flip per DEPLOYMENT.md.)"
else
  die "Health check failed at $URL/healthz — inspect: doctl apps logs $APP_ID --type run"
fi
