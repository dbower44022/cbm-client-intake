# Stage 11 — Deploy the chapter's applications

**Version:** 0.8  
**Last Updated:** 09-23-26 14:27  
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
- The chapter's domain names in its Cloudflare account, or at its own DNS provider with manual DNS (step 3.7)
- The chapter's hosting account linked to the code repository on GitHub (step 5.9)

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

1. Nothing to run by hand. The settings generator in step 11.2 creates the session secret the first time it runs, as a random value of 48 bytes, and appends it to the chapter's settings file (CHAPTER-ENV-FILE, which is ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env).
2. After step 11.2, open CHAPTER-ENV-FILE in a text editor, copy the value after SESSION_SECRET= into a new item in the chapter's Operations vault named Session secret, and save.
   *You should see:* The Session secret item in the Operations vault.

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

1. Before running it, check CHAPTER-ENV-FILE already holds these three lines, written by the script in step 9.10:
   - ESPO_API_KEY=
   - ESPO_PROVISION_USERNAME=
   - ESPO_PROVISION_PASSWORD=
2. Download the Google machine account key from the chapter's Operations vault (step 10.2) and save it as ~/.config/cbm-SHORT-LABEL/google-key.json. Then add this line to the end of CHAPTER-ENV-FILE. The file is named rather than pasted because the key runs over several lines, which would break the build commands that read CHAPTER-ENV-FILE:
   - GOOGLE_SERVICE_ACCOUNT_KEY_FILE=~/.config/cbm-SHORT-LABEL/google-key.json
3. Check the form's flags section names every switch deliberately, as true or false. The Google switches (gmail_sync, gcal_events, gdrive_docs, google_directory_check, google_create_mailbox) go into the deployment from here, not from the settings page: the background worker decides at start-up whether to read the mailbox, and a switch set later at /setup never reaches it. Set gdrive_identity to service, and set deploy_on_push to true so the application follows the release branch from its first build.
4. In a terminal, in the folder ~/Dropbox/Projects/cbm-client-intake, type the line below and press Enter. CHAPTER-VALUES-FILE is the filled-in chapter information form saved as YAML (the trial chapter's is prds/chapter-network/rehearsal-2026-08-31/lakeside-values.yaml):
   - uv run python scripts/rehearsal/render_spec.py CHAPTER-VALUES-FILE ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env ~/.config/cbm-SHORT-LABEL/SHORT-LABEL-app.yaml
   *You should see:* A line reading: wrote ~/.config/cbm-SHORT-LABEL/SHORT-LABEL-app.yaml following branch release with N shared + N web-only env vars. If it reads secrets not yet minted, step 9.10 has not run. If it names GOOGLE_SERVICE_ACCOUNT_KEY_FILE or shared_drive_id, a Google switch is on before stage 10 has produced what it needs.
5. Open SHORT-LABEL-app.yaml and check three things. The generator sets them itself; this is a check, not an edit:
   - There is no ENV_LABEL line.
   - ALLOWED_ORIGINS is https://APP-ADDRESS, or absent if the application address is not known yet.
   - Every branch line reads branch: release (the web part, the worker and the migrate job).
   - No value names Cleveland or cbmentors.org. The chapter's own website, mentor email domain and mailbox addresses appear instead.
6. Open CHAPTER-ENV-FILE and copy the value after APP_ENCRYPTION_KEY= into a new item in the chapter's Operations vault named Stored-data encryption key. This value must never change.
   *You should see:* The Stored-data encryption key item in the Operations vault.
7. Never commit SHORT-LABEL-app.yaml anywhere. It holds secrets in plain text. It is deleted in step 11.3.

**Done when:** The settings are produced from the chapter information form and every value in them traces back to a line on that form.

**How to check:** Every value in the settings file matches a line on the form.

**If it didn't work:** The generator refuses to run when the CRM key or the administrator credentials are missing. Fetch them from the vault and run it again.

**What usually goes wrong:** The stored-data encryption key. The generator creates it quietly on first run, and changing it later destroys the data it protects, so it is permanent from the moment it exists. Also, the trial script asks for a development database, which takes no backups (see step 11.4). A form field written as "none yet" is left out of the settings, so the software's own default applies until the field is filled in and the settings are generated again.

---

## 11.3 Load the secrets

**Why:** The applications need their secrets at start-up, and a secret left readable in a file is a secret leaked.

**Who:** The central support organization

**Finish first:**

- step 11.2 Generate the deployment settings

**Do this:**

1. Nothing to run. The settings file from step 11.2 carries every secret into the deployment when step 11.5 creates the application. The database connection is supplied by the hosting platform and never appears in the file.
2. After step 11.5 has succeeded, type the line below and press Enter, to delete the settings file:
   - rm ~/.config/cbm-SHORT-LABEL/SHORT-LABEL-app.yaml ~/.config/cbm-SHORT-LABEL/google-key.json
   *You should see:* The prompt again, with no message.
3. Check every secret in CHAPTER-ENV-FILE also has an item in the Operations vault. Then delete CHAPTER-ENV-FILE too, once the vault holds everything.
   *You should see:* No settings file and no secrets file left on the computer.

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

1. Nothing to run. Step 11.5 creates the database with the application, named SHORT-LABEL-db.
2. Straight after step 11.5, sign in to the chapter's hosting account at cloud.digitalocean.com and open Apps, then SHORT-LABEL-intake, then Settings, then the component SHORT-LABEL-db. The path is the one Cleveland used on 23 July 2026 (DEPLOYMENT.md).
   *You should see:* Either a managed database, or a development database with an option to convert it.
3. If it is a development database, choose Database Type and Scale, then Convert to a Managed Database, and choose:
   - Plan: the smallest node size (db-s-1vcpu-1gb)
   - Nodes: 1
   - Standby node: none
   *You should see:* The conversion completing and the application redeploying by itself, with no downtime. The connection details do not change.

**Done when all of these are true:**

- The database exists in the chapter's hosting account.
- Its connection details are supplied to the application by the hosting platform, and no person holds them.
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
- step 5.9 Link the hosting account to the code repository

**Do this:**

1. If this computer has never been signed in to the chapter's hosting account, type the line below and press Enter, then paste the chapter's DigitalOcean token from the Operations vault when asked:
   - doctl auth init --context SHORT-LABEL
   *You should see:* A message that the token was validated.
2. Type the line below and press Enter, so every following doctl command acts on the chapter's account and not Cleveland's:
   - doctl auth switch --context SHORT-LABEL
3. Type the line below and press Enter:
   - doctl apps create --spec ~/.config/cbm-SHORT-LABEL/SHORT-LABEL-app.yaml
   *You should see:* A table with the new application's ID and the name SHORT-LABEL-intake. Copy the ID into the Operations vault as a note named Application ID; later steps call it APP-ID.
4. Type the line below and press Enter:
   - doctl apps get APP-ID
   *You should see:* The application listed. In the hosting account's web page, its Components show web, delivery-worker and migrate.

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

1. Nothing to run. The migrate job runs by itself before the application starts.
2. Type the line below and press Enter:
   - doctl apps list-deployments APP-ID
   *You should see:* The first deployment in the list with its phase ACTIVE. A phase of ERROR means the migrate job or the build failed; open the deployment in the hosting account's web page and read its log.

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

1. Open https://APP-ADDRESS/healthz in a browser. Until step 11.10, use the address DigitalOcean gave the application, shown by doctl apps get APP-ID under Default Ingress.
   *You should see:*
   - status: ok
   - version: the current release's number, the one the release branch holds today
   - releaseTag: the same release with a v in front. The application follows the release branch from its first build, so it reads the tag straight away. A null here means the release branch's latest commit is not a cut release.

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

1. In the folder ~/Dropbox/Projects/cbm-client-intake, with doctl switched to the chapter's account (step 11.5), type the line below and press Enter. It changes nothing:
   - uv run python scripts/set_updates_policy.py APP-ID latest-stable
   *You should see:* The change it would make to each of the three parts.
2. Type the line below and press Enter. The deploy option starts a fresh deployment; without it the application rebuilds the same commit it already runs:
   - uv run python scripts/set_updates_policy.py APP-ID latest-stable --apply --deploy
   *You should see:* The spec updated and a new deployment started.
3. Type the line below and press Enter:
   - uv run python scripts/set_updates_policy.py APP-ID latest-stable --status
   *You should see:* One line per part, each showing branch=release and deploy_on_push=True, and a final line reading conformant with 'latest-stable'.

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

1. Type the line below and press Enter:
   - uv run python scripts/set_updates_policy.py APP-ID latest-stable --status
   *You should see:* Every part showing branch=release, none showing branch=main, and the line conformant with 'latest-stable'.

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

1. Type the line below and press Enter, and copy the address shown under Default Ingress (it ends .ondigitalocean.app):
   - doctl apps get APP-ID
2. In the chapter's Cloudflare account, open the domain, then DNS, then Records, and choose Add record. Enter exactly:
   - Type: CNAME
   - Name: the first part of the application's address, for example apps
   - Target: the Default Ingress address, without https://
   - Proxy status: DNS only (grey cloud)
   - TTL: Auto
   *You should see:* The record listed with a grey cloud.
3. With manual DNS (step 3.7), add the same CNAME record in the chapter's DNS provider account instead, with any proxy or forwarding off. Its screens differ by provider and are not given here; the Name and Target are the same.
4. In the hosting account, open Apps, then SHORT-LABEL-intake, then Settings, then Domains, and add APP-ADDRESS. Choose to manage DNS yourself and make it the primary domain. Labels are not checked on screen for this guide.
   *You should see:* The domain listed, moving to Active once the certificate is issued.

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

1. Nothing to do. The hosting platform issues the certificate and renews it by itself.
2. Open https://APP-ADDRESS in a private browser window.
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

1. Open https://APP-ADDRESS/healthz in a browser and read these fields:
   - status: ok
   - organization: the chapter's own name, not Cleveland's
   - releaseTag: the current release
   - database: ok
   - worker, then lastHeartbeatAgeSeconds: under 180
   *You should see:* All five as listed.
2. Read the crmConfig block's state field.
   *You should see:*
   - stamped or unstamped: both are fine
   - absent, forbidden or unreachable: each is a problem to report

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

1. Open https://APP-ADDRESS and sign in with the CRM administrator account the deployment wizard created in step 9.2. Its name and password are in the Operations vault.
2. Open Client Administration.
   *You should see:* Records, or an empty list. Both are fine. A message that access was refused means a permission was missed in stage 9.

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

1. Confirm no other deployment reads the same shared operations mailbox. Only one deployment may read a given mailbox.
2. Every Google setting in steps 11.14 to 11.18 reached the application from the form in step 11.2. Sign in to https://APP-ADDRESS/setup as a CRM administrator and confirm these show the chapter's values:
   - GOOGLE_SERVICE_ACCOUNT_JSON: shown as set
   - OPS_MAILBOX: the shared operations mailbox address
   - COMMS_INTERNAL_DOMAINS: the chapter's email domain, and the mentors' domain when it differs
   - GMAIL_SYNC: true
   *You should see:* Each value as listed. Do not change them here.
3. If a value is missing or wrong, correct the form, run step 11.2 again, then type the two lines below, pressing Enter after each. The first loads the new settings; the second restarts the worker, which reads its mail switches only at start-up:
   - doctl apps update APP-ID --spec ~/.config/cbm-SHORT-LABEL/SHORT-LABEL-app.yaml
   - doctl apps create-deployment APP-ID
   *You should see:* A new deployment reaching ACTIVE. Delete the settings file and the key file again afterwards, as in step 11.3.
4. In the hosting account, open Apps, then SHORT-LABEL-intake, then Runtime Logs, and choose the delivery-worker component.
   *You should see:* A line naming the mailbox the worker acts as, and it is the shared operations mailbox. If that line is absent or names another address, stop; the cause is in stage 10.
5. From an outside address, send a message to the shared operations mailbox.
   *You should see:* Within about five minutes, the message in Submission Admin as a new email submission.

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

1. At https://APP-ADDRESS/setup, confirm these show the chapter's values. If not, correct them the way step 11.14 describes:
   - ALERT_EMAIL_FROM: the alert sending mailbox (step 4.8)
   - ALERT_EMAIL_TO: the alert receiving address (step 4.9)
2. Open a record in the application and send a message from it to an outside address you can read.
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

1. At https://APP-ADDRESS/setup, confirm this shows true. If not, correct it the way step 11.14 describes:
   - GCAL_EVENTS: true
2. This check needs a mentor with a login and an assigned client, and none exists until stage 15. Create them now: the test mentor from step 17.1, then a test application and its assignment from steps 17.3 and 17.4, using the made-up values those steps give. Step 17.9 removes them.
3. Sign in as a mentor, open a client in Client Management, and create a session with Status Scheduled and a start time tomorrow.
   *You should see:* The meeting on the mentor's Google calendar, with the client's contacts invited and a Meet link attached.

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

1. At https://APP-ADDRESS/setup, confirm these show the chapter's values. If not, correct them the way step 11.14 describes:
   - GDRIVE_SHARED_DRIVE_ID: the shared drive identifier (step 10.5)
   - GDRIVE_IDENTITY: service
   - GDRIVE_DOCS: true
2. Open a client in Client Management, open its Documents tab, and upload a small test file.
   *You should see:* The file listed on the Documents tab, and a folder for that client on the shared drive holding it.

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

1. At https://APP-ADDRESS/setup, confirm these show the chapter's values. If not, correct them the way step 11.14 describes:
   - MENTOR_EMAIL_DOMAIN: the domain mentors' mailboxes are made on
   - GOOGLE_DELEGATED_ADMIN: the chapter's Google administrator address (step 4.5). The directory calls act as this administrator.
   - GOOGLE_MEMBERS_GROUP: the members group address (step 4.10), or empty to skip the group step
   - GOOGLE_DIRECTORY_CHECK: true
   - GOOGLE_CREATE_MAILBOX: true
   - MENTOR_PROVISION_USERS: true
2. In Mentor Administration, create a test mentor with a first and last name no real mentor has, and set Mentor Status to Accepted-Provisional.
   *You should see:* The status window reporting the mailbox created, and a temporary password shown once. Copy it into the Operations vault.
3. Sign in at mail.google.com as the new mentor address, with the temporary password.
   *You should see:* The mailbox opens and asks for a new password.
4. Delete the test mentor's mailbox in admin.google.com, then the test mentor record and its contact in the CRM.
5. Switch doctl back to the account you use for Cleveland, so the next doctl command does not act on the chapter's account. Type the line below to see the account names, then the second with the right one:
   - doctl auth list
   - doctl auth switch --context CLEVELAND-CONTEXT

**Done when:** A mentor taken through approval ends up with a real working mailbox on the chapter's mentor email domain.

**How to check:** The new mailbox exists and the mentor can sign in to it.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Two directory permissions are needed, reading and changing. A grant with only the reading one gets all the way to this step before failing. And the mentor email domain is a setting somebody has to fill in; a chapter whose mentor addresses are on a different domain from its staff addresses has to say so.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.8 | 09-23-26 14:27 | The placeholder CHAPTER-SLUG is now SHORT-LABEL, the form's own name for it (Doug, 09-23-26: slug is a terrible name for a user). The guide's index lists every shared placeholder. |
| 0.7 | 09-23-26 13:54 | Manual DNS added (Doug, 09-23-26): step 11.10 adds the application's CNAME record at the chapter's own DNS provider when the chapter kept it. |
| 0.6 | 09-23-26 12:25 | Step 11.5 now waits for step 5.9, the hosting account's link to the code repository on GitHub, without which creating the application fails. |
| 0.5 | 09-23-26 00:55 | From the review before the first real chapter. Every Google, mail, Drive, website and Zoom setting now goes into the deployment in step 11.2, from the form, and steps 11.14 to 11.18 confirm them at /setup instead of setting them there: the background worker decides at start-up from its own settings whether to read the mailbox, so a switch set at /setup never reached it. The Google key is named by file (GOOGLE_SERVICE_ACCOUNT_KEY_FILE), and step 11.3 deletes the file. The stored-data encryption key the generator creates is now one the software accepts; before, /setup refused to store any secret. Step 11.7 no longer names a release that does not exist, and step 11.16 creates the test mentor and client it needs. Step 11.18 switches doctl back. |
| 0.4 | 09-19-26 14:45 | Step 11.4's finishing test now matches step 11.3: the hosting platform supplies the database connection to the application, and no person holds it (Doug, 09-19-26). |
| 0.3 | 09-19-26 00:50 | The settings generator no longer writes the trial chapter's footer label, a localhost origin or the development branch, so the step that corrected them by hand is now a check. It refuses the development branch unless the form allows it. |
| 0.2 | 09-19-26 00:07 | Every action made exact (Doug, 09-19-26: sweep every step): the settings generator's command line and the three values in its output that are wrong for a real chapter (the Rehearsal label, the localhost origin, and the main branch); doctl commands against the chapter's own account; the managed database conversion path; the release policy commands; the Cloudflare record; the health page's exact fields; and the settings each Google check switches on at /setup, including GOOGLE_DELEGATED_ADMIN, which no list had named. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for deploying the applications (3-Methods-CRM-Google-Applications.md, version 0.5) with the step list's finishing tests. Numbered actions, a reason per step, and a check an app can run were added. |
