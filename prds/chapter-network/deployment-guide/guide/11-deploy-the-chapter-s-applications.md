# Stage 11 — Deploy the chapter's applications

**Version:** 0.1  
**Last Updated:** 09-18-26 17:20  
**Generated from** `steps/stage-11.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The applications are what the chapter's staff, mentors and the public actually use: the intake forms, the staff tools and the public events page. This stage deploys them into the chapter's own hosting account, connects them to the chapter's CRM and Google account, and sets them to take each weekly release by themselves. It ends by proving each Google connection works, one at a time.

**Who:** The central support organization, inside the chapter's hosting account.  
**Time:** About an hour for the deployment itself; the August build was active on the first attempt in seven minutes. The Google checks at the end are not timed yet.  
**When this stage is done:** Backups and monitoring can be set up (stage 12), and the chapter's website pages can be connected (stage 13).

**Before you start:**

- The chapter information form, complete and reviewed (stage 8)
- The CRM, built and matching the standard, with the applications' key in the vault (stage 9)
- The Google permissions and the Google key (stage 10)
- The chapter's domain names in its Cloudflare account (step 3.7)

**Steps in this stage:**

- 11.1 Generate the session secret
- 11.2 Generate the deployment settings
- 11.3 Load the secrets
- 11.4 Create the database
- 11.5 Create the application parts
- 11.6 Run the database setup
- 11.7 Deploy the released version
- 11.8 Set the update policy to Latest Stable
- 11.9 Confirm the application does not follow the development branch
- 11.10 Point the application's web address at the application
- 11.11 Publish the application at its own web address
- 11.12 Confirm the application is healthy
- 11.13 Confirm the application can read the CRM
- 11.14 Confirm incoming mail
- 11.15 Confirm outgoing mail
- 11.16 Confirm the calendar
- 11.17 Confirm the shared drive
- 11.18 Confirm a new mentor gets a mailbox

---

## 11.1 Generate the session secret

**Why:** The session secret protects every sign-in to the applications, so each chapter has its own.

**Who:** The central support organization

**Finish first:**

- step 2.7 Set up the chapter's password vault

**Do this:**

1. Generate a new random value of at least 48 characters. The settings generator (step 11.2) does this the first time it runs.
2. Put the value in the chapter's Operations vault.
   *You should see:* The session secret listed in the vault.

**Done when:** A new random session secret has been generated for this chapter alone and stored in the secrets store. It is never copied from another chapter.

**How to check:** The value is in the vault and differs from every other chapter's.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Copying another chapter's.

---

## 11.2 Generate the deployment settings

**Why:** The deployment settings are what the hosting platform builds the applications from, and every value must come from the reviewed form, not from memory.

**Who:** The central support organization

**Finish first:**

- step 8.9 Review the completed form
- step 9.17 Create the account the applications sign in with

**Do this:**

1. Run scripts/rehearsal/render_spec.py with the chapter information form, the secrets file and an output file name.
   *You should see:* A settings file written, containing the secret values in plain text.
2. Never commit the output file, and delete it once step 11.5 is done.
3. Move the stored-data encryption key the generator created into the chapter's Operations vault.
   *You should see:* The encryption key listed in the vault.

**Done when:** The settings are produced from the chapter information form and every value in them traces back to a line on that form.

**How to check:** Every value in the settings file matches a line on the form.

**If it didn't work:** The generator refuses to run when the CRM key or the administrator credentials are missing. Fetch them from the vault and run it again.

**What usually goes wrong:** The stored-data encryption key. The generator creates it quietly on first run, and changing it later destroys the data it protects, so it is permanent from the moment it exists. Also, the trial script asks for a development database, which takes no backups (see step 11.4), and it does not know the Google or Zoom values.

---

## 11.3 Load the secrets

**Why:** The applications need their secrets at start-up, and a secret left readable in a file is a secret leaked.

**Who:** The central support organization

**Finish first:**

- step 11.2 Generate the deployment settings

**Do this:**

1. Today the settings file from step 11.2 carries the secrets into the deployment. Nothing else to do.
2. After step 11.5, delete the settings file.
   *You should see:* No copy of the settings file left anywhere.

**Done when all of these are true:**

- Every secret is loaded into the deployment, including the Google key.
- The session secret is loaded.
- The stored-data encryption key is loaded.
- None of them appears in a file anyone can read.

**Note:** The database connection is not among them — the hosting platform supplies that to the application directly.

**How to check:** The application starts, and no settings file with secrets is left on any computer.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The settings file with plain-text secrets left on a laptop or committed. Getting the settings back from the platform afterwards does not help: the platform hands the secrets back scrambled into an unreadable form.

---

## 11.4 Create the database

**Why:** Every submission is saved in the application's database before it reaches the CRM, so the database must exist and take backups.

**Who:** The central support organization

**Finish first:**

- step 5.1 Create the server hosting account

**Do this:**

1. The database is created with the application in step 11.5, named after the chapter's short label.
2. Straight after step 11.5, open the application's settings in the hosting account and find the database part.
   *You should see:* Whether it says it is a managed database or a development database.
3. If it is a development database, convert it to a managed database, at the smallest size.
   *You should see:* The database shown as a managed database.

**Done when all of these are true:**

- The database exists in the chapter's hosting account.
- Its connection details are in the secrets store.
- The application can reach it.

**How to check:** The application connects, and the hosting account shows a managed database.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Leaving it as a development database. Nothing reports an error, and there are no backups. The trial chapter's database is in this state. Also, the hosting platform adds an instruction to the connection details that the application's database library rejects; the software strips it, so it only looks broken.

---

## 11.5 Create the application parts

**Why:** The applications run as three parts, and the background worker is the one that sends mail and finishes unfinished work.

**Who:** The central support organization

**Finish first:**

- step 11.2 Generate the deployment settings
- step 11.3 Load the secrets

**Do this:**

1. Run doctl apps create with the settings file from step 11.2, signed in to the chapter's hosting account.
   *You should see:* A new application with an identifier.
2. Open the application in the hosting account.
   *You should see:* Three parts listed — the web part, the delivery worker and the migrate setup job.

**Done when:** The web part, the background worker part and the setup job all exist.

**How to check:** All three parts appear in the hosting account.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Creating only the web part. Without the background worker the system looks fine and quietly does nothing.

---

## 11.6 Run the database setup

**Why:** The application cannot start until its database has the tables it expects.

**Who:** The central support organization

**Finish first:**

- step 11.5 Create the application parts

**Do this:**

1. Nothing to run. The setup job runs by itself before the application starts.
2. Open the deployment's log in the hosting account.
   *You should see:* The migrate job reported as successful.

**Done when:** The setup job has completed and the database holds the expected tables.

**How to check:** The deployment log shows the setup job succeeded.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 11.7 Deploy the released version

**Why:** Every chapter runs the same named release, so a support question never starts with "which version are you on".

**Who:** The central support organization

**Finish first:**

- step 11.6 Run the database setup

**Do this:**

1. Check the application follows the release branch, which always points at the latest release.
2. Open the application's health address, /healthz, in a browser.
   *You should see:* releaseTag set to the current release, for example v0.228.1, and version matching it.

**Done when:** The application is running the version the release schedule names, and it reports that version when asked.

**How to check:** /healthz shows releaseTag equal to the current release.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** releaseTag reads null. That means the application follows the development branch rather than the release branch. It is the honest answer, not a fault.

---

## 11.8 Set the update policy to Latest Stable

**Why:** Latest Stable makes the application take each weekly release by itself, so no chapter falls behind.

**Who:** The central support organization

**Finish first:**

- step 11.7 Deploy the released version

**Do this:**

1. Run scripts/set_updates_policy.py with the application's identifier and latest-stable, without the apply option.
   *You should see:* The plan it would apply to all three parts.
2. Run it again with the apply option and the deploy option. The deploy option starts a fresh deployment, without which the application stays one release behind while reporting itself healthy.
   *You should see:* All three parts changed.
3. Run it with the status option.
   *You should see:* All three parts read back as latest-stable, in agreement.

**Done when:** All three parts of the application follow the release branch and the policy script reads all three back in agreement. An application has three parts, each with its own setting, and setting one without the others half-updates it with no warning from the platform.

**How to check:** The status option reports all three parts in agreement.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Setting one part and not the others. Nothing on the platform tells you that you have half-updated it.

---

## 11.9 Confirm the application does not follow the development branch

**Why:** The development branch delivers untested software, and no chapter's live system may take it.

**Who:** The central support organization

**Finish first:**

- step 11.8 Set the update policy to Latest Stable

**Do this:**

1. Run scripts/set_updates_policy.py with the application's identifier and the status option.
   *You should see:* All three parts naming the release branch, and none naming main.

**Done when all of these are true:**

- No part of the deployment follows the main development branch.

**Note:** This replaces what the earlier planning documents said. Those documents require automatic deployment to be switched off on a chapter's application, which was right when the release version travelled inside each deployment's settings. The version is now stamped into the software itself when a release is cut, so an application following the release branch with automatic deployment on updates itself correctly. The danger was never automatic deployment — it is automatic deployment from the development branch, which delivers untested software straight to a chapter's live system.

**How to check:** All three parts name the release branch.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 11.10 Point the application's web address at the application

**Why:** People reach the applications by the chapter's own address, not the hosting platform's.

**Who:** The central support organization

**Finish first:**

- step 3.7 Move the domain names' DNS to the chapter's Cloudflare account
- step 11.5 Create the application parts

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the chapter's Cloudflare account, open the domain, then DNS, and add a CNAME record for the application's address, pointing at the address the hosting platform gave the application.
2. Set the record to "DNS only", the grey cloud.
   *You should see:* The record listed with a grey cloud.
3. In the hosting account, add the address to the application as its main domain.

**Done when:** The domain name record for the application address resolves to it.

**How to check:** A name lookup on the application's address returns the hosting platform's address for it.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The proxy switched on, an orange cloud. The hosting platform then cannot issue or renew the certificate. Also, straight after the record is created, some resolvers keep an earlier "no such address" answer for a while; wait rather than changing the record.

---

## 11.11 Publish the application at its own web address

**Why:** A secure connection protects every sign-in and every form submission.

**Who:** The central support organization

**Finish first:**

- step 11.10 Point the application's web address at the application

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Nothing to do. The hosting platform issues the certificate and renews it.
2. Open the application's address in a browser.
   *You should see:* The applications' sign-in page, with no certificate warning.

**Done when:** The application loads at its address over a secure connection, and the security certificate is set to renew by itself.

**How to check:** The page loads with no warning.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 11.12 Confirm the application is healthy

**Why:** The health address is the one place that shows, at a glance, that the application runs, knows whose it is, and has a working background worker.

**Who:** The central support organization

**Finish first:**

- step 11.7 Deploy the released version

**Do this:**

1. Open the application's address followed by /healthz, and read three things:
   - The organization: the chapter's own name.
   - releaseTag: the release.
   - The worker block: a recent heartbeat.
   *You should see:* All three as listed.
2. Read the crmConfig block.
   *You should see:*
   - {'A state of stamped or unstamped': 'both are fine'}
   - {'Not absent, forbidden or unreachable': 'each of those is a problem to report'}

**Done when all of these are true:**

- The application's health address reports it is running.
- The health address names the chapter correctly.
- The health address shows the background worker alive.

**How to check:** /healthz shows the chapter's name, a live worker and a readable CRM.

**If it didn't work:** Wait a minute and read it again before calling it a failure.

**What usually goes wrong:** Reading it before the new software has finished starting, which shows a failure that is not real. And Cleveland's name where the chapter's should be, which means the chapter name setting was not applied.

---

## 11.13 Confirm the application can read the CRM

**Why:** A permission missed in stage 9 shows up here as an empty screen rather than an error, so it is checked directly.

**Who:** The central support organization

**Finish first:**

- step 9.17 Create the account the applications sign in with
- step 11.12 Confirm the application is healthy

**Do this:**

1. Sign in to the applications and open a page that lists records, such as Client Administration.
   *You should see:* Records, or an empty list. Both are fine.

**Done when:** A request through the application returns CRM data.

**How to check:** The page shows records or an empty list, not a refusal.

**If it didn't work:** A refusal means a permission was missed in stage 9. Go back to steps 9.11 and 9.12.

**What usually goes wrong:** A page that asks for more than two hundred records at once is refused rather than trimmed, and inside the software that refusal reads as "there are no records". This once emptied every selection list on Cleveland's live system.

---

## 11.14 Confirm incoming mail

**Why:** Inbound email is the first Google connection, and if it fails nothing after it will work.

**Who:** The central support organization

**Finish first:**

- step 10.3 Enter the permission grant
- step 10.4 Name the mailbox the software acts as

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Confirm no other deployment reads the same shared operations mailbox.
2. Switch on the mail feature on the application's settings page, and restart the background worker.
3. Read the worker's log.
   *You should see:* A line naming the mailbox the worker is acting as, and it is the shared operations mailbox.
4. Send a message from an outside address to the shared operations mailbox.
   *You should see:* The message appearing against a record in the application.

**Done when:** A message sent to the shared operations mailbox appears in the application.

**How to check:** The log names the right mailbox and the test message appears in the application.

**If it didn't work:** If the log line is missing or names the wrong address, stop. The cause is in stage 10, not here.

**What usually goes wrong:** Two deployments reading the same mailbox. Each takes roughly half the messages, and neither is obviously broken.

---

## 11.15 Confirm outgoing mail

**Why:** Staff and mentors send email from records, and it must arrive with the chapter's own name.

**Who:** The central support organization

**Finish first:**

- step 11.14 Confirm incoming mail

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Open a record in the application and send a message from it to an outside address you can read.
   *You should see:* The message arriving, with the chapter's own name as the sender.

**Done when:** A message sent from a record arrives, and the sender shown is the chapter.

**How to check:** The test message arrives with the chapter's name.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The address the software sends warnings from must also be a real licensed mailbox. A group or alias is refused, and the refusal reads as though the machine account is not allowed at all.

---

## 11.16 Confirm the calendar

**Why:** Mentors' sessions are put on their Google calendars, with the right people invited.

**Who:** The central support organization

**Finish first:**

- step 11.14 Confirm incoming mail

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Switch on the calendar feature on the application's settings page.
2. Create a scheduled session through the application.
   *You should see:* The meeting on the mentor's calendar, with the invitations sent.

**Done when:** A meeting created through the application appears on the calendar with the right people invited.

**How to check:** The meeting is on the calendar and the invitations went out.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The calendar permission is a separate entry in the grant from step 10.3, and the one most often missed, because working mail makes everything look fine.

---

## 11.17 Confirm the shared drive

**Why:** Record documents are filed on the chapter's shared drive, so the application must be able to create folders there.

**Who:** The central support organization

**Finish first:**

- step 10.5 Create the shared drive and add the machine account
- step 11.14 Confirm incoming mail

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Switch on the documents feature on the application's settings page.
2. Create a record that should get a folder.
   *You should see:* The folder appearing on the shared drive.

**Done when:** The application creates a folder on the shared drive and it appears.

**How to check:** The folder is on the shared drive.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The service account is not a member of the shared drive, or the drive's identifier on the form is wrong. Both give silence, not an error.

---

## 11.18 Confirm a new mentor gets a mailbox

**Why:** This last check exercises the most — the directory permissions, the mentor email domain and the approval process — and it is what each new mentor will depend on.

**Who:** The central support organization

**Finish first:**

- step 10.3 Enter the permission grant
- step 11.14 Confirm incoming mail

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Switch on the mentor account switches on the application's settings page, including the Google directory check.
2. In Mentor Administration, take a test mentor through approval.
   *You should see:* A new mailbox created on the chapter's mentor email domain.
3. Sign in to the new mailbox.
   *You should see:* The mailbox opens.
4. Remove the test mentor's mailbox and records afterwards.

**Done when:** A mentor taken through approval ends up with a real working mailbox on the chapter's mentor email domain.

**How to check:** The new mailbox exists and the mentor can sign in to it.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Two directory permissions are needed, reading and changing. A grant with only the reading one gets all the way to this step before failing. And the mentor email domain is a setting somebody has to fill in; a chapter whose mentor addresses are on a different domain from its staff addresses has to say so.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for deploying the applications (3-Methods-CRM-Google-Applications.md, version 0.5) with the step list's finishing tests. Numbered actions, a reason per step, and a check an app can run were added. |
