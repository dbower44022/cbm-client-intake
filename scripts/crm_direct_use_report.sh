#!/usr/bin/env bash
# Read-only: what people do in the CRM's own screens. Run on a CRM droplet:
#
#   scripts/on_crm.sh production scripts/crm_direct_use_report.sh
#
# Uses Action History (about the last 15–22 days). A row counts as "the CRM's
# own screens" when its address is NOT shared by 3 or more logins in the
# sign-in log (the shared ones are this application's addresses). For each
# login and record type: how many records were read, created, changed and
# deleted that way. Addresses are counted, never printed. Writes nothing.
set -eu
docker exec -i espocrm-db sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --table espocrm' <<'SQL'
WITH shared AS (
  SELECT ip_address FROM auth_log_record
   WHERE created_at > NOW() - INTERVAL 60 DAY
   GROUP BY ip_address HAVING COUNT(DISTINCT username) >= 3
)
SELECT u.user_name AS login,
       h.target_type AS record_type,
       SUM(h.action = 'read')   AS viewed,
       SUM(h.action = 'create') AS created,
       SUM(h.action = 'update') AS changed,
       SUM(h.action = 'delete') AS deleted,
       MAX(h.created_at)        AS last_seen
  FROM action_history_record h
  JOIN user u ON u.id = h.user_id
  LEFT JOIN shared s ON s.ip_address = h.ip_address
 WHERE s.ip_address IS NULL
   AND u.type <> 'api'
 GROUP BY u.user_name, h.target_type
 ORDER BY u.user_name, (SUM(h.action <> 'read')) DESC, viewed DESC;
SELECT MIN(created_at) AS history_starts FROM action_history_record;
SQL
