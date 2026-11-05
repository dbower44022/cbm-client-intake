#!/usr/bin/env bash
# Switch off the sign-in log for the CRM's key-based (API) users only:
# `'authApiUserLogDisabled' => true` in EspoCRM's configuration.
# Streamed to the droplet by scripts/on_crm.sh; nothing is copied there.
#
#   scripts/on_crm.sh test       scripts/set_authlog_switch.sh            # --check, the default: reads only
#   scripts/on_crm.sh test       scripts/set_authlog_switch.sh --apply    # sets it to true
#   scripts/on_crm.sh test       scripts/set_authlog_switch.sh --off      # the undo: sets it to false
#   scripts/on_crm.sh production scripts/set_authlog_switch.sh --apply
#   scripts/on_crm.sh boston     scripts/set_authlog_switch.sh --apply
#
# Handoff: crm-history-settings-crm-handoff.md § 2. Plan:
# prds/mentor-login-integrity-plan.md § 4.6.
#
# WHICH FILE. data/config-internal.php, not data/config.php. Read from the
# EspoCRM source 11-05-26 (9.3.10 on crm-test; 9.3.10 and 10.0.10 images,
# identical in all three points):
#   - authApiUserLogDisabled is listed in `systemItems`
#     (application/Espo/Resources/defaults/systemConfig.php);
#   - ConfigWriter::save() sends every system item to config-internal.php
#     (InternalConfigHelper::isParamForInternalConfig), so that is where
#     EspoCRM itself would put it, and a later save by EspoCRM keeps it there;
#   - Config merges config.php, then config-internal.php, then the two
#     override files, then state.php — a value in config-internal.php beats
#     one in config.php, never the reverse.
# Authentication.php skips the sign-in log row only when the user is an API
# user AND authApiUserLogDisabled is true. People's sign-ins stay logged.
#
# THE TRAP. `authLogDisabled` (no "ApiUser") switches off ALL sign-in
# logging, people included. This script never writes it; --check warns if
# it is set anywhere.
#
# WHAT --apply DOES, all as www-data inside the `espocrm` container:
#   1. builds a candidate copy with the one line added (or false -> true),
#   2. `php -l` on the candidate, and proves it holds exactly the old
#      settings plus this one — on any failure the live file is untouched,
#   3. backs the live file up beside itself (cp -p: owner and mode kept),
#   4. writes the candidate INTO the live file (same inode, so the owner,
#      uid 33, and the mode stay as they were),
#   5. `php -l` on the live file; a failure puts the backup back, exit 1,
#   6. reads the effective value back through PHP and prints the backup path.
# Restarts nothing. PHP reads the configuration files on each request.
#
# UNDO. `--off` — the same guarded edit, setting the value to false. Chosen
# over restoring the backup: EspoCRM rewrites config-internal.php itself
# (for example when a secret is regenerated), so an old backup can undo
# more than this one line. The backup is there for a broken file only.
#
# Exit: 0 done or nothing to do, 1 edit refused or rolled back, 64 usage.
set -eu

CONTAINER="${CONTAINER:-espocrm}"
WORKDIR="${WORKDIR:-/var/www/html}"
FILE="data/config-internal.php"
KEY="authApiUserLogDisabled"
STAMP="$(date -u +%Y%m%d-%H%M%S)"

mode="${1:---check}"
case "$mode" in
  --check) want="" ;;
  --apply) want="true" ;;
  --off)   want="false" ;;
  *) echo "usage: set_authlog_switch.sh [--check | --apply | --off]" >&2; exit 64 ;;
esac

#: Run a command inside the CRM container as www-data, in EspoCRM's root.
in_crm() { docker exec -u www-data -w "$WORKDIR" "$CONTAINER" "$@"; }

#: EspoCRM's own version: the CLI `version` command, else data/state.php.
espo_version() {
  local v
  v="$(in_crm php command.php version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
  [ -n "$v" ] || v="$(in_crm php -r '
    foreach (["data/state.php", "data/config-internal.php", "data/config.php"] as $f) {
      if (is_file($f)) { $c = include $f; if (is_array($c) && !empty($c["version"])) { echo $c["version"]; exit; } }
    }' 2>/dev/null || true)"
  echo "${v:-?}"
}

# Reads both keys from every configuration file, in EspoCRM's merge order,
# and prints the effective value. Exit 5 when authLogDisabled is effectively
# true (the everything-off key).
READ_PHP=$(cat <<'PHP'
$files = ['data/config.php', 'data/config-internal.php', 'data/config-override.php',
          'data/config-internal-override.php', 'data/state.php'];
$keys = ['authApiUserLogDisabled', 'authLogDisabled'];
$eff = [];
foreach ($files as $f) {
    if (!is_file($f)) { continue; }
    $c = include $f;
    if (!is_array($c)) { echo "  $f: DOES NOT RETURN AN ARRAY\n"; continue; }
    $seen = [];
    foreach ($keys as $k) {
        if (array_key_exists($k, $c)) { $seen[] = "$k = " . var_export($c[$k], true); $eff[$k] = $c[$k]; }
    }
    echo "  $f: ", $seen ? implode(', ', $seen) : 'neither key', "\n";
}
foreach ($keys as $k) {
    echo "  effective $k: ", array_key_exists($k, $eff) ? var_export($eff[$k], true) : 'not set (false)', "\n";
}
exit(!empty($eff['authLogDisabled']) ? 5 : 0);
PHP
)

# argv: live file, wanted value (true|false), candidate path.
# Exit 0 candidate written, 3 already as wanted, 2 refused (nothing written).
EDIT_PHP=$(cat <<'PHP'
[, $path, $want, $out] = $argv;
$key = 'authApiUserLogDisabled';
$wantBool = ($want === 'true');
$data = include $path;
if (!is_array($data)) { fwrite(STDERR, "$path does not return an array - nothing written\n"); exit(2); }
$text = file_get_contents($path);
if (array_key_exists($key, $data)) {
    if ($data[$key] === $wantBool) { echo "$key is already $want - nothing to do\n"; exit(3); }
    $re = '/^(\s*[\'"]' . $key . '[\'"]\s*=>\s*)(true|false|0|1|null|\'\'|"")(\s*,?[ \t]*)$/mi';
    $n = preg_match_all($re, $text);
    if ($n !== 1) { fwrite(STDERR, "found $n editable '$key' lines (expected 1) - nothing written\n"); exit(2); }
    $new = preg_replace($re, '${1}' . $want . '${3}', $text);
} else {
    $pos = strrpos($text, '];');
    if ($pos === false || trim(substr($text, $pos + 2)) !== '') {
        fwrite(STDERR, "the file does not end with '];' - nothing written\n"); exit(2);
    }
    $head = rtrim(substr($text, 0, $pos));
    if (substr($head, -1) !== ',' && substr($head, -1) !== '[') { $head .= ','; }
    $new = $head . "\n  '" . $key . "' => " . $want . ",\n];\n";
}
if (file_put_contents($out, $new) === false) { fwrite(STDERR, "could not write $out\n"); exit(2); }
exit(0);
PHP
)

# argv: live file, candidate, wanted value. Exit 0 only when the candidate
# holds exactly the live file's settings with this one key set as wanted.
VERIFY_PHP=$(cat <<'PHP'
[, $live, $cand, $want] = $argv;
$a = include $live; $b = include $cand;
if (!is_array($a) || !is_array($b)) { fwrite(STDERR, "not an array\n"); exit(1); }
$a['authApiUserLogDisabled'] = ($want === 'true');
if ($a !== $b) {
    $diff = array_keys(array_diff_key($a, $b) + array_diff_key($b, $a));
    foreach ($a as $k => $v) { if (array_key_exists($k, $b) && $b[$k] !== $v) { $diff[] = $k; } }
    fwrite(STDERR, "candidate differs from the live file beyond the one key: " . implode(', ', array_unique($diff)) . "\n");
    exit(1);
}
exit(0);
PHP
)

report() {
  local rc=0
  in_crm php -r "$READ_PHP" || rc=$?
  if [ "$rc" = 5 ]; then
    echo "!!!! WARNING: authLogDisabled is TRUE — ALL sign-in logging is off, people included."
    echo "!!!! That is the wrong key. Nobody's sign-ins are being recorded. Tell Doug."
  elif [ "$rc" != 0 ]; then
    echo "!!!! could not read the configuration (exit $rc)"; return 1
  fi
}

echo "== $(hostname): container $CONTAINER, image $(docker inspect "$CONTAINER" --format '{{.Config.Image}}' 2>/dev/null || echo '?')"
echo "EspoCRM $(espo_version); PHP $(in_crm php -r 'echo PHP_VERSION;')"
echo "Files (owner uid:gid, mode):"
in_crm sh -c 'for f in data/config*.php data/state.php; do [ -f "$f" ] && echo "  $f $(stat -c "%u:%g %a" "$f")"; done; true'
echo "Settings:"
report

[ -n "$want" ] || { echo "(--check: nothing written)"; exit 0; }

echo "== $mode: $KEY => $want in $FILE"
cand="$FILE.candidate-authlog-$STAMP"
backup="$FILE.bak-authlog-$STAMP"
rc=0
in_crm php -r "$EDIT_PHP" "$FILE" "$want" "$cand" || rc=$?
if [ "$rc" = 3 ]; then echo "RESULT: unchanged"; exit 0; fi
if [ "$rc" != 0 ]; then echo "RESULT: refused (exit $rc); nothing written" >&2; exit 1; fi

if ! in_crm php -l "$cand" >/dev/null || ! in_crm php -r "$VERIFY_PHP" "$FILE" "$cand" "$want"; then
  in_crm rm -f "$cand"
  echo "RESULT: the candidate failed its checks; the live file was not touched" >&2; exit 1
fi

in_crm cp -p "$FILE" "$backup"
in_crm sh -c 'cat "$1" > "$2"' sh "$cand" "$FILE"
in_crm rm -f "$cand"

if ! in_crm php -l "$FILE" >/dev/null; then
  in_crm sh -c 'cat "$1" > "$2"' sh "$backup" "$FILE"
  echo "RESULT: php -l failed on the live file; the backup was put back: $backup" >&2
  in_crm php -l "$FILE" >&2 || true
  exit 1
fi

echo "Read back:"
report
echo "  $FILE $(in_crm stat -c '%u:%g %a' "$FILE")"
echo "Backup: $WORKDIR/$backup (inside the $CONTAINER container)"
echo "RESULT: $KEY is now $want"
