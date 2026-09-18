# Stage 12 — Set up backups and monitoring

**Version:** 0.1  
**Last Updated:** 09-18-26 17:30  
**Generated from** `steps/stage-12.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

This stage makes sure the chapter's records can be got back after a mistake or a failure, and that a person finds out when the system stops working. It comes before any real records are loaded, because a backup taken afterwards is too late for whatever went wrong before it.

**Who:** The central support organization, working inside the chapter's hosting account. The chapter names who reads the alerts.  
**Time:** About two hours, most of it waiting for a restored copy to be built.  
**Before you start:** The CRM server (stage 9); The applications and their database (stage 11); Outgoing mail working, for the alert emails (step 11.15); The decision about who receives warning messages (step 4.9)  
**When this stage is done:** The chapter's pages can go on its website (stage 13), and real records can be loaded (stage 15).

**Steps in this stage:** 12.1 Back up the CRM server on a schedule, 12.2 Back up the application database on a schedule, 12.3 Restore from a backup once, 12.4 Confirm alerts reach a person, 12.5 Add the chapter to the list of systems being watched

---

## 12.1 Back up the CRM server on a schedule

**Why:** A backup of the whole server holds the CRM's database, its uploaded files and its configuration together, so one restore brings back all three.

**Who:** The central support organization inside the chapter's hosting account  
**Finish first:** step 9.2

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the chapter's hosting account, open the CRM server, then its Backups tab.
2. Switch backups on and choose daily.
   *You should see:* Backups shown as enabled, with a daily schedule and a backup window.
3. Write down the schedule, the backup window and how many days each backup is kept, on the chapter's entry in the list of watched systems (step 12.5).

**Done when:** Backups run automatically, and the schedule and how long backups are kept are written down.

**How to check:** The next morning, the Backups tab lists a backup taken overnight.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Two things. Seven days is short: a mistake nobody notices for eight days cannot be undone from these backups. And backups cost extra and are easy to leave off, because the deployment wizard does not switch them on.

---

## 12.2 Back up the application database on a schedule

**Why:** Submissions that have arrived but not yet reached the CRM exist only in this database, so losing it loses them.

**Who:** The central support organization inside the chapter's hosting account  
**Finish first:** step 11.4

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the chapter's hosting account, open the application's settings and find its database.
   *You should see:* The database described as a managed database.
2. If it is described as a development database instead, convert it to a managed database there, at the smallest size.
   *You should see:* The database described as a managed database. The application keeps running during the change.
3. Open the database's Backups tab.
   *You should see:* Daily backups, each kept seven days.
4. Write the schedule and retention on the chapter's entry in the list of watched systems.

**Done when:** Backups run automatically, and the schedule and retention are written down.

**How to check:** The database's Backups tab lists a backup taken in the last day.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A development database that nobody notices. Everything works, no error appears, and there are no backups. The trial chapter's database is in this state.

---

## 12.3 Restore from a backup once

**Why:** A backup nobody has restored is only a hope, so each kind is restored once into a separate copy and checked.

**Who:** The central support organization  
**Finish first:** step 12.1, step 12.2

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. For the database, restore into a new database with the hosting provider's command-line tool, `doctl databases fork`, naming the live database as the source. It never restores over the live one.
   *You should see:* A new database, listed as online. Do not show or save the address the tool prints; it carries the administrator password.
2. Allow your own computer through the new database's firewall. It copies the live database's firewall, which lets only the application in.
3. Connect to the new database and count the rows in every table.
   *You should see:* Every table present and holding data, and the newest submission recent.
4. Delete the new database the same hour. It holds the chapter's real personal details.
5. For the CRM server, create a new server from the latest backup in the server's Backups tab.
6. Open the new server's own address in a browser, sign in as the central support organization's administrator, and open one recent record.
   *You should see:* The record, as it was at the time of the backup.
7. Delete the new server.
8. Write down the date, what was checked and how long each restore took.

**Done when:** A restore has actually been performed and the result checked. An untested backup is not a backup.

**How to check:** Both copies started and held the expected records, and the test is written down.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A restore with no date given rebuilds the database to the latest moment it can, not to the last daily backup. That is better, but it means the two are the same command. Also, the restored copy holds real personal details, so it is printed as counts and dates only and deleted the same hour.

---

## 12.4 Confirm alerts reach a person

**Why:** When the system stops working or submissions pile up, somebody has to be told, and an alert nobody reads is the same as no alert.

**Who:** The chapter and the central support organization — the central support organization sets it up; the chapter names who reads the alerts  
**Finish first:** step 4.9, step 11.15

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Create an uptime check on the application's health address with the hosting provider's command-line tool, `doctl monitoring uptime create`, and an alert on it that emails the alert address after two minutes down.
   *You should see:* The check listed as enabled.
2. Create a second uptime check the same way on the CRM's own address, with the same alert.
   *You should see:* Two checks listed, one for the application and one for the CRM.
3. Add database alerts for processor, memory and disk above 90 per cent, emailing the same address.
4. Send a test alert from the application. There is no button for this yet. Open a console on the background worker in the hosting account and run the software's own alert sender with a test message.
   *You should see:* The test alert arrives at the alert address.
5. Write down the names of the people who read the alert address.

**Done when:** A test alert arrives at an address somebody reads, and it is recorded who reads it.

**How to check:** The test alert arrives, and a named person confirms they saw it.

**If it didn't work:** If no test alert arrives, check the Google connection first. The application sends its alerts through the chapter's Google account.

**What usually goes wrong:** Three things. A chapter with the Google connection switched off gets no alert emails at all, and nothing says so. An alert address that nobody reads: use one address forwarded to named people, as Cleveland does. And nothing watching the CRM directly: without the second uptime check, a CRM outage is noticed only when a delivery fails.

---

## 12.5 Add the chapter to the list of systems being watched

**Why:** The central support organization supports every chapter, and needs one place saying where each chapter's systems are and when they were last checked.

**Who:** The central support organization  
**Finish first:** step 12.1, step 12.2, step 12.3, step 12.4

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Open the list of watched systems, kept in the chapter-network folder of the software's code repository until the fleet console exists.
2. Add the chapter, with its CRM address, its application address, the hosting account it lives in, both backup schedules, who reads the alerts, and the date of the last restore test.
   *You should see:* Every column filled in for the chapter.

**Done when:** The central support organization's list of systems includes this chapter's CRM and application.

**How to check:** The chapter is on the list, with every column filled in.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The list drifting from the truth. An old restore test date on the list is a chapter whose backups nobody has checked lately.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:30 | First version as data, converted from the methods for backups and monitoring (6-Methods-Backups-Monitoring.md, version 0.4) with the step list's finishing tests. |
