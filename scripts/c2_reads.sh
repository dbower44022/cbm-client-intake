#!/usr/bin/env bash
# Read-only: the two C2 checks in production's WEB container, output printed
# here (mentor login integrity plan, step 4c). Run from the repository folder:
#
#   scripts/c2_reads.sh
#
# 1. scripts/measure_signin_log_read.py — timings and counts only.
# 2. scripts/integrity_report.py --live — the login-fault backlog; records
#    nothing.
# Uses doctl's console through a pseudo-terminal (do-app-console-scripting
# memory); writes nothing to the CRM or the application's database.
set -eu
APP=aa1ddf69-f359-4b53-91ba-035cbed7bd53   # production
CMD='cd /app; echo C2-BEGIN; echo C2-BEGIN; .venv/bin/python scripts/measure_signin_log_read.py; echo; echo ====; .venv/bin/python scripts/integrity_report.py --live; echo C2-END; exit'
OUT=$(mktemp)
echo "Connecting to production's web container (about 3 minutes)…"
(printf '%s\n' "$CMD"; sleep 170) \
  | timeout 190 script -qec "doctl apps console $APP web" /dev/null \
  | tr -d '\r' > "$OUT" || true
# Print between the markers (the begin marker is printed twice because the
# first output line is often eaten; either copy starts the print).
awk '/^C2-BEGIN$/{p=1; next} /^C2-END$/{p=0} p' "$OUT"
if ! grep -q '^C2-END$' "$OUT"; then
  echo "--- the run did not finish; the last lines received:"
  tail -20 "$OUT"
fi
rm -f "$OUT"
