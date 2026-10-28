#!/usr/bin/env bash
# Install (or remove) the CRM's multi-column sorted list endpoint on a chapter's CRM.
#
#   scripts/install_sorted_list.sh test            install on crm-test
#   scripts/install_sorted_list.sh test --remove   take it away again
#
# What it installs (prds/shared-grid-plan.md § 8, Doug's ruling 10-28-26):
#   crm/extensions/sorted-list/custom/Espo/Custom/Api/SortedList.php
#   one route, GET /SortedList/:entityType, MERGED into
#   custom/Espo/Custom/Resources/routes.json (any routes already there are
#   kept; the old file is saved beside it as routes.json.bak-<stamp>).
# Then it rebuilds EspoCRM. Nothing in the database changes.
#
# crm-test first. Production and Boston only after the crm-test check and
# Doug's go-ahead, at a release slot.
set -euo pipefail
cd "$(dirname "$0")/.."
chapter="${1:-}"; mode="${2:-install}"
case "$chapter" in
  test)       target=root@104.131.45.208; key="" ;;
  production) target=root@147.182.135.50; key="" ;;
  boston)     target=root@209.97.157.6;   key="$HOME/.ssh/crm-boston" ;;
  lakeside)   target=root@143.198.4.94;   key="" ;;
  *) echo "usage: scripts/install_sorted_list.sh <test|production|boston|lakeside> [--remove]" >&2; exit 64 ;;
esac
opts=(-o ConnectTimeout=20)
[ -n "$key" ] && opts+=(-i "$key")
remote() { ssh "${opts[@]}" "$target" "$@"; }
stamp="$(date -u +%Y%m%d-%H%M)"
php_file="custom/Espo/Custom/Api/SortedList.php"
routes="custom/Espo/Custom/Resources/routes.json"

echo "== $chapter ($target): sorted list endpoint, $mode"
echo "EspoCRM: $(remote "docker exec -w /var/www/html espocrm php -r '\$c=include \"data/config.php\"; echo \$c[\"version\"] ?? \"?\";'" 2>/dev/null || echo '?')"

if [ "$mode" = "--remove" ]; then
  remote "docker exec -w /var/www/html espocrm rm -f $php_file"
  remote "docker exec -w /var/www/html espocrm php -r '
    \$f = \"$routes\"; if (!is_file(\$f)) { echo \"no routes file\n\"; exit; }
    copy(\$f, \$f . \".bak-$stamp\");
    \$r = json_decode(file_get_contents(\$f), true) ?: [];
    \$r = array_values(array_filter(\$r, fn(\$x) => (\$x[\"route\"] ?? \"\") !== \"/SortedList/:entityType\"));
    if (\$r) { file_put_contents(\$f, json_encode(\$r, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . \"\n\"); } else { unlink(\$f); }
    echo \"route removed\n\";'"
else
  # The PHP file, as www-data's own.
  tar -C crm/extensions/sorted-list -cf - "$php_file" \
    | remote "docker exec -i -w /var/www/html espocrm tar -xf - && docker exec espocrm chown -R www-data:www-data /var/www/html/custom/Espo/Custom/Api"
  # The route, merged into whatever routes the CRM already has.
  remote "docker exec -w /var/www/html espocrm php -r '
    \$f = \"$routes\"; @mkdir(dirname(\$f), 0775, true);
    \$r = is_file(\$f) ? (json_decode(file_get_contents(\$f), true) ?: []) : [];
    if (is_file(\$f)) { copy(\$f, \$f . \".bak-$stamp\"); }
    \$r = array_values(array_filter(\$r, fn(\$x) => (\$x[\"route\"] ?? \"\") !== \"/SortedList/:entityType\"));
    \$r[] = [\"route\" => \"/SortedList/:entityType\", \"method\" => \"get\", \"actionClassName\" => \"Espo\\\\Custom\\\\Api\\\\SortedList\"];
    file_put_contents(\$f, json_encode(\$r, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . \"\n\");
    echo count(\$r) . \" route(s) in routes.json\n\";' && docker exec espocrm chown www-data:www-data /var/www/html/$routes"
fi

remote "docker exec -u www-data -w /var/www/html espocrm php command.php rebuild" && echo "rebuild: done"
echo "== finished. Check it from the application: Claude reads /api/v1/SortedList/CProspect with the org-wide key."
