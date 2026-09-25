# Stage 11 — Deploy the chapter's applications

**Version:** 0.12  
**Last Updated:** 09-25-26 13:00  
**Generated from** `steps/stage-11.yaml` — do not edit this page; edit the YAML and re-render.

---

## Summary

In this stage we put the chapter's applications on its own hosting account and prove they work. We generate the deployment settings from the reviewed chapter information form, create the application's three parts and its database, set the update policy the chapter chose, give the application the chapter's own web address, and read its health page. Then we prove each Google connection in turn: incoming mail, outgoing mail, the calendar, the shared drive and a new mentor's mailbox. The applications are what the chapter's staff, mentors and the public actually use, and this stage is where they first run for this chapter. The Google checks come last, one at a time and in an order where each depends on the one before, because each fails in a way that names nothing useful.

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
- 11.8 Set the update policy the chapter chose
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

**Summary:** The settings generator in step 11.2 creates a session secret for this chapter: a random value that signs every sign-in the applications issue. We copy it into the vault so it can be restored if the deployment is ever rebuilt. Each chapter has its own, because a secret shared between chapters would let a sign-in from one chapter's applications be accepted by another's.

**Who:** The central support organization

**Finish first:**

- step 2.7 Set up the chapter's password vault

**Do this:**

1. Nothing to run by hand. The settings generator in step 11.2 creates the session secret the first time it runs, as a random value of 48 bytes, and appends it to the chapter's settings file (CHAPTER-ENV-FILE, which is ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env).
2. After step 11.2, open CHAPTER-ENV-FILE in a text editor, copy the value after SESSION_SECRET= into a new item in the chapter's Operations vault named Session secret, and save.
   *You should see:* The Session secret item in the Operations vault.

**Done when:** A new random session secret has been generated for this chapter alone and stored in the secrets store. It is never copied from another chapter.

**How to check:**

- Open CHAPTER-ENV-FILE (~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env) in a text editor. It holds one line beginning SESSION_SECRET= followed by a long run of letters, digits and symbols with no spaces. An empty value, or no such line, means step 11.2 has not run.
- In Proton Pass, open the chapter's Operations vault. The item named Session secret holds the same value, character for character: compare the first six and the last six characters against the file.
- Open another chapter's Session secret item beside it, Cleveland's or the trial chapter's. The two values differ. The same value in two vaults means one was copied, and both chapters must be given fresh ones.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Copying another chapter's.

---

## 11.2 Generate the deployment settings

**Summary:** We run the settings generator, which reads the filled-in chapter information form and the chapter's secrets file and writes the settings file the hosting platform builds the applications from. Every value comes from the reviewed form rather than from memory, so what the chapter approved in stage 8 is what gets deployed. On its first run the generator also creates the stored-data encryption key, which we copy into the vault at once, because it can never change afterwards without destroying the data it protects.

**Who:** The central support organization

**Finish first:**

- step 8.9 Review the completed form
- step 9.7 Apply the standard with one script

**Do this:**

1. Before running it, check CHAPTER-ENV-FILE already holds these three lines, written by the script in step 9.7:
   - ESPO_API_KEY=
   - ESPO_PROVISION_USERNAME=
   - ESPO_PROVISION_PASSWORD=
2. Download the Google machine account key from the chapter's Operations vault (step 10.2) and save it as ~/.config/cbm-SHORT-LABEL/google-key.json. Then add this line to the end of CHAPTER-ENV-FILE. The file is named rather than pasted because the key runs over several lines, which would break the build commands that read CHAPTER-ENV-FILE:
   - GOOGLE_SERVICE_ACCOUNT_KEY_FILE=~/.config/cbm-SHORT-LABEL/google-key.json
3. Check the form's flags section names every switch deliberately, as true or false. The Google switches (gmail_sync, gcal_events, gdrive_docs, google_directory_check, google_create_mailbox) go into the deployment from here, not from the settings page: the background worker decides at start-up whether to read the mailbox, and a switch set later at /setup never reaches it. Set gdrive_identity to service, and set deploy_on_push to true so the application follows the release branch from its first build.
4. In a terminal, in the folder ~/Dropbox/Projects/cbm-client-intake, type the line below and press Enter. CHAPTER-VALUES-FILE is the filled-in chapter information form saved as YAML (the trial chapter's is prds/chapter-network/rehearsal-2026-08-31/lakeside-values.yaml):
   - uv run python scripts/rehearsal/render_spec.py CHAPTER-VALUES-FILE ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env ~/.config/cbm-SHORT-LABEL/SHORT-LABEL-app.yaml

   *You should see:* A line reading: wrote ~/.config/cbm-SHORT-LABEL/SHORT-LABEL-app.yaml following branch release with N shared + N web-only env vars. If it reads secrets not yet minted, step 9.7 has not run. If it names GOOGLE_SERVICE_ACCOUNT_KEY_FILE or shared_drive_id, a Google switch is on before stage 10 has produced what it needs.
5. Open SHORT-LABEL-app.yaml and check three things. The generator sets them itself; this is a check, not an edit:
   - There is no ENV_LABEL line.
   - ALLOWED_ORIGINS is https://APP-ADDRESS, or absent if the application address is not known yet.
   - Every branch line reads branch: release (the web part, the worker and the migrate job).
   - No value names Cleveland or cbmentors.org. The chapter's own website, mentor email domain and mailbox addresses appear instead.
6. Open CHAPTER-ENV-FILE and copy the value after APP_ENCRYPTION_KEY= into a new item in the chapter's Operations vault named Stored-data encryption key. This value must never change.
   *You should see:* The Stored-data encryption key item in the Operations vault.
7. Never commit SHORT-LABEL-app.yaml anywhere. It holds secrets in plain text. It is deleted in step 11.3.

**Done when:** The settings are produced from the chapter information form and every value in them traces back to a line on that form.

**How to check:**

- The generator's last line reads wrote ~/.config/cbm-SHORT-LABEL/SHORT-LABEL-app.yaml, names the release branch, and gives a count of shared and web-only settings. Any other last line is a refusal, and it names what is missing.
- Open SHORT-LABEL-app.yaml in a text editor and search for Cleveland, then for cbmentors.org, then for Rehearsal. None is found. Each would be a value the generator took from the software's own defaults instead of from the form.
- Search the same file for branch:. Every match reads branch: release, and there are three of them: the web part, the worker and the migrate job.
- Pick three values from the form, for example the chapter name, the shared operations mailbox and the shared drive identifier, and find each one in the file. Each reads exactly as the form has it, character for character.
- In Proton Pass, the Operations vault holds an item named Stored-data encryption key, and its value matches the line beginning APP_ENCRYPTION_KEY= in CHAPTER-ENV-FILE.

**If it didn't work:** The generator refuses to run when the CRM key or the administrator credentials are missing. Fetch them from the vault and run it again.

**What usually goes wrong:** The stored-data encryption key. The generator creates it quietly on first run, and changing it later destroys the data it protects, so it is permanent from the moment it exists. Also, the trial script asks for a development database, which takes no backups (see step 11.4). A form field written as "none yet" is left out of the settings, so the software's own default applies until the field is filled in and the settings are generated again.

---

## 11.3 Load the secrets

**Summary:** The settings file from step 11.2 carries every secret into the deployment when the application is created in step 11.5, and the hosting platform keeps them scrambled so they cannot be read back. Our part is the other half: once the deployment holds them, check the vault holds every one, then delete the settings file, the Google key file and the secrets file from the computer. A secret readable in a file on a laptop is a secret leaked, and this is the weakest point in the stage.

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

**How to check:**

- At cloud.digitalocean.com, open Apps, then SHORT-LABEL-intake, then Settings, then the web component, then its environment variables. SESSION_SECRET, APP_ENCRYPTION_KEY, ESPO_API_KEY, ESPO_PROVISION_PASSWORD and GOOGLE_SERVICE_ACCOUNT_JSON are all listed, each shown masked or as an encrypted value beginning EV[, never as its plain value. A name missing was never loaded; a value readable in full was loaded without the encrypt option.
- Before deleting anything, go through CHAPTER-ENV-FILE line by line. For each secret in it (ESPO_API_KEY, ESPO_PROVISION_USERNAME, ESPO_PROVISION_PASSWORD, SESSION_SECRET and APP_ENCRYPTION_KEY) the Operations vault holds an item by name, and the Google machine account key item holds the key file. Check by name, one at a time.
- In a terminal, type ls ~/.config/cbm-SHORT-LABEL/ and press Enter. The listing shows no file ending -app.yaml, no google-key.json and no file ending .env. Anything still listed holds secrets in plain text.
- The application starts: the first deployment in step 11.6 reaches ACTIVE. A secret loaded under a wrong name shows up as a start-up failure in that deployment's log, not here.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The settings file with plain-text secrets left on a laptop or committed. Getting the settings back from the platform afterwards does not help: the platform hands the secrets back scrambled into an unreadable form.

---

## 11.4 Create the database

**Summary:** The application keeps its own database, and every submission is saved there before anything reaches the CRM; that is what stops a submission being lost when the CRM is down. Step 11.5 creates the database with the application, but the trial settings ask for a development database, which takes no backups. So straight afterwards we convert it to a managed database on the smallest plan. The platform redeploys the application by itself, and the connection details do not change.

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

**How to check:**

- At cloud.digitalocean.com, open Apps, then SHORT-LABEL-intake, then Settings. The components list shows SHORT-LABEL-db, and opening it shows a managed database with a plan name such as db-s-1vcpu-1gb, not a development database. A development database is the failure: convert it as the actions describe.
- In the same account, open Databases in the left-hand menu. The managed database is listed there in its own right, with a status of Online. A development database never appears in this list.
- Open https://APP-ADDRESS/healthz. The database field reads ok and durableStore reads true. This proves the application reached the database, whichever kind it is.
- Nobody holds the connection details: the settings file from step 11.2 has no line beginning DATABASE_URL, and the vault has no item for it. The platform supplies it to the application directly.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Leaving it as a development database. Nothing reports an error, and there are no backups. The trial chapter's database is in this state. Also, the hosting platform adds an instruction to the connection details that the application's database library rejects; the software strips it, so it only looks broken.

---

## 11.5 Create the application parts

**Summary:** We create the application in the chapter's hosting account from the settings file, using the command-line tool signed in to the chapter's account under its own named context. The application is three parts: the web part people use, the background worker that delivers submissions and sends mail and finishes unfinished work, and the setup job that prepares the database before each start. All three come from the one settings file, so creating the application creates them together. A web part on its own looks fine and quietly does nothing.

**Who:** The central support organization

**Finish first:**

- step 11.2 Generate the deployment settings
- step 11.3 Load the secrets
- step 5.9 Link the hosting account to the code repository

**Do this:**

1. If this computer has never been signed in to the chapter's hosting account, type the line below and press Enter, then paste the DigitalOcean token from the Operations vault when asked. It must be the token made under your own sign-in in step 5.8, not one made under the chapter's sign-in:
   - doctl auth init --context SHORT-LABEL

   *You should see:* A message that the token was validated.
2. Check whose token it is. Type the line below and press Enter:
   - doctl --context SHORT-LABEL account get --format Email

   *You should see:* Your own DigitalOcean sign-in address, the one that linked GitHub in step 5.9. The chapter's own address here means the create below fails: make a token under your own sign-in (step 5.8) and run doctl auth init again with a new context name.
3. Every doctl command in this stage names the chapter's context with --context SHORT-LABEL, and every script that calls doctl runs with DIGITALOCEAN_CONTEXT=SHORT-LABEL in front. Do not use doctl auth switch: it changes this computer's default for every later command, including Cleveland's.
4. Type the line below and press Enter:
   - doctl --context SHORT-LABEL apps create --spec ~/.config/cbm-SHORT-LABEL/SHORT-LABEL-app.yaml

   *You should see:* A table with the new application's ID and the name SHORT-LABEL-intake. Copy the ID into the Operations vault as a note named Application ID; later steps call it APP-ID.
5. Type the line below and press Enter:
   - doctl --context SHORT-LABEL apps get APP-ID

   *You should see:* The application listed. In the hosting account's web page, its Components show web, delivery-worker and migrate.

**Done when:** The web part, the background worker part and the setup job all exist.

**How to check:**

- In a terminal, type doctl --context SHORT-LABEL apps get APP-ID and press Enter. One line names SHORT-LABEL-intake, and its ID matches the note named Application ID in the Operations vault.
- At cloud.digitalocean.com, open Apps, then SHORT-LABEL-intake. Under Components three are listed: web, delivery-worker and migrate. Two means the settings file was cut down; three is the only right answer.
- Type doctl --context SHORT-LABEL account get --format Email and press Enter once more. The address is still your own sign-in, so every later command in this stage acts on the chapter's account under the right token.
- Type doctl apps list, with no context, and press Enter. It still lists Cleveland's three applications. This shows this computer's default context was not changed, which is what doctl auth switch would have done.

**If it didn't work:**

- GitHub user not authenticated: the token belongs to a different sign-in from the one that linked GitHub in step 5.9. DigitalOcean ties the GitHub link to a sign-in, not to the team. Make a token under that sign-in (step 5.8), run doctl auth init with a new context name, and create again (Boston, 09-24-26).

**What usually goes wrong:** Creating only the web part. Without the background worker the system looks fine and quietly does nothing.

---

## 11.6 Run the database setup

**Summary:** The migrate job runs before the application starts and creates or updates the tables in the application's database. Nothing is run by hand: we read the first deployment's result to confirm the job ran and the application came up. A deployment that ends in ERROR is nearly always this job or the build, and its log says which.

**Who:** The central support organization

**Finish first:**

- step 11.5 Create the application parts

**Do this:**

1. Nothing to run. The migrate job runs by itself before the application starts.
2. Type the line below and press Enter:
   - doctl --context SHORT-LABEL apps list-deployments APP-ID

   *You should see:* The first deployment in the list with its phase ACTIVE. A phase of ERROR means the migrate job or the build failed; open the deployment in the hosting account's web page and read its log.

**Done when:** The setup job has completed and the database holds the expected tables.

**How to check:**

- Type doctl --context SHORT-LABEL apps list-deployments APP-ID and press Enter. The top row's Phase reads ACTIVE. PENDING or BUILDING means wait a few minutes and look again; ERROR means read the log.
- At cloud.digitalocean.com, open Apps, then SHORT-LABEL-intake, then the deployments list, and open the top deployment. Its steps show the migrate job completed before the web and delivery-worker parts started, and the job's log ends without an error.
- Open the health page at the platform's address (https://APP-ADDRESS/healthz only after step 11.10). database reads ok. An application that came up against a database with missing tables fails here, not at deployment.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 11.7 Deploy the released version

**Summary:** The application takes its software from the release branch, which holds only cut releases, so the first build already runs the current release. We read the health page to confirm the version it reports is that release and that it carries the release tag. Every chapter runs the same named release, so a support question never has to begin by asking which version a chapter is on.

**Who:** The central support organization

**Finish first:**

- step 11.6 Run the database setup

**Do this:**

1. Open https://APP-ADDRESS/healthz in a browser. Until step 11.10, use the address DigitalOcean gave the application, shown by doctl --context SHORT-LABEL apps get APP-ID under Default Ingress.
   *You should see:*

   - status: ok
   - version: the current release's number, the one the release branch holds today
   - releaseTag: the same release with a v in front. The application follows the release branch from its first build, so it reads the tag straight away. A null here means the release branch's latest commit is not a cut release.

**Done when:** The application is running the version the release schedule names, and it reports that version when asked.

**How to check:**

- Open https://APP-ADDRESS/healthz. releaseTag reads the current release with a v in front, for example v0.232.0, and version reads the same number without the v. The two must agree: the tag is honoured only when it matches the build.
- Find the current release to compare against. In a terminal, in the folder ~/Dropbox/Projects/cbm-client-intake, type git tag --sort=-v:refname and press Enter. The first line is the newest release, and it matches the health page's releaseTag.
- A releaseTag of null is the honest answer that the application is not on a cut release: either it follows the development branch, which step 11.9 catches, or the release branch has moved past the last cut. Neither is fixed here; report it.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** releaseTag reads null. That means the application follows the development branch rather than the release branch. It is the honest answer, not a fault.

---

## 11.8 Set the update policy the chapter chose

**Summary:** The chapter chose in step 8.6 whether its applications take each release automatically or only when it asks. We apply that choice with one script that sets all three parts of the application at once, then read it back. Each part carries its own setting, and the platform gives no warning when one is set and the others are not, which is why one script does all three and the status option is the check.

**Who:** The central support organization

**Finish first:**

- step 11.7 Deploy the released version

**Do this:**

1. POLICY is the chapter's answer to Take each release automatically? in step 8.6: latest-stable for yes, on-demand for no. In the folder ~/Dropbox/Projects/cbm-client-intake, type the line below and press Enter. The first word points the script at the chapter's account. It changes nothing:
   - DIGITALOCEAN_CONTEXT=SHORT-LABEL uv run python scripts/set_updates_policy.py APP-ID POLICY

   *You should see:* The change it would make to each of the three parts.
2. Type the line below and press Enter. The deploy option starts a fresh deployment; without it the application rebuilds the same commit it already runs:
   - DIGITALOCEAN_CONTEXT=SHORT-LABEL uv run python scripts/set_updates_policy.py APP-ID POLICY --apply --deploy

   *You should see:* The spec updated and a new deployment started.
3. Type the line below and press Enter:
   - DIGITALOCEAN_CONTEXT=SHORT-LABEL uv run python scripts/set_updates_policy.py APP-ID POLICY --status

   *You should see:* One line per part, each showing branch=release, with deploy_on_push=True for latest-stable or deploy_on_push=False for on-demand, and a final line reading conformant with the policy named.

**Done when:** All three parts of the application follow the release branch and the policy script reads all three back in agreement with the policy the chapter chose. An application has three parts, each with its own setting, and setting one without the others half-updates it with no warning from the platform.

**How to check:**

- Type DIGITALOCEAN_CONTEXT=SHORT-LABEL uv run python scripts/set_updates_policy.py APP-ID POLICY --status and press Enter. There are exactly three part lines: web, delivery-worker and migrate. Each reads branch=release. Each reads deploy_on_push=True when POLICY is latest-stable, or deploy_on_push=False when it is on-demand. The final line reads conformant and names the policy.
- Type doctl --context SHORT-LABEL apps list-deployments APP-ID and press Enter. The top row is a new deployment, later than the one from step 11.6, started by the --deploy option, and its Phase reaches ACTIVE. Without that option the application keeps running the commit it already had.
- At cloud.digitalocean.com, open Apps, then SHORT-LABEL-intake, then Settings, then each of the three components in turn. Under Source, each names the release branch and shows automatic deployment on or off in line with the policy. Three components checked, not one.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Setting one part and not the others. Nothing on the platform tells you that you have half-updated it.

---

## 11.9 Confirm the application does not follow the development branch

**Summary:** We read the update policy back once more, looking only at the branch. The development branch delivers untested software, and an application following it with automatic deployment on would take every change the moment it is pushed. The release branch with automatic deployment on is safe, because the release stamp travels inside the software. The danger was never automatic deployment; it is automatic deployment from the development branch.

**Who:** The central support organization

**Finish first:**

- step 11.8 Set the update policy the chapter chose

**Do this:**

1. Type the line below and press Enter:
   - DIGITALOCEAN_CONTEXT=SHORT-LABEL uv run python scripts/set_updates_policy.py APP-ID POLICY --status

   *You should see:* Every part showing branch=release, none showing branch=main, and the line conformant with the policy named.

**Done when all of these are true:**

- No part of the deployment follows the main development branch.

**Note:** This replaces what the earlier planning documents said. Those documents require automatic deployment to be switched off on a chapter's application, which was right when the release version travelled inside each deployment's settings. The version is now stamped into the software itself when a release is cut, so an application following the release branch with automatic deployment on updates itself correctly. The danger was never automatic deployment — it is automatic deployment from the development branch, which delivers untested software straight to a chapter's live system.

**How to check:**

- In the status output from the action, every part line reads branch=release. Search the output for branch=main: nothing is found. One part on main is enough to fail this check, even with the other two right.
- At cloud.digitalocean.com, open Apps, then SHORT-LABEL-intake, then Settings, and open each of the three components. Under Source, the branch reads release on each. This is the platform's own view, and it must agree with the script's.
- Open https://APP-ADDRESS/healthz. releaseTag is not null. An application on the development branch reports null there, so a value is a third, independent confirmation.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 11.10 Point the application's web address at the application

**Summary:** We give the application the chapter's own address, for example apps.CHAPTER-DOMAIN, by adding one CNAME record at the chapter's DNS provider that points the name at the platform's address, and by telling the hosting platform that name is its primary domain. The platform then issues the certificate for it. The record has to be DNS only: a proxy in front of it stops the platform issuing or renewing the certificate.

**Who:** The central support organization

**Finish first:**

- step 3.7 Move the domain names' DNS to the chapter's Cloudflare account
- step 11.5 Create the application parts

**Do this:**

1. Type the line below and press Enter, and copy the address shown under Default Ingress (it ends .ondigitalocean.app):
   - doctl --context SHORT-LABEL apps get APP-ID
2. In the chapter's Cloudflare account, open the domain, then DNS, then Records, and choose Add record. Enter exactly:
   - Type: CNAME
   - Name: the first part of the application's address, for example apps
   - Target: the Default Ingress address, without https://
   - Proxy status: DNS only (grey cloud)
   - TTL: Auto

   *You should see:* The record listed with a grey cloud.
3. With manual DNS (step 3.7), add the same CNAME record in the chapter's DNS provider account instead, with any proxy or forwarding off. Its screens differ by provider and are not given here; the Name and Target are the same. As in step 9.3, type only the first part of the address as the record's host, for apps.bbmentors.org just apps: Squarespace and most providers add the domain themselves.
4. In the hosting account, open Apps, then SHORT-LABEL-intake, then Settings, then Domains, and add APP-ADDRESS. Choose to manage DNS yourself and make it the primary domain. Labels are not checked on screen for this guide.
   *You should see:* The domain listed, moving to Active once the certificate is issued. On Boston (09-24-26) the certificate was issued within the hour of the record appearing; the line doctl --context SHORT-LABEL apps get APP-ID -o json shows the domain's phase PENDING until then, and ACTIVE after.

**Done when:** The domain name record for the application address resolves to it.

**How to check:**

- In a terminal, type dig +short APP-ADDRESS and press Enter (or nslookup APP-ADDRESS on a computer without dig). The first line is the application's platform address, ending .ondigitalocean.app. No answer at all, straight after creating the record, is usually a resolver keeping its earlier "no such name" answer: wait ten minutes and look again before changing anything.
- In Cloudflare, open the domain, then DNS, then Records. The CNAME row for the application's name shows a grey cloud under Proxy status. An orange cloud is the known failure: click it to turn the proxy off. With manual DNS, the provider's record shows the same name and target, with no forwarding.
- Type doctl --context SHORT-LABEL apps get APP-ID -o json and press Enter, and find the domains section. APP-ADDRESS is listed with phase ACTIVE. PENDING within the first hour is normal (Boston took under an hour); PENDING for longer means the record is wrong or proxied.
- At cloud.digitalocean.com, open Apps, then SHORT-LABEL-intake, then Settings, then Domains. APP-ADDRESS is listed as the primary domain with a status of Active.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The proxy switched on, an orange cloud. The hosting platform then cannot issue or renew the certificate. Also, straight after the record is created, some resolvers keep an earlier "no such address" answer for a while; wait rather than changing the record.

---

## 11.11 Publish the application at its own web address

**Summary:** Nothing to build here: once the domain is active, the hosting platform issues the security certificate and renews it by itself. We confirm the applications answer at the chapter's own address over a secure connection with no warning, because every sign-in and every form submission travels over that connection.

**Who:** The central support organization

**Finish first:**

- step 11.10 Point the application's web address at the application

**Do this:**

1. Nothing to do. The hosting platform issues the certificate and renews it by itself.
2. Open https://APP-ADDRESS in a private browser window.
   *You should see:* The applications' sign-in page, with no certificate warning.

**Done when:** The application loads at its address over a secure connection, and the security certificate is set to renew by itself.

**How to check:**

- In a private browser window, open https://APP-ADDRESS. The sign-in page loads with the padlock in the address bar and no warning page in front of it. A warning that the connection is not private means the certificate is missing or was issued for another name.
- Click the padlock and view the certificate. It is issued to APP-ADDRESS by Let's Encrypt (the certificate service the platform uses), and its expiry date is within the next ninety days. The platform renews it before then; nobody has to.
- Open https://APP-ADDRESS/healthz, at the chapter's address rather than the platform's. It answers status: ok. This shows the name reaches the same application, not merely that a certificate exists.
- Open http://APP-ADDRESS, without the s. The browser is sent on to the https address. A page that stays on http is a domain the platform has not taken over.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 11.12 Confirm the application is healthy

**Summary:** The health page is the one place that shows, at a glance, that the application runs, knows which chapter it belongs to, reaches its database and has a live background worker. We read it once, field by field, before any check that depends on those things. A page read too soon after a deployment shows a failure that is not real, so wait a minute and read it again before reporting one.

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

**How to check:**

- Open https://APP-ADDRESS/healthz. status reads ok, and version and releaseTag agree with what step 11.7 found.
- organization reads the chapter's own name, exactly as the form gives it. Cleveland's name there means the chapter name setting did not reach the deployment: correct the form and run step 11.2 again.
- database reads ok, and inside worker, lastHeartbeatAgeSeconds is under 180. A number that grows on each reload means the delivery-worker part is not running: read its runtime log in the hosting account.
- Inside crmConfig, state reads stamped or unstamped. absent means the CRM does not hold the configuration-version record the standard defines (stage 9 is incomplete); forbidden means the application's CRM key cannot read it (step 9.7); unreachable means the CRM address is wrong or the CRM is down. Each names a different place to look.
- Reload the page after one minute. The values are the same, and the heartbeat age has reset rather than grown.

**If it didn't work:** Wait a minute and read it again before calling it a failure.

**What usually goes wrong:** Reading it before the new software has finished starting, which shows a failure that is not real. And Cleveland's name where the chapter's should be, which means the chapter name setting was not applied.

---

## 11.13 Confirm the application can read the CRM

**Summary:** We sign in to the applications with the CRM administrator account and open one screen that lists CRM records. A permission missed in stage 9 does not show as an error inside the applications; it shows as an empty screen, or as a refusal naming the entity. So this is the one check that reads the CRM through the application itself rather than through the health page.

**Who:** The central support organization

**Finish first:**

- step 9.7 Apply the standard with one script
- step 11.12 Confirm the application is healthy

**Do this:**

1. Open https://APP-ADDRESS and sign in with the CRM administrator account the deployment wizard created in step 9.3. Its name and password are in the Operations vault.
2. Open Client Administration.
   *You should see:* Records, or an empty list. Both are fine. A message that access was refused means a permission was missed in stage 9.

**Done when:** A request through the application returns CRM data.

**How to check:**

- At https://APP-ADDRESS, sign in with the CRM administrator account from step 9.3. The portal opens with tiles for the staff tools. A sign-in refused means the CRM address or the account is wrong, not a permission.
- Open Client Administration. The grid shows records, or the words for an empty list. Either is a pass. A message naming an entity and an operation, for example CEngagement read, is a permission missed in stage 9: go back to step 9.7.
- Open Mentor Administration and see the same: a list or an empty list, never a refusal. A second screen reading a second entity is a fairer sample than one.
- Note what this pass proves. An administrator passes every permission check whatever the roles say, so this proves the connection and the key, not the roles. Stage 14 proves the roles, with a real non-administrator account.

**If it didn't work:** A refusal means a permission was missed in stage 9. Go back to step 9.7.

**What usually goes wrong:** A page that asks for more than two hundred records at once is refused rather than trimmed, and inside the software that refusal reads as "there are no records". This once emptied every selection list on Cleveland's live system.

---

## 11.14 Confirm incoming mail

**Summary:** This is the first Google connection, and everything after it depends on it. The background worker signs in to Google as the machine account, acts as the shared operations mailbox, and captures each new message into Submission Admin. We confirm the settings reached the deployment, that the worker names the right mailbox in its log, and that a real message arrives. Only one deployment may read a given mailbox: two would each take roughly half the messages, and neither would look broken.

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

**How to check:**

- At https://APP-ADDRESS/setup, the four settings named in the actions show the chapter's values, with GOOGLE_SERVICE_ACCOUNT_JSON marked as set. Where the page shows a value in force beside the stored one, the two agree.
- At cloud.digitalocean.com, open Apps, then SHORT-LABEL-intake, then Runtime Logs, and choose delivery-worker. In the first minutes after start-up there is a line naming the mailbox the worker reads, and it is the shared operations mailbox. Then search the log for unauthorized_client: it does not appear. If it does, the grant in step 10.3 is missing a mail permission or has not taken effect yet.
- From an outside address (a personal mailbox, not one on the chapter's domain), send a message to the shared operations mailbox with a subject you will recognise. Within about five minutes, open Submission Admin at https://APP-ADDRESS/ops: the message is listed as a new email submission with that subject.
- Open the submission. Its sender is the outside address and its body is the message you sent. Then close it with a reason, so the test does not sit in the queue.

**If it didn't work:** If the log line is missing or names the wrong address, stop. The cause is in stage 10, not here.

**What usually goes wrong:** Two deployments reading the same mailbox. Each takes roughly half the messages, and neither is obviously broken.

---

## 11.15 Confirm outgoing mail

**Summary:** Staff and mentors send email from records, and the worker sends alerts, both through Google as the machine account acting as a chapter mailbox. We confirm the alert addresses reached the deployment, then send one message from a record to an outside address we can read. The alert sending address must be a real licensed mailbox, for the same reason as in step 10.4: a group or an alias is refused, and the refusal reads as though the machine account is not allowed at all.

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

**How to check:**

- At https://APP-ADDRESS/setup, ALERT_EMAIL_FROM and ALERT_EMAIL_TO show the addresses from steps 4.8 and 4.9. At admin.google.com, under Directory then Users, the ALERT_EMAIL_FROM address is listed as a licensed user, the same test step 10.4 made for the operations mailbox.
- Open a record in the application, choose to send an email from it, and send a short message to an outside address you can read. The compose screen closes with no error message.
- In the outside mailbox, the message arrives within a few minutes. The From line shows the chapter's own name, and the address is one of the chapter's mailboxes, never Cleveland's. A message that never arrives, with no error in the application, is a send Google refused: search the delivery-worker runtime log for unauthorized_client.
- Back in the application, the record's Communications tab lists the message you sent, with the time it went. That is the application's own record of the send, written after Google accepted it.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The address the software sends warnings from must also be a real licensed mailbox. A group or alias is refused, and the refusal reads as though the machine account is not allowed at all.

---

## 11.16 Confirm the calendar

**Summary:** Sessions a mentor schedules in the applications are put on that mentor's Google calendar, with the client's contacts invited and a Meet link attached, by the machine account acting as the mentor. This needs a mentor with a login and an assigned client, and neither exists until stage 15, so the check creates the test mentor and client from stage 17 and removes them afterwards. The calendar permission is the one most often missed in the grant, because working mail makes everything look fine.

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

**How to check:**

- At https://APP-ADDRESS/setup, GCAL_EVENTS shows true.
- Signed in as the test mentor, open the test client in Client Management and save a session with Status Scheduled and a start time tomorrow. The save succeeds, and the session appears on the record's Sessions tab.
- Sign in at calendar.google.com as the test mentor's chapter mailbox. The session is on tomorrow at the time entered, with the client's contact listed as a guest and a Google Meet link in the event.
- Use an address you own for the test client's contact, and open that inbox. The invitation arrived, from the mentor's chapter address.
- If nothing appears on the calendar and the session saved without complaint, read the web component's runtime log in the hosting account (the calendar runs in the web part, not the worker) and search for calendar. A line reading unauthorized_client is the calendar permission missing from step 10.3.
- Change the session's start time in the application and save again. The calendar event moves to the new time; a second event appearing is a fault to report. Then set the session to Cancelled: the event is cancelled on the calendar.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The calendar permission is a separate entry in the grant from step 10.3, and the one most often missed, because working mail makes everything look fine.

---

## 11.17 Confirm the shared drive

**Summary:** Record documents are filed on the chapter's shared drive, in a folder per record, by the machine account as a member of the drive. We confirm the drive identifier and the two Drive settings reached the deployment, then upload one small file to a client's Documents tab and look for it on the drive. Both known failures, the machine account not being a member and a wrong identifier, give silence rather than an error, so the file on the drive is the only proof.

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

**How to check:**

- At https://APP-ADDRESS/setup, GDRIVE_SHARED_DRIVE_ID shows the identifier from step 10.5 (about nineteen characters, usually beginning 0A), GDRIVE_IDENTITY shows service and GDRIVE_DOCS shows true.
- Open the test client in Client Management, open its Documents tab, and upload a small file such as a one-line text file. The file appears in the Documents list with its name, and opening it from the list shows its content.
- At drive.google.com, signed in as the chapter's Google administrator, open Shared drives, then CHAPTER-NAME Documents. There is a top-level folder for clients, inside it a folder named for the client with its record identifier in brackets, and inside that (or inside a folder for the engagement) the file you uploaded.
- If the file is on the Documents tab but not on the drive, or the upload fails with no message, read the web component's runtime log and search for drive. A message that the drive was not found is a wrong identifier; one that access was refused is a machine account that is not a member of the drive.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The service account is not a member of the shared drive, or the drive's identifier on the form is wrong. Both give silence, not an error.

---

## 11.18 Confirm a new mentor gets a mailbox

**Summary:** This last check exercises the most. When a mentor is set to Accepted-Provisional in Mentor Administration, the application creates a Google Workspace mailbox for them on the mentor email domain, adds it to the members group, and advances the record to Provisional. It does this as the machine account acting as the chapter's Google administrator, so it needs both directory permissions, reading and changing; a grant with only the reading one gets all the way here before failing. It is what every new mentor will depend on. The step ends by pointing the command-line tool back at the account used for Cleveland.

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

**How to check:**

- At https://APP-ADDRESS/setup, the six settings named in the actions show the chapter's values. GOOGLE_DELEGATED_ADMIN is the chapter's Google administrator address, a real person's account and not a group; GOOGLE_MEMBERS_GROUP is the members group address, or empty.
- In Mentor Administration, after the test mentor is set to Accepted-Provisional, the status window reports the mailbox created and shows a temporary password once. Reload the mentor: Mentor Status now reads Provisional, which the application sets only once the account is confirmed, and the mentor's chapter email address reads firstname.lastname@ the mentor email domain.
- At admin.google.com, open Directory, then Users, and search for that address. It is listed as a user with a licence, created today. Open it: under Groups, the members group is listed when GOOGLE_MEMBERS_GROUP was set. A user with no group is the group step failing, which the status window reports and which does not stop the mailbox.
- In a private browser window, sign in at mail.google.com as the new address with the temporary password. Google asks for a new password, then opens an empty inbox.
- In Mentor Administration, choose Update Mentor Status. The sweep reports the test mentor's mailbox found, and nobody stranded at Accepted-Provisional.
- After the clean-up, the test user is gone from Directory then Users at admin.google.com, and the test mentor and its contact are gone from the CRM. Then type doctl auth list and press Enter: the context marked current is the one used for Cleveland, not SHORT-LABEL.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Two directory permissions are needed, reading and changing. A grant with only the reading one gets all the way to this step before failing. And the mentor email domain is a setting somebody has to fill in; a chapter whose mentor addresses are on a different domain from its staff addresses has to say so.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.12 | 09-25-26 13:00 | Rewritten for the reader, as stage 10 was (Doug, 09-25-26): the stage and every step open with a Summary, what is done and why in a few plain sentences, in place of the one-line Why. Every How to check is now a list of concrete checks naming where to look and what must be seen, one per line: the secret compared against the vault and against another chapter's, the settings file searched for Cleveland's values and for the branch lines, the hosting account's own view of the three parts and their branches beside the script's, the certificate's issuer and expiry, each health-page field and what each crmConfig state points at, the worker log searched for unauthorized_client, and for each Google check the place on Google's side where the result must appear. Actions are unchanged. |
| 0.11 | 09-24-26 23:08 | Corrections from Boston's build on 09-24-26. Step 11.5 checks whose token the context holds before creating, because DigitalOcean ties its GitHub link to a sign-in and a token made under the chapter's own sign-in fails with GitHub user not authenticated. Every doctl command names the chapter's context and every script runs with DIGITALOCEAN_CONTEXT, in place of doctl auth switch, which changed this computer's default for Cleveland's commands too. Step 11.10 repeats the host-name trap for manual DNS and records the timing. Statuses updated: 11.4 managed, 11.10 and 11.11 done for real. |
| 0.10 | 09-24-26 00:39 | The chapter decides when its applications take a release (Doug, 09-24-26, CRMBuilder decision DEC-1156): a chapter may decline a release or schedule the upgrade for a time of its own. Step 11.8 sets the policy the chapter chose in step 8.6, latest-stable or on-demand, in place of Latest Stable for every chapter; step 11.9 reads the policy back by name. The stage no longer says every chapter takes each weekly release by itself. |
| 0.9 | 09-23-26 20:40 | References to stage 9 follow its renumbering from twenty steps to nine (stage 9 version 0.11). |
| 0.8 | 09-23-26 14:27 | The placeholder CHAPTER-SLUG is now SHORT-LABEL, the form's own name for it (Doug, 09-23-26: slug is a terrible name for a user). The guide's index lists every shared placeholder. |
| 0.7 | 09-23-26 13:54 | Manual DNS added (Doug, 09-23-26): step 11.10 adds the application's CNAME record at the chapter's own DNS provider when the chapter kept it. |
| 0.6 | 09-23-26 12:25 | Step 11.5 now waits for step 5.9, the hosting account's link to the code repository on GitHub, without which creating the application fails. |
| 0.5 | 09-23-26 00:55 | From the review before the first real chapter. Every Google, mail, Drive, website and Zoom setting now goes into the deployment in step 11.2, from the form, and steps 11.14 to 11.18 confirm them at /setup instead of setting them there: the background worker decides at start-up from its own settings whether to read the mailbox, so a switch set at /setup never reached it. The Google key is named by file (GOOGLE_SERVICE_ACCOUNT_KEY_FILE), and step 11.3 deletes the file. The stored-data encryption key the generator creates is now one the software accepts; before, /setup refused to store any secret. Step 11.7 no longer names a release that does not exist, and step 11.16 creates the test mentor and client it needs. Step 11.18 switches doctl back. |
| 0.4 | 09-19-26 14:45 | Step 11.4's finishing test now matches step 11.3: the hosting platform supplies the database connection to the application, and no person holds it (Doug, 09-19-26). |
| 0.3 | 09-19-26 00:50 | The settings generator no longer writes the trial chapter's footer label, a localhost origin or the development branch, so the step that corrected them by hand is now a check. It refuses the development branch unless the form allows it. |
| 0.2 | 09-19-26 00:07 | Every action made exact (Doug, 09-19-26: sweep every step): the settings generator's command line and the three values in its output that are wrong for a real chapter (the Rehearsal label, the localhost origin, and the main branch); doctl commands against the chapter's own account; the managed database conversion path; the release policy commands; the Cloudflare record; the health page's exact fields; and the settings each Google check switches on at /setup, including GOOGLE_DELEGATED_ADMIN, which no list had named. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for deploying the applications (3-Methods-CRM-Google-Applications.md, version 0.5) with the step list's finishing tests. Numbered actions, a reason per step, and a check an app can run were added. |
