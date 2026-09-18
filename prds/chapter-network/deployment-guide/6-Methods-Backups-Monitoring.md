# New Chapter Deployment Guide — Methods for Backups and Monitoring

**Document:** The written-out steps for one stage — setting up backups and
monitoring (stage 12)
**Version:** 0.3
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-18-26 01:40

---

## What this is

The stage that makes sure a chapter's records can be got back, and that a person
finds out when the chapter's system stops working. It sits after deploying the
applications and before any real records are loaded. A backup taken after the first
real records arrive is too late for whatever went wrong before it.

None of this stage was covered by the August build of the trial chapter. It is
written from what Cleveland runs today, which was read directly from Cleveland's
hosting account on 09-18-26 rather than taken from the documents. Where Cleveland's
own practice falls short, the step says so.

Each step carries the same eight headings as the other methods documents.

**What writing this stage found** is set out at the end. The short version: until
09-18-26 nobody had ever restored a backup of any system in this project,
Cleveland's included. The application database has now been restored once, on
Cleveland's production system, and it worked. The CRM server has still never been
restored. And the trial chapter's application database was created on a tier that
takes no backups at all.

---

# Stage 12 — Set up backups and monitoring

**Stage status: not yet tried on any chapter.** Steps 12.1, 12.2 and 12.4 are done
for real on Cleveland's production system. Step 12.3 is done for real for the
application database only, on Cleveland's production system on 09-18-26.

---

### 12.1 Back up the CRM server on a schedule

**Done when:** backups run automatically, and the schedule and how long backups are
kept are written down.

**Who:** central support organization, inside the chapter's hosting account.

**First:** the CRM server exists (step 9.2).

**How to do it today:** in the hosting account, open the CRM server's Backups tab.
Switch backups on and choose daily. Write down the schedule, the backup window and
how many days each backup is kept. The hosting provider backs up the whole server,
so a backup holds the CRM's database, its uploaded files and its configuration
together.

Cleveland's production CRM server does exactly this. On 09-18-26 it read: daily
backups, taken between 04:00 and 08:00 UTC, each kept for seven days.

**How it will be done later:** the fleet console switches backups on when it
creates the server, and shows the date of the latest backup for every chapter.

**How you know it worked:** the next morning, the Backups tab lists a backup taken
overnight.

**What goes wrong:** two things.

The first: seven days is short. A problem that nobody notices for eight days, such
as records quietly deleted by a mistake, cannot be undone from these backups. A
longer copy kept somewhere else would close this gap. It is not built.

The second: backups cost extra on top of the server's price, and they are easy to
leave off when the server is created. The deployment tool's wizard does not switch
them on. Cleveland's test system has them off, which is deliberate there because it
restores itself every night from a fixed copy.

**Status:** done for real on Cleveland's production CRM. Not tried on the trial
chapter's server, which was not checked.

---

### 12.2 Back up the application database on a schedule

**Done when:** backups run automatically, and the schedule and retention are written
down.

**Who:** central support organization, inside the chapter's hosting account.

**First:** the database exists (step 11.4).

**How to do it today:** the application database must be a managed database, not a
development database. A development database takes no backups at all. Check this in
the hosting account under the application's settings: the database component must
say it is a managed database. If it does not, convert it there. Choose the
smallest size. Cleveland converted its production database this way on 23 July 2026
without the application stopping. A managed database is backed up daily and each
backup is kept for seven days. It can also be restored to any moment in that week.

**How it will be done later:** the settings generator creates a managed database
from the start, so there is nothing to convert.

**How you know it worked:** the database's Backups tab lists a backup taken in the
last day.

**What goes wrong:** creating a development database and not noticing. Everything
works, nothing reports an error, and there are no backups. The trial chapter's
database was created this way, because the settings generator used in August asks
for a development database. Submissions that have arrived but not yet reached the
CRM exist only in this database. Losing it while the CRM is down loses those
submissions for good.

**Status:** done for real on Cleveland's production database. Not done on the trial
chapter, whose database takes no backups.

---

### 12.3 Restore from a backup once

**Done when:** a restore has actually been performed and the result checked. An
untested backup is not a backup.

**Who:** central support organization.

**First:** steps 12.1 and 12.2, and at least one backup of each.

**How to do it today:** never restore over the live system to test. Restore into a
new copy, check the copy, then delete it.

For the CRM server: in the Backups tab, create a new server from the latest backup.
When it starts, open the new server's own address in a browser and sign in as the
central support organization's administrator. Check that a recent record is there.
Then delete the new server.

For the application database: restore it into a new database with the hosting
provider's command-line tool (`doctl databases fork`), naming the live database as
the source. The hosting provider always restores into a new database, never over the
existing one. Allow your own computer through the new database's firewall, connect
to it, and count the rows in every table. Every table should be there and hold data,
and the newest submission should be recent. Then delete the new database.

The restored copy holds the chapter's real records, including personal details. Do
it from a computer the central support organization controls, print counts and
dates only, and delete the copy the same hour. Never print the new database's
address: the hosting provider's address for it carries the administrator password.

Write down the date, how long each restore took, and what was checked.

**How it will be done later:** the fleet console runs a restore test on a schedule
and reports the result.

**How you know it worked:** both copies started and held the expected records, and
the record of the test is written down.

**What goes wrong:** for the application database, three things were learned on
09-18-26.

The first: a restore with no date given does not use the last daily backup. It
rebuilds the database to the latest moment it can. The test copy held a submission
received eight hours after the last daily backup. That is better, not worse, but
it means "restore the latest backup" and "restore to now" are the same command.

The second: the hosting provider's output after the restore includes the new
database's address with its password. A script that shows that output to the screen
leaks the password. The test did exactly that. The password was for the copy only,
and stopped working when the copy was deleted.

The third: the new database copies the live database's firewall, which admits only
the application. You have to add your own computer before you can connect.

For the CRM server, nothing is known, because it has never been restored.

What is known about using a restore for real: a database restore produces a new database address, and using it for
real means changing the application's settings and redeploying. The software is
built to survive that. Deliveries resume where they stopped rather than repeating,
and a submission replayed twice is recognised the second time.

**Status:** done for real for the application database, on Cleveland's production
system on 09-18-26. How long the restore took was not timed. The copy held all 20 tables,
179 submissions and 1,690 email threads, and its newest submission was from
09-17-26 17:06 UTC, eight hours after the last daily backup. The copy was deleted
the same hour. The CRM server restore is not yet tried anywhere.

---

### 12.4 Confirm alerts reach a person

**Done when:** a test alert arrives at an address somebody reads, and it is recorded
who reads it.

**Who:** central support organization; the chapter names who reads the alerts.

**First:** the warning-message decision (step 4.9), and outgoing mail confirmed
(step 11.15).

**How to do it today:** there are two kinds of alert, and both need checking.

The first kind comes from the application itself. The background worker watches
for undelivered submissions, submissions that have waited too long, and failures.
It emails the addresses on the chapter information form. These emails are sent
through the chapter's Google account, so they work only once the Google connection
is working. With no way to send, an alert is written to the application's log and
nobody sees it. There is no test button. To send a test alert, open a console on the
worker in the hosting account and run a single command that calls the software's
own alert sender with a test message. Cleveland's runbook for running a command
inside the deployed application covers how.

The second kind comes from the hosting provider. Create an uptime check on the
application's health page, and an alert on it that emails a person when the page
stops answering. Cleveland has exactly this on its production application: the
check fires after two minutes down. Add alerts on the database for disk, memory and
processor above 90 per cent, which Cleveland also has.

**How it will be done later:** a "send a test alert" button on the settings page.

**How you know it worked:** the test alert arrives, and a named person confirms they
saw it.

**What goes wrong:** three things.

The first: a chapter with the Google connection switched off gets no alert emails at
all, and nothing says so. The trial chapter is in this state.

The second: the address alerts go to is a group, and nobody in the group reads it.
Cleveland's hosting alerts go to a group address. That works for receiving mail,
but the step is only finished when a named person is known to read it.

The third: nothing watching the CRM directly. The application notices a CRM that
is down only when a delivery fails, which needs a submission to arrive first. Add a
second uptime check on the CRM's own address, with the same two-minute down alert.
Cleveland had only the application check until 09-18-26.

**Status:** done for real on Cleveland's production system. The CRM uptime check
(`cbm-crm-prod-up`, on the CRM's home page, alerting after two minutes down) was
added on 09-18-26. No test alert has been sent for either check. Not tried on any
chapter.

---

### 12.5 Add the chapter to the list of systems being watched

**Done when:** the central support organization's list of systems includes this
chapter's CRM and application.

**Who:** central support organization.

**First:** steps 12.1 to 12.4.

**How to do it today:** there is no such list. Cleveland's three applications are
listed by hand in the software's own orientation file, with their addresses and
identifiers. Until the fleet console exists, keep one written list in the
chapter-network folder of the software's code repository. For each chapter, record
the CRM address, the application address, the hosting account it lives in, the
backup schedules, who reads the alerts, and the date of the last restore test.

**How it will be done later:** the fleet console is the list. It reads each
chapter's health page and shows every chapter on one screen.

**How you know it worked:** the chapter is on the list, with every column filled in.

**What goes wrong:** the list drifts from the truth. Recording the date of the last
restore test is what keeps the list honest. An entry with an old date is a
chapter whose backups nobody has checked lately.

**Status:** not yet tried. The list does not exist.

---

## What writing this stage found

**1. Nobody had ever restored a backup.** The backups ran every day and had never
been checked, on Cleveland or anywhere else. On 09-18-26 Cleveland's production
application database was restored into a new copy, checked and deleted, and it
worked (step 12.3). The CRM server has still never been restored. That is the
larger risk, because the CRM holds the records themselves.

**2. The trial chapter's database takes no backups.** The settings generator used in
August (`scripts/rehearsal/render_spec.py`) asks for a development database. Step
11.4 in the deployment methods should say "managed database", and the generator
should ask for one.

**3. Nothing watched the CRM directly.** Cleveland had an uptime check on its
application and none on its CRM. One was added on 09-18-26, emailing the same
address as the application's check.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.3 | 09-18-26 01:40 | An uptime check on Cleveland's production CRM added on 09-18-26, closing finding 3. Step 12.4 updated to match. |
| 0.2 | 09-18-26 01:35 | Step 12.3 is now done for real for the application database. Cleveland's production database was restored into a new copy, checked and deleted on 09-18-26. The method was rewritten from what happened, with three things learned: a restore with no date rebuilds to the latest moment rather than the last daily backup; the hosting provider's output carries the copy's password; and the copy inherits a firewall that must be opened. The CRM server restore is still untried. |
| 0.1 | 09-18-26 01:15 | First draft of the methods for setting up backups and monitoring. Written from Cleveland's production hosting account, read directly on 09-18-26: daily CRM server backups kept seven days, a managed application database with daily backups kept seven days, an uptime check with an alert on the application, and processor, memory and disk alerts on the databases. Three findings: no backup has ever been restored, the trial chapter's database takes no backups, and nothing watches the CRM directly. |
