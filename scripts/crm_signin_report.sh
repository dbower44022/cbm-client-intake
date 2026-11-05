#!/usr/bin/env bash
# Read-only: what fills the CRM's sign-in log, and who signs in to the CRM's
# own screens rather than through the application. Run on a CRM droplet:
#
#   scripts/on_crm.sh production scripts/crm_signin_report.sh
#
# Part 1: sign-in log rows in the last 7 days, by login type and method.
# Part 2: for each non-API login over the last 60 days, how many sign-ins came
#   from a "shared" address (one used by 3 or more different logins — the
#   application's DigitalOcean addresses) and how many from any other
#   address (a person's own connection, i.e. the CRM's own screens).
#   Addresses are counted, never printed.
# Writes nothing.
set -eu
docker exec -i espocrm-db sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --table espocrm' <<'SQL'
SELECT IFNULL(u.type, '(no user)') AS login_type,
       IFNULL(a.authentication_method, '-') AS method,
       COUNT(*) AS rows_7_days
  FROM auth_log_record a LEFT JOIN user u ON u.id = a.user_id
 WHERE a.created_at > NOW() - INTERVAL 7 DAY
 GROUP BY 1, 2 ORDER BY 3 DESC;

WITH shared AS (
  SELECT ip_address FROM auth_log_record
   WHERE created_at > NOW() - INTERVAL 60 DAY
   GROUP BY ip_address HAVING COUNT(DISTINCT username) >= 3
)
SELECT a.username,
       SUM(s.ip_address IS NOT NULL) AS via_shared_address,
       SUM(s.ip_address IS NULL)     AS from_other_address,
       MAX(CASE WHEN s.ip_address IS NULL THEN a.created_at END) AS last_other
  FROM auth_log_record a
  LEFT JOIN user u ON u.id = a.user_id
  LEFT JOIN shared s ON s.ip_address = a.ip_address
 WHERE a.created_at > NOW() - INTERVAL 60 DAY
   AND (u.type IS NULL OR u.type <> 'api')
 GROUP BY a.username
HAVING from_other_address > 0
 ORDER BY last_other DESC;
SQL
