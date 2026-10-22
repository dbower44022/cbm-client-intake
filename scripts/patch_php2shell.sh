#!/usr/bin/env bash
# Patch one server against PHP2Shell (CVE-2026-109618, CVE-2026-109619).
# Streamed to the server by scripts/on_crm.sh; nothing is copied there.
#
#   scripts/on_crm.sh test       scripts/patch_php2shell.sh espocrm 9.3.10-fpm
#   scripts/on_crm.sh production scripts/patch_php2shell.sh espocrm 9.3.10-fpm
#   scripts/on_crm.sh boston     scripts/patch_php2shell.sh espocrm 10.0.10-fpm
#   scripts/on_crm.sh lakeside   scripts/patch_php2shell.sh espocrm 10.0.10-fpm
#   scripts/on_crm.sh docs       scripts/patch_php2shell.sh bookstack
#
# EspoCRM: dumps the database first, pins the three PHP containers to the
# named image tag (the fixed images carry PHP 8.4.27), recreates only those
# three, then waits for the image's own upgrade step and reports the result.
# The tag is pinned on purpose: the bare `fpm` tag now means EspoCRM 10, and
# Cleveland's CRMs run 9.3 — pulling `fpm` would be a major upgrade.
# The database, nginx and certbot containers are never pulled or touched.
#
# BookStack: pulls and recreates only the bookstack container.
#
# Undo: an EspoCRM version cannot be stepped back down by changing the image.
# The way back is the database dump this script writes (path printed below)
# plus the saved compose file docker-compose.yml.pre-php2shell.
set -euo pipefail
kind="${1:-}"; tag="${2:-}"
stamp="$(date -u +%Y%m%d-%H%M)"

case "$kind" in
  espocrm)
    [ -n "$tag" ] || { echo "usage: espocrm <image tag, e.g. 9.3.10-fpm>" >&2; exit 64; }
    cd /var/www/espocrm
    echo "BEFORE: PHP $(docker exec espocrm php -r 'echo PHP_VERSION;'), EspoCRM $(docker exec -w /var/www/html espocrm bin/command config:get version 2>/dev/null || echo '?')"

    dump="/root/pre-php2shell-$stamp.sql.gz"
    echo "Dumping the database to $dump ..."
    docker exec espocrm-db sh -c 'mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --single-transaction --all-databases' | gzip > "$dump"
    [ -s "$dump" ] || { echo "STOP: the dump is empty; nothing was changed." >&2; exit 1; }
    echo "Dump OK: $(du -h "$dump" | cut -f1)"

    cp -n docker-compose.yml docker-compose.yml.pre-php2shell
    sed -i -E "s#image: espocrm/espocrm:[A-Za-z0-9._-]+#image: espocrm/espocrm:$tag#" docker-compose.yml
    echo "Compose now uses: $(grep -c "espocrm/espocrm:$tag" docker-compose.yml) x espocrm/espocrm:$tag"

    docker compose pull espocrm espocrm-daemon espocrm-websocket
    docker compose up -d espocrm espocrm-daemon espocrm-websocket

    want="${tag%%-*}"
    echo "Waiting for EspoCRM to report $want (the image upgrades in place on start) ..."
    for _ in $(seq 1 60); do
      got="$(docker exec -w /var/www/html espocrm bin/command config:get version 2>/dev/null || true)"
      [ "$got" = "$want" ] && break
      sleep 5
    done
    echo "AFTER:  PHP $(docker exec espocrm php -r 'echo PHP_VERSION;'), EspoCRM ${got:-?}"
    for c in espocrm espocrm-daemon espocrm-websocket; do
      echo "  $c: $(docker inspect "$c" --format '{{.State.Status}}') PHP $(docker exec "$c" php -r 'echo PHP_VERSION;' 2>/dev/null || echo '?')"
    done
    if [ "${got:-}" = "$want" ]; then echo "RESULT: patched"; else
      echo "RESULT: NOT CONFIRMED — last lines of the espocrm log:"; docker logs --tail 25 espocrm 2>&1; fi
    ;;
  bookstack)
    cd /opt/bookstack
    echo "BEFORE: PHP $(docker exec bookstack php -r 'echo PHP_VERSION;'), BookStack $(docker exec bookstack cat /app/www/version 2>/dev/null)"
    docker compose pull bookstack
    docker compose up -d bookstack
    for _ in $(seq 1 30); do docker exec bookstack php -r 'echo 1;' >/dev/null 2>&1 && break; sleep 5; done
    sleep 10
    v="$(docker exec bookstack php -r 'echo PHP_VERSION;')"
    echo "AFTER:  PHP $v, BookStack $(docker exec bookstack cat /app/www/version 2>/dev/null)"
    case "$v" in 8.5.1[2-9]*|8.5.[2-9]*) echo "RESULT: patched" ;; *) echo "RESULT: NOT CONFIRMED"; docker logs --tail 25 bookstack 2>&1 ;; esac
    ;;
  *) echo "usage: patch_php2shell.sh espocrm <tag> | bookstack" >&2; exit 64 ;;
esac
