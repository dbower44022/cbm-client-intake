#!/usr/bin/env bash
# Read-only: time the activity page's CRM-notes read in production's WEB
# container (mentor login integrity plan, step 6). Run from the repository
# folder once v0.313.0 is deployed:
#
#   scripts/note_reads.sh
#
# Uses doctl's console through a pseudo-terminal (do-app-console-scripting
# memory); writes nothing to the CRM or the application's database.
set -eu
APP=aa1ddf69-f359-4b53-91ba-035cbed7bd53   # production
CMD='cd /app; echo NR-BEGIN; echo NR-BEGIN; .venv/bin/python scripts/measure_note_read.py; echo NR-END; exit'
OUT=$(mktemp)
echo "Connecting to production's web container (about 2 minutes)…"
(printf '%s\n' "$CMD"; sleep 100) \
  | timeout 120 script -qec "doctl apps console $APP web" /dev/null \
  | tr -d '\r' > "$OUT" || true
awk '/^NR-BEGIN$/{p=1; next} /^NR-END$/{p=0} p' "$OUT"
if ! grep -q '^NR-END$' "$OUT"; then
  echo "--- the run did not finish; the last lines received:"
  tail -20 "$OUT"
fi
rm -f "$OUT"
