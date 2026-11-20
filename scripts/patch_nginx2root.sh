#!/usr/bin/env bash
# Patch one CRM server against NGINX2Root (CVE-2026-123007, CVE-2026-123633).
# Streamed to the server by scripts/on_crm.sh; nothing is copied there.
#
#   scripts/on_crm.sh test       scripts/patch_nginx2root.sh
#   scripts/on_crm.sh bma        scripts/patch_nginx2root.sh
#   scripts/on_crm.sh lakeside   scripts/patch_nginx2root.sh
#   scripts/on_crm.sh boston     scripts/patch_nginx2root.sh
#   scripts/on_crm.sh production scripts/patch_nginx2root.sh
#
# Pins the espocrm-nginx container to an exact fixed image (default
# nginx:1.31.9, the fixed mainline release; pass another tag as the first
# argument) and recreates only that container. The tag is pinned on purpose:
# CRMBuilder writes the bare `nginx` image, which means "whatever was latest
# when the server was built" — every server was built before the fix.
# The image is pulled BEFORE the compose file is changed, so a tag that does
# not exist yet stops the script with nothing changed. EspoCRM, its database,
# the daemon, the websocket and certbot are never touched. The CRM is
# unreachable for a few seconds while the container restarts.
#
# Undo (puts the vulnerable version back — only if the new one fails):
#   cd /var/www/espocrm && cp docker-compose.yml.pre-nginx2root docker-compose.yml
#   docker compose up -d --force-recreate espocrm-nginx
set -euo pipefail
tag="${1:-1.31.9}"
cd /var/www/espocrm

nginx_version() { docker exec espocrm-nginx nginx -v 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo '?'; }
echo "BEFORE: nginx $(nginx_version), image $(docker inspect -f '{{.Config.Image}}' espocrm-nginx)"

echo "Pulling nginx:$tag ..."
docker pull -q "nginx:$tag" || { echo "STOP: nginx:$tag could not be pulled; nothing was changed." >&2; exit 1; }

echo "Testing the server's own configuration with the new image ..."
mounts="$(docker inspect -f '{{range .Mounts}}-v {{.Source}}:{{.Destination}}:ro {{end}}' espocrm-nginx)"
net="$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' espocrm-nginx | awk '{print $1}')"
# Same network as the live container, so the upstream names in the config resolve,
# and the same environment, so the image's template step fills in the same values
# (the CRMBuilder config uses $NGINX_HOST and friends).
envfile="$(mktemp)"; trap 'rm -f "$envfile"' EXIT
docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' espocrm-nginx \
  | grep -v -E '^$|^(PATH|NGINX_VERSION|NJS_VERSION|NJS_RELEASE|PKG_RELEASE|DYNPKG_RELEASE)=' > "$envfile"
# shellcheck disable=SC2086
if ! docker run --rm --network "$net" --env-file "$envfile" $mounts "nginx:$tag" nginx -t 2>&1 | tail -3; then
  echo "STOP: the configuration does not pass nginx -t with nginx:$tag; nothing was changed." >&2; exit 1
fi

cp -n docker-compose.yml docker-compose.yml.pre-nginx2root
sed -i -E "s#^([[:space:]]*image:[[:space:]]*)nginx(:[A-Za-z0-9._-]+)?[[:space:]]*\$#\1nginx:$tag#" docker-compose.yml
n="$(grep -cE "image:[[:space:]]*nginx:$tag\$" docker-compose.yml || true)"
echo "Compose now uses nginx:$tag in $n place(s)"
[ "$n" -ge 1 ] || { cp docker-compose.yml.pre-nginx2root docker-compose.yml; echo "STOP: no nginx image line found; compose file restored." >&2; exit 1; }

docker compose up -d --force-recreate espocrm-nginx
sleep 5

got="$(nginx_version)"
state="$(docker inspect -f '{{.State.Status}}' espocrm-nginx)"
code="$(curl -sk -o /dev/null -w '%{http_code}' --http2 https://127.0.0.1/ || echo 000)"
echo "AFTER:  nginx $got, container $state, local HTTPS answers $code"
if [ "$got" = "$tag" ] && [ "$state" = running ] && [ "$code" != 000 ]; then
  echo "RESULT: patched (nginx $got)"
else
  echo "RESULT: NOT CONFIRMED — last lines of the nginx log:"; docker logs --tail 25 espocrm-nginx 2>&1
fi
