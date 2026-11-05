#!/usr/bin/env bash
# Read-only: size of the CRM tables that hold history, and the age of their
# oldest row. Run on a CRM droplet through scripts/on_crm.sh:
#
#   scripts/on_crm.sh production scripts/crm_table_sizes.sh
#
# Reads information_schema and two MIN() queries; writes nothing.
set -eu
docker exec espocrm-db sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "
SELECT table_schema, table_name, table_rows,
       ROUND((data_length+index_length)/1048576,1) AS mb
  FROM information_schema.tables
 WHERE table_name IN (\"action_history_record\",\"note\",\"auth_log_record\",\"c_action_log\")
 ORDER BY mb DESC;
SELECT table_schema, ROUND(SUM(data_length+index_length)/1048576,1) AS total_mb
  FROM information_schema.tables
 WHERE table_schema NOT IN (\"mysql\",\"information_schema\",\"performance_schema\",\"sys\")
 GROUP BY table_schema;
"'
db="$(docker exec espocrm-db sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "SELECT table_schema FROM information_schema.tables WHERE table_name=\"action_history_record\" LIMIT 1"')"
docker exec espocrm-db sh -c "mariadb -uroot -p\"\$MARIADB_ROOT_PASSWORD\" -N -e \"
SELECT 'action_history oldest', MIN(created_at), COUNT(*) FROM \\\`$db\\\`.action_history_record;
SELECT 'action_history per day (last 7)', ROUND(COUNT(*)/7) FROM \\\`$db\\\`.action_history_record WHERE created_at > NOW() - INTERVAL 7 DAY;
\""
