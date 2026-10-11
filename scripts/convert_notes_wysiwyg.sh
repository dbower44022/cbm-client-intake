#!/usr/bin/env bash
# Convert a notes field from text to wysiwyg on a dockerized EspoCRM droplet.
#
# Runs ON the droplet (the CRM lives in the `espocrm` container). From the
# repository root, one line per instance:
#
#   ssh root@<droplet> bash -s < scripts/convert_notes_wysiwyg.sh
#
# Default: CSponsorProfile.description (Funder Notes) and
# CEngagement.description (Client Administration's Notes column) — the two
# handoffs csponsorprofile-description-wysiwyg-crm-handoff.md and
# cengagement-description-wysiwyg-crm-handoff.md. Pass entity names to
# convert a different set: `bash -s CPartnerProfile < …`.
#
# Per entity: a timestamped backup beside the file, the one key flipped,
# the file rewritten in its 4-space style; a file with no `description`
# entry gains one; a missing or unparsable file aborts THAT entity and
# writes nothing. One rebuild at the end, then every type read back from
# the files. Idempotent — a field already wysiwyg is left as it is.
#
# Entity Manager cannot change an existing field's type; text -> wysiwyg
# keeps the same TEXT column, so no data migration and no data loss.
# Not between 04:00 and 05:00 UTC on crm-test (the reset window).
set -u
CONTAINER="${CONTAINER:-espocrm}"
DIR=/var/www/html/custom/Espo/Custom/Resources/metadata/entityDefs
ENTITIES=("$@")
[ ${#ENTITIES[@]} -eq 0 ] && ENTITIES=(CSponsorProfile CEngagement)
STAMP=$(date -u +%Y%m%d-%H%M%S)
changed=0
for e in "${ENTITIES[@]}"; do
  echo "== $e"
  docker exec -u www-data "$CONTAINER" php -r '
    $p = $argv[1]; $stamp = $argv[2];
    if (!file_exists($p)) { fwrite(STDERR, "no file $p - nothing written\n"); exit(2); }
    $d = json_decode(file_get_contents($p), true);
    if (!is_array($d)) { fwrite(STDERR, "JSON parse failed - nothing written\n"); exit(2); }
    $cur = $d["fields"]["description"]["type"] ?? null;
    if ($cur === "wysiwyg") { echo "description already wysiwyg - unchanged\n"; exit(3); }
    copy($p, $p . ".bak-desc-wysiwyg-" . $stamp);
    $d["fields"]["description"]["type"] = "wysiwyg";
    file_put_contents($p, json_encode($d, JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE) . "\n");
    echo "description was ", json_encode($cur), ", now ", json_encode($d["fields"]["description"]), "\n";
    exit(0);
  ' "$DIR/$e.json" "$STAMP"
  rc=$?
  if [ $rc -eq 0 ]; then changed=1; elif [ $rc -ne 3 ]; then echo "   skipped (exit $rc)"; fi
done
if [ $changed -eq 1 ]; then
  echo "== rebuild"
  docker exec -u www-data "$CONTAINER" php command.php rebuild
fi
echo "== read back from the files"
for e in "${ENTITIES[@]}"; do
  printf '%s.description: ' "$e"
  docker exec -u www-data "$CONTAINER" php -r '
    $d = json_decode(@file_get_contents($argv[1]), true);
    echo json_encode($d["fields"]["description"] ?? null), "\n";
  ' "$DIR/$e.json"
done
