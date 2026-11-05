#!/usr/bin/env bash
# Read-only: the production checks C3, C4, C5, C7 and C8 of the mentor login
# integrity plan (prds/mentor-login-integrity-plan.md, § 7). Run on a CRM
# droplet through scripts/on_crm.sh:
#
#   scripts/on_crm.sh production scripts/check_login_integrity_prod.sh
#
# SELECT statements and file reads (cat / php -r reading JSON) only; writes
# nothing, restarts nothing. Each query runs on its own, so one failing query
# prints FAILED and the rest still run.
set -u

q() {  # q "<title>"  (SQL on stdin)
  echo; echo "=== $1"
  docker exec -i espocrm-db sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --table espocrm' \
    || echo "FAILED: $1"
}

# --- Column names first, so a wrong guess below is readable from the output.
q "columns of the tables used" <<'SQL'
SELECT table_name, GROUP_CONCAT(column_name ORDER BY ordinal_position) AS columns
  FROM information_schema.columns
 WHERE table_schema = 'espocrm'
   AND table_name IN ('user','team','role','team_user','role_team','role_user',
                      'entity_user','entity_team','c_mentor_profile',
                      'action_history_record','note')
 GROUP BY table_name;
SQL
q "tables whose name suggests a user or team join" <<'SQL'
SELECT table_name FROM information_schema.tables
 WHERE table_schema = 'espocrm'
   AND (table_name LIKE '%user%' OR table_name LIKE '%team%')
 ORDER BY table_name;
SQL

# --- C3: tracked ("audited") fields in the custom metadata.
echo; echo "=== C3 tracked fields (custom metadata)"
for e in CMentorProfile CPartnerProfile CSponsorProfile; do
  f="/var/www/html/custom/Espo/Custom/Resources/metadata/entityDefs/$e.json"
  echo "--- $e"
  docker exec espocrm php -r '
    $d = json_decode(@file_get_contents($argv[1]), true);
    if (!is_array($d)) { echo "  (file missing or unreadable)\n"; exit; }
    $f = $d["fields"] ?? [];
    $a = []; foreach ($f as $k => $v) if (!empty($v["audited"])) $a[] = $k;
    echo "  audited: ", ($a ? implode(", ", $a) : "(none)"), "\n";
    foreach (["cbmEmail","mentorStatus","mentorType","acceptingNewClients",
              "maximumClientCapacity","mentorStatusNotes","departureDate",
              "partnershipStatus","funderStatus"] as $n)
      if (isset($f[$n])) echo "  has $n: type=", $f[$n]["type"] ?? "?",
        " audited=", !empty($f[$n]["audited"]) ? "yes" : "no", "\n";
    $m = []; foreach ($f as $k => $v)
      if (preg_match("/note|prefer/i", $k)) $m[] = $k;
    echo "  fields named like note/prefer: ", ($m ? implode(", ", $m) : "(none)"), "\n";
  ' "$f" || echo "  FAILED reading $e"
done
echo "--- labels mentioning Mentor Assignment Preferences or Status Notes"
docker exec espocrm sh -c 'grep -rniE "assignment preferences|status notes" /var/www/html/custom/Espo/Custom/Resources/i18n/en_US/CMentorProfile.json' \
  || echo "  (no match)"

# --- C4: Sharon Rose's changes to User records, 10-17-26 to 11-02-26.
q "C4 Sharon Rose's logins" <<'SQL'
SELECT id, user_name, type, is_active FROM user
 WHERE first_name LIKE 'Sharon%' AND last_name LIKE 'Rose%';
SQL
q "C4 action history on User by Sharon Rose" <<'SQL'
SELECT h.created_at, h.action, h.target_id, t.user_name AS target_login,
       CONCAT_WS(' ', t.first_name, t.last_name) AS target_name, h.ip_address IS NOT NULL AS has_ip
  FROM action_history_record h
  JOIN user s ON s.id = h.user_id AND s.first_name LIKE 'Sharon%' AND s.last_name LIKE 'Rose%'
  LEFT JOIN user t ON t.id = h.target_id
 WHERE h.target_type = 'User' AND h.action <> 'read'
 ORDER BY h.created_at;
SQL
q "C4 action history oldest row (retention)" <<'SQL'
SELECT MIN(created_at) AS history_starts FROM action_history_record;
SQL
q "C4 notes on User records written by Sharon Rose" <<'SQL'
SELECT n.created_at, n.type, n.parent_id, t.user_name AS target_login, LEFT(n.data, 600) AS data
  FROM note n
  JOIN user s ON s.id = n.created_by_id AND s.first_name LIKE 'Sharon%' AND s.last_name LIKE 'Rose%'
  LEFT JOIN user t ON t.id = n.parent_id
 WHERE n.parent_type = 'User'
 ORDER BY n.created_at;
SQL
q "C4 User records last modified by Sharon Rose" <<'SQL'
SELECT t.id, t.user_name, CONCAT_WS(' ', t.first_name, t.last_name) AS name,
       t.type, t.is_active, t.created_at, t.modified_at
  FROM user t
  JOIN user s ON s.id = t.modified_by_id AND s.first_name LIKE 'Sharon%' AND s.last_name LIKE 'Rose%';
SQL
q "C4 User records created by Sharon Rose" <<'SQL'
SELECT t.id, t.user_name, CONCAT_WS(' ', t.first_name, t.last_name) AS name,
       t.type, t.is_active, t.created_at
  FROM user t
  JOIN user s ON s.id = t.created_by_id AND s.first_name LIKE 'Sharon%' AND s.last_name LIKE 'Rose%';
SQL

# --- C5: the two mentor profiles' statuses and logins.
q "C5 mentor profiles: David Weissman and Doug/Douglas Bower" <<'SQL'
SELECT p.id, p.name, p.mentor_status, p.deleted, p.cbm_email,
       u.user_name AS assigned_user_single, p.created_at, p.modified_at
  FROM c_mentor_profile p
  LEFT JOIN user u ON u.id = p.assigned_user_id
 WHERE p.id = '6a62ca9f5188b9656'
    OR p.name LIKE '%Weissman%'
    OR p.name LIKE '%Bower%'
 ORDER BY p.name, p.created_at;
SQL
q "C5 mentor profiles carrying doug.bower or david.weissman as an assigned user" <<'SQL'
SELECT u.user_name, eu.entity_id AS profile_id, p.name, p.mentor_status,
       p.deleted AS profile_deleted, eu.deleted AS link_deleted
  FROM entity_user eu
  JOIN user u ON u.id = eu.user_id
  LEFT JOIN c_mentor_profile p ON p.id = eu.entity_id
 WHERE eu.entity_type = 'CMentorProfile'
   AND u.user_name IN ('doug.bower@cbmentors.org','david.weissman@cbmentors.org')
 ORDER BY u.user_name, p.name;
SQL
q "C5 entity types present in entity_user (sanity)" <<'SQL'
SELECT entity_type, COUNT(*) FROM entity_user GROUP BY entity_type;
SQL

# --- C7: Data Integrity Team, System Management.
q "C7 teams and roles named like Data Integrity or System Management" <<'SQL'
SELECT 'team' AS kind, id, name, deleted FROM team
 WHERE name LIKE '%Integrity%' OR name LIKE '%System Management%'
UNION ALL
SELECT 'role', id, name, deleted FROM role
 WHERE name LIKE '%Integrity%' OR name LIKE '%System Management%';
SQL
q "C7 roles attached to those teams" <<'SQL'
SELECT t.name AS team, r.name AS role, rt.deleted AS link_deleted
  FROM team t
  JOIN role_team rt ON rt.team_id = t.id
  JOIN role r ON r.id = rt.role_id
 WHERE t.name LIKE '%Integrity%' OR t.name LIKE '%System Management%';
SQL
q "C7 members of those teams" <<'SQL'
SELECT t.name AS team, COUNT(u.id) AS members,
       GROUP_CONCAT(u.user_name ORDER BY u.user_name) AS logins
  FROM team t
  LEFT JOIN team_user tu ON tu.team_id = t.id AND tu.deleted = 0
  LEFT JOIN user u ON u.id = tu.user_id AND u.deleted = 0
 WHERE t.deleted = 0
   AND (t.name LIKE '%Integrity%' OR t.name LIKE '%System Management%')
 GROUP BY t.name;
SQL
q "C7 users holding an Integrity role directly" <<'SQL'
SELECT r.name AS role, u.user_name
  FROM role r
  JOIN role_user ru ON ru.role_id = r.id AND ru.deleted = 0
  JOIN user u ON u.id = ru.user_id AND u.deleted = 0
 WHERE r.name LIKE '%Integrity%' OR r.name LIKE '%System Management%';
SQL

# --- C8: CActionLog read per role; roles on the three manager teams.
q "C8 each role's CActionLog permission" <<'SQL'
SELECT name AS role,
       JSON_EXTRACT(data, '$.CActionLog') AS cactionlog
  FROM role
 WHERE deleted = 0
 ORDER BY name;
SQL
q "C8 roles attached to Mentor / Partner Management / Sponsor Management teams" <<'SQL'
SELECT t.name AS team, r.name AS role, JSON_EXTRACT(r.data, '$.CActionLog') AS cactionlog
  FROM team t
  JOIN role_team rt ON rt.team_id = t.id AND rt.deleted = 0
  JOIN role r ON r.id = rt.role_id AND r.deleted = 0
 WHERE t.deleted = 0
   AND t.name IN ('Mentor Team','Partner Management Team','Sponsor Management Team')
 ORDER BY t.name, r.name;
SQL
echo; echo "=== done"
