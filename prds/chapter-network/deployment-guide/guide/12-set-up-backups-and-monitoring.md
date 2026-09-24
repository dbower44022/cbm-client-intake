# Stage 12 — Set up backups and monitoring

**Version:** 0.4  
**Last Updated:** 09-23-26 20:40  
**Generated from** `steps/stage-12.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

This stage makes sure the chapter's records can be got back after a mistake or a failure, and that a person finds out when the system stops working. It comes before any real records are loaded, because a backup taken afterwards is too late for whatever went wrong before it.

**Who:** The central support organization, working inside the chapter's hosting account. The chapter names who reads the alerts.  
**Time:** About two hours, most of it waiting for a restored copy to be built.  
**When this stage is done:** The chapter's pages can go on its website (stage 13), and real records can be loaded (stage 15).

**Before you start:**

- The CRM server (stage 9)
- The applications and their database (stage 11)
- Outgoing mail working, for the alert emails (step 11.15)
- The decision about who receives warning messages (step 4.9)

**Steps in this stage:**

- 12.1 Back up the CRM server on a schedule
- 12.2 Back up the application database on a schedule
- 12.3 Restore from a backup once
- 12.4 Confirm alerts reach a person
- 12.5 Add the chapter to the list of systems being watched

---

## 12.1 Back up the CRM server on a schedule

**Why:** A backup of the whole server holds the CRM's database, its uploaded files and its configuration together, so one restore brings back all three.

**Who:** The central support organization inside the chapter's hosting account

**Finish first:**

- step 9.3 Run CRMBuilder's deploy wizard

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In a terminal signed in to the chapter's DigitalOcean account (`doctl auth init` with the chapter's DigitalOcean token), list the servers and note the CRM server's ID:
   - doctl compute droplet list --format ID,Name,Features

   *You should see:* The CRM server's row. Its Features column does not yet include backups.
2. Switch on daily backups, putting the CRM server's ID in place of SERVER-ID:
   - doctl compute droplet-action enable-backups SERVER-ID --backup-policy-plan daily --backup-policy-hour 4 --wait

   *You should see:* The action reported as completed.
3. Read the policy back:
   - doctl compute droplet backup-policies get SERVER-ID

   *You should see:* Enabled true, Plan daily, Hour 4, Retention Period Days 7. Cleveland's production CRM reads exactly this.
4. Write on the chapter's entry in the list of watched systems (step 12.5):
   - Schedule: daily
   - Backup window: from 04:00 UTC, four hours long
   - Kept for: seven days

**Done when:** Backups run automatically, and the schedule and how long backups are kept are written down.

**How to check:** The next morning, the Backups tab lists a backup taken overnight.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Two things. Seven days is short: a mistake nobody notices for eight days cannot be undone from these backups. And backups cost extra and are easy to leave off, because the deployment wizard does not switch them on.

---

## 12.2 Back up the application database on a schedule

**Why:** Submissions that have arrived but not yet reached the CRM exist only in this database, so losing it loses them.

**Who:** The central support organization inside the chapter's hosting account

**Finish first:**

- step 11.4 Create the database

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the chapter's DigitalOcean account, list the databases and note the application database's ID:
   - doctl databases list --format ID,Name,Engine,Size

   *You should see:* A row for the application's database. If there is no row at all, the database is a development database, which this command does not list and which takes no backups.
2. If there is no row, convert the database: in the DigitalOcean web console, open the application, then Settings, then the database component, and choose to convert it to a managed database at the smallest size. This label was the one Cleveland used on 07-23-26 and has not been checked since.
   *You should see:* The application keeps running, and the database now appears in the list above.
3. List the database's backups, putting the database's ID in place of DATABASE-ID:
   - doctl databases backups DATABASE-ID

   *You should see:* A backup dated within the last day. Backups are daily and kept seven days.
4. Write on the chapter's entry in the list of watched systems:
   - Schedule: daily
   - Kept for: seven days, with restore to any moment in that week

**Done when:** Backups run automatically, and the schedule and retention are written down.

**How to check:** The database's Backups tab lists a backup taken in the last day.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A development database that nobody notices. Everything works, no error appears, and there are no backups. The trial chapter's database is in this state.

---

## 12.3 Restore from a backup once

**Why:** A backup nobody has restored is only a hope, so each kind is restored once into a separate copy and checked.

**Who:** The central support organization

**Finish first:**

- step 12.1 Back up the CRM server on a schedule
- step 12.2 Back up the application database on a schedule

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Database first. Find the application database's ID:
   - doctl databases list --format ID,Name
2. Restore it into a new database, putting that ID in place of DATABASE-ID. The output is thrown away on purpose, because it includes the new database's password:
   - doctl databases fork restore-test-SHORT-LABEL --restore-from-cluster-id DATABASE-ID --wait > /dev/null

   *You should see:* The prompt returns after five to fifteen minutes, with nothing printed.
3. Find the new database's ID:
   - doctl databases list --format ID,Name,Status

   *You should see:* A row named restore-test-SHORT-LABEL with status online. Note its ID as RESTORED-ID.
4. Let your own computer through the new database's firewall, which copies the live one and admits only the application. Putting your computer's public address in place of YOUR-IP (find it with `curl -s https://api.ipify.org`):
   - doctl databases firewalls append RESTORED-ID --rule ip_addr:YOUR-IP
5. Count the submissions in the copy, without ever printing its address. This needs `psql` installed. The application's database is named after the chapter's short label, so put it in place of DATABASE-NAME (list it with `doctl databases db list RESTORED-ID`):
   - psql "$(doctl databases connection RESTORED-ID --no-header --format URI | sed 's#/defaultdb?#/DATABASE-NAME?#')" -c 'select count(*), max(received_at) from submission'

   *You should see:* A count of submissions and the date of the newest one, which should be recent. On Cleveland's test on 09-18-26 the newest was eight hours after the last daily backup, because a restore with no date rebuilds to the latest moment.
6. Delete the copy the same hour. It holds the chapter's real personal details:
   - doctl databases delete RESTORED-ID --force

   *You should see:* The copy gone from `doctl databases list`.
7. Now the CRM server. List its backups, putting the CRM server's ID in place of SERVER-ID:
   - doctl compute droplet backups SERVER-ID

   *You should see:* One backup image per day. Note the newest image's ID as BACKUP-IMAGE-ID.
8. Create a new server from that backup, in the same region and size as the CRM server (read both from `doctl compute droplet get SERVER-ID --format Region,SizeSlug`):
   - doctl compute droplet create restore-test-SHORT-LABEL --image BACKUP-IMAGE-ID --region REGION --size SIZE --wait

   *You should see:* A new server with its own public address, NEW-SERVER-IP.
9. Open https://NEW-SERVER-IP in a browser. The certificate warning is expected, because the certificate is for the CRM's real address. Sign in as the central support organization's administrator and open one record changed recently.
   *You should see:* The record, as it was at the time of the backup.
10. Delete the new server:
    - doctl compute droplet delete restore-test-SHORT-LABEL --force
11. Write down on the chapter's entry in the list of watched systems:
    - The date.
    - What was checked in each copy.
    - How long each restore took, timed from the command to the copy being usable.

**Done when:** A restore has actually been performed and the result checked. An untested backup is not a backup.

**How to check:** Both copies started and held the expected records, and the test is written down.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A restore with no date given rebuilds the database to the latest moment it can, not to the last daily backup. That is better, but it means the two are the same command. Also, the restored copy holds real personal details, so it is printed as counts and dates only and deleted the same hour.

---

## 12.4 Confirm alerts reach a person

**Why:** When the system stops working or submissions pile up, somebody has to be told, and an alert nobody reads is the same as no alert.

**Who:** The chapter and the central support organization — the central support organization sets it up; the chapter names who reads the alerts

**Finish first:**

- step 4.9 Decide who receives the system's warning messages
- step 11.15 Confirm outgoing mail

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. The alert address must belong to a member of the chapter's DigitalOcean team; DigitalOcean refuses any other. Check it is listed under the chapter's team members in the DigitalOcean web console.
2. Create the uptime check on the application's health page, putting the application's address in place of APP-ADDRESS:
   - doctl monitoring uptime create SHORT-LABEL-app-up --target https://APP-ADDRESS/healthz --type https --regions us_east

   *You should see:* A new uptime check with its ID. Note it as APP-CHECK-ID.
3. Add its alert, putting the alert address in place of ALERT-ADDRESS:
   - doctl monitoring uptime alert create APP-CHECK-ID --name SHORT-LABEL-app-down --type down --threshold 1 --comparison less_than --period 2m --emails ALERT-ADDRESS

   *You should see:* The alert with type down and period 2m. These are exactly the settings on Cleveland's production application.
4. Create the uptime check on the CRM's own address, putting it in place of CRM-ADDRESS:
   - doctl monitoring uptime create SHORT-LABEL-crm-up --target https://CRM-ADDRESS/ --type https --regions us_east

   *You should see:* A second uptime check with its ID. Note it as CRM-CHECK-ID.
5. Add its alert:
   - doctl monitoring uptime alert create CRM-CHECK-ID --name SHORT-LABEL-crm-down --type down --threshold 1 --comparison less_than --period 2m --emails ALERT-ADDRESS
6. Add the three database alerts, putting the application database's ID in place of DATABASE-ID. Run each line on its own:
   - doctl monitoring alert create --type v1/dbaas/alerts/cpu_alerts --compare GreaterThan --value 90 --window 5m --entities DATABASE-ID --emails ALERT-ADDRESS --description 'CPU is running high'
   - doctl monitoring alert create --type v1/dbaas/alerts/memory_utilization_alerts --compare GreaterThan --value 90 --window 5m --entities DATABASE-ID --emails ALERT-ADDRESS --description 'Memory Utilization is running high'
   - doctl monitoring alert create --type v1/dbaas/alerts/disk_utilization_alerts --compare GreaterThan --value 90 --window 5m --entities DATABASE-ID --emails ALERT-ADDRESS --description 'Disk Utilization is running high'

   *You should see:* Three alert policies. They match Cleveland's database alerts.
7. Send a test alert from the application itself. Open a console on the background worker, putting the application's ID in place of APP-ID:
   - doctl apps console APP-ID delivery-worker
8. In that console, run:
   - PYTHONPATH=/app .venv/bin/python -c "import asyncio; from core.config import get_settings; from core.monitoring import send_alert; asyncio.run(send_alert(get_settings(), 'Test alert: checking the alert path'))"

   *You should see:* The line "alert sent (email to ...)" in the output, and the message arrives at the alert address. The line "ALERT (no delivery channel configured/working)" means the alert went only to the log.
9. Write down the names of the people who read the alert address.

**Done when:** A test alert arrives at an address somebody reads, and it is recorded who reads it.

**How to check:** The test alert arrives, and a named person confirms they saw it.

**If it didn't work:** If no test alert arrives, check the Google connection first. The application sends its alerts through the chapter's Google account.

**What usually goes wrong:** Three things. A chapter with the Google connection switched off gets no alert emails at all, and nothing says so. An alert address that nobody reads: use one address forwarded to named people, as Cleveland does. And nothing watching the CRM directly: without the second uptime check, a CRM outage is noticed only when a delivery fails.

---

## 12.5 Add the chapter to the list of systems being watched

**Why:** The central support organization supports every chapter, and needs one place saying where each chapter's systems are and when they were last checked.

**Who:** The central support organization

**Finish first:**

- step 12.1 Back up the CRM server on a schedule
- step 12.2 Back up the application database on a schedule
- step 12.3 Restore from a backup once
- step 12.4 Confirm alerts reach a person

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Open the list of watched systems. It does not exist yet. Until the fleet console exists, create it once as `prds/chapter-network/watched-systems.md` in the software's code repository, one section per chapter.
2. Add a section for the chapter headed with its name, holding one line each for:
   - CRM address: the value of crm_base_url
   - Application address: the value of app_base_url
   - Hosting account: the DigitalOcean team name
   - CRM server backups: the schedule from step 12.1
   - Application database backups: the schedule from step 12.2
   - Alert readers: the names from step 12.4
   - Last restore test: the date from step 12.3

   *You should see:* Every line filled in. No password or key appears anywhere in the file.

**Done when:** The central support organization's list of systems includes this chapter's CRM and application.

**How to check:** The chapter is on the list, with every column filled in.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The list drifting from the truth. An old restore test date on the list is a chapter whose backups nobody has checked lately.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.4 | 09-23-26 20:40 | References to stage 9 follow its renumbering from twenty steps to nine (stage 9 version 0.11). |
| 0.3 | 09-23-26 14:27 | The placeholder CHAPTER-SLUG is now SHORT-LABEL, the form's own name for it (Doug, 09-23-26: slug is a terrible name for a user). The guide's index lists every shared placeholder. |
| 0.2 | 09-19-26 00:15 | Every action made precise (Doug, 09-19-26): exact doctl commands with named placeholders for backups, the restore test and the uptime and database alerts, flags checked against doctl's own help, and the restore copy's password never printed. |
| 0.1 | 09-18-26 17:30 | First version as data, converted from the methods for backups and monitoring (6-Methods-Backups-Monitoring.md, version 0.4) with the step list's finishing tests. |
