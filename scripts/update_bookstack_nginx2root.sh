#!/usr/bin/env bash
# Update the docs server's BookStack container so its built-in NGINX carries the
# NGINX2Root fix (CVE-2026-123007, CVE-2026-123633: fixed in 1.30.7 / 1.31.9).
# Streamed to the server by scripts/on_crm.sh; nothing is copied there.
#
#   scripts/on_crm.sh docs scripts/update_bookstack_nginx2root.sh
#
# Order: read the versions; pull the latest image and check ITS NGINX before
# anything changes (an image without the fix stops here, nothing changed);
# dump the database; tag the running image as bookstack-pre-nginx2root; then
# recreate only the bookstack container. A newer image also upgrades BookStack
# itself, and its database migrations run on start — hence the dump.
# Caddy and the database container are never touched.
#
# Undo: in /opt/bookstack, change the bookstack image in docker-compose.yml to
#   bookstack-pre-nginx2root:saved   then   docker compose up -d bookstack
# and, if BookStack's migrations must be reversed too, restore the dump this
# script prints. OPEN-ITEMS.md #90.
set -euo pipefail
cd /opt/bookstack
stamp="$(date -u +%Y%m%d-%H%M)"
image="$(docker inspect -f '{{.Config.Image}}' bookstack)"

ngx() { grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1; }
#: True when an NGINX version string carries the fix (1.30.7+ on 1.30, 1.31.9+, or 1.32+).
fixed() { local v="$1" a b c; IFS=. read -r a b c <<<"$v"
  [ "$a" -gt 1 ] || { [ "$a" -eq 1 ] && { [ "$b" -ge 32 ] || { [ "$b" -eq 31 ] && [ "$c" -ge 9 ]; } || { [ "$b" -eq 30 ] && [ "$c" -ge 7 ]; }; }; }; }

before="$(docker exec bookstack nginx -v 2>&1 | ngx)"
echo "BEFORE: BookStack $(docker exec bookstack cat /app/www/version 2>/dev/null), nginx $before, image $image"

echo "Pulling $image ..."
docker pull -q "$image"
new="$(docker run --rm --entrypoint nginx "$image" -v 2>&1 | ngx)"
echo "The pulled image carries nginx $new"
fixed "$new" || { echo "STOP: the newest $image still carries nginx $new (fix: 1.30.7); nothing was changed. Try again in a few days." >&2; exit 1; }

dump="/root/pre-nginx2root-bookstack-$stamp.sql.gz"
echo "Dumping the database to $dump ..."
# Dump with BookStack's OWN database login, read from its container: that is the
# login the site works with today. (The database container's root password
# variable is only used when the database is first created, and on this server
# it no longer matches — refused 11-20-26.) The password travels as MYSQL_PWD,
# never on a command line.
benv() { docker exec bookstack printenv "$1" 2>/dev/null || true; }
db_user="$(benv DB_USERNAME)"; [ -n "$db_user" ] || db_user="$(benv DB_USER)"
db_pass="$(benv DB_PASSWORD)"; [ -n "$db_pass" ] || db_pass="$(benv DB_PASS)"
db_name="$(benv DB_DATABASE)"
[ -n "$db_user" ] && [ -n "$db_name" ] || { echo "STOP: BookStack's database login is not in its container settings; nothing was changed." >&2; exit 1; }
if ! docker exec -e MYSQL_PWD="$db_pass" bookstack_db mariadb-dump -u"$db_user" --single-transaction --no-tablespaces "$db_name" | gzip > "$dump"; then
  echo "STOP: the database dump failed; nothing was changed." >&2; exit 1
fi
[ "$(gzip -dc "$dump" | head -c 4096 | wc -c)" -gt 100 ] || { echo "STOP: the dump is empty; nothing was changed." >&2; exit 1; }
echo "Dump OK: $(du -h "$dump" | cut -f1)"

docker tag "$(docker inspect -f '{{.Image}}' bookstack)" bookstack-pre-nginx2root:saved
cp -n docker-compose.yml "docker-compose.yml.pre-nginx2root" 2>/dev/null || true
docker compose up -d bookstack

echo "Waiting for BookStack to start ..."
for _ in $(seq 1 36); do
  docker exec bookstack sh -c 'curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1/' 2>/dev/null | grep -qE '^(200|302)$' && break
  sleep 5
done
after="$(docker exec bookstack nginx -v 2>&1 | ngx)"
code="$(curl -s -o /dev/null -w '%{http_code}' -m 15 https://docs.clevelandbusinessmentors.org/ || echo 000)"
echo "AFTER:  BookStack $(docker exec bookstack cat /app/www/version 2>/dev/null), nginx $after, the public site answers $code"
if fixed "$after" && { [ "$code" = 200 ] || [ "$code" = 302 ]; }; then
  echo "RESULT: patched (nginx $after)"
else
  echo "RESULT: NOT CONFIRMED — last lines of the bookstack log:"; docker logs --tail 25 bookstack 2>&1
fi
