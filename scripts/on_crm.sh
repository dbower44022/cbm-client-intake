#!/usr/bin/env bash
# Run a local shell script on a chapter's CRM droplet, by chapter name.
#
#   scripts/on_crm.sh <chapter> <script> [args…]
#
#   scripts/on_crm.sh boston scripts/convert_notes_wysiwyg.sh
#   scripts/on_crm.sh test   scripts/convert_notes_wysiwyg.sh CPartnerProfile
#
# Exists so that a chat command fits on one terminal line: the Boston droplet
# needs its own key (`-i ~/.ssh/crm-boston`), which pushes the bare ssh line
# past 70 characters and the paste breaks it. The script is streamed to
# `bash -s` on the droplet as root; nothing is copied there.
#
# Chapters (the CRM droplets, not the application platforms):
#   test        crm-test, droplet CBM-TEST            root@104.131.45.208
#   production  Cleveland production, cbm-espocrm-prod root@147.182.135.50
#   boston      Boston Business Mentors               root@209.97.157.6  (key ~/.ssh/crm-boston)
set -eu
chapter="${1:-}"; script="${2:-}"
if [ -z "$chapter" ] || [ -z "$script" ]; then
  echo "usage: scripts/on_crm.sh <test|production|boston> <script> [args…]" >&2; exit 64
fi
shift 2
case "$chapter" in
  test)       target=root@104.131.45.208; key="" ;;
  production) target=root@147.182.135.50; key="" ;;
  boston)     target=root@209.97.157.6;   key="$HOME/.ssh/crm-boston" ;;
  *) echo "unknown chapter '$chapter' (test, production, boston)" >&2; exit 64 ;;
esac
[ -r "$script" ] || { echo "no such script: $script" >&2; exit 66; }
opts=(-o ConnectTimeout=20)
[ -n "$key" ] && opts+=(-i "$key")
echo "== $chapter ($target): $(basename "$script") $*" >&2
exec ssh "${opts[@]}" "$target" bash -s -- "$@" < "$script"
