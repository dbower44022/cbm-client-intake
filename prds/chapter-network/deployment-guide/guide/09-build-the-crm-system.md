# Stage 9 — Build the CRM system

**Version:** 0.12  
**Last Updated:** 09-23-26 22:55  
**Generated from** `steps/stage-09.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The CRM is the chapter's system of record. Every client, mentor, partner, funder and meeting lives in it, and every application reads and writes it. This stage builds the chapter's own CRM on the chapter's own server, and makes it identical to every other chapter's CRM, so that one release of the software works for all of them.

**Who:** The central support organization, working inside the chapter's accounts.  
**Time:** About half a day when nothing goes wrong.  
**When this stage is done:** The Google permissions (stage 10) and the applications (stage 11) can start. The applications need the CRM key that step 9.7 creates.

**Before you start:**

- The chapter information form, complete and reviewed, saved as the chapter's values file (step 8.10)
- The chapter's hosting account, with the central support organization's access (steps 5.1 and 5.4)
- The chapter's domain names in its Cloudflare account, or at its own DNS provider with manual DNS (step 3.7)
- The chapter's own DigitalOcean token, and its Cloudflare token unless it uses manual DNS, entered in CRMBuilder (step 5.8)
- The chapter's vault in Proton Pass, for every secret this stage creates (step 2.7)

**Not possible yet:** the build goes ahead without these.

- Duplicate checking, saved views and automated rules. The standard does not yet say what these are, because nobody has examined them on Cleveland's systems (work list item 3). A chapter's CRM is built without them for now.
- Five event email templates. They exist on no system yet (work list item 18), so the checking tool in step 9.9 reports them missing. That result is expected.
- The server size. Step 9.3 uses 2 processors and 4 GB of memory. That is a recommendation, not yet ruled.

**Steps in this stage:**

- 9.1 Write down the versions to build with
- 9.2 Prepare the build computer
- 9.3 Run CRMBuilder's deploy wizard
- 9.4 Confirm the server works
- 9.5 Install the two paid add-on products
- 9.6 Copy the standard configuration onto the server
- 9.7 Apply the standard with one script
- 9.8 Stamp the configuration version
- 9.9 Run the checking tool

---

## 9.1 Write down the versions to build with

**Why:** Two paid add-on products and one release of the standard configuration go onto the CRM, and later steps check against their version numbers.

**Who:** The central support organization

**Finish first:** nothing.

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the chapter's Operations vault in Proton Pass, create a note named CRM build versions. Everything this step writes down goes in it.
2. Write down the two add-on products and the versions Cleveland's production CRM runs. To read them, sign in to Cleveland's production CRM as an administrator and open Administration, then Extensions. On 31 August 2026 they were:
   - Advanced Pack 3.12.1
   - Google Integration 1.8.4

   *You should see:* The two product names and version numbers in the note.
3. On each product maker's website, check that the version supports CRM version 10.
   *You should see:* Both versions marked as supporting version 10.
4. Write down the release of the standard configuration. There is no published version number yet (work list item 15). Until there is, write: Cleveland's test system on today's date, with roles and teams as captured on 31 August 2026.
5. Do not write down a CRM version. CRMBuilder always installs the current release, and step 9.4 records the exact number once the server exists.

**Done when all of these are true:**

- The CRM build versions note names both add-on products and their versions.
- Both versions support CRM version 10.
- The note names the release of the standard configuration.

**How to check:** Open the CRM build versions note in the vault.

**If it didn't work:** If either add-on version does not support CRM version 10, do not start the build. Ask the maker which version does, and write that one down instead.

**What usually goes wrong:** Writing down 9.3.4 as the CRM version, the version Cleveland's test system runs. A new chapter never runs it: CRMBuilder installs the current release, and Cleveland moves up later.

---

## 9.2 Prepare the build computer

**Why:** The deploy wizard in step 9.3 needs a sign-in key and an administrator password that already exist, and the scripts in later steps need a settings file.

**Who:** The central support organization

**Finish first:**

- step 2.7 Set up the chapter's password vault
- step 8.10 Store the form where the central support organization can reach it

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Work at the build computer. The build computer is the central support organization's own computer, the one with CRMBuilder installed. Every command in this stage is typed in a terminal window on the build computer. Two folders on it are used:
   - CRMBuilder's folder: ~/Dropbox/Projects/crmbuilder
   - The client intake software's folder: ~/Dropbox/Projects/cbm-client-intake
2. Create the server sign-in key. This is an SSH key: a pair of files that lets a person open a command line on the server. Type the line below and press Enter. Then press Enter twice more, to leave the key without a passphrase:
   - ssh-keygen -t ed25519 -f ~/.ssh/crm-SHORT-LABEL -C crm-SHORT-LABEL

   *You should see:* Two new files: ~/.ssh/crm-SHORT-LABEL, the private half, which later steps call KEY-FILE; and ~/.ssh/crm-SHORT-LABEL.pub, the public half.
3. Show the public half, so it can be copied. Type the line below and press Enter:
   - cat ~/.ssh/crm-SHORT-LABEL.pub

   *You should see:* One line beginning ssh-ed25519 and ending crm-SHORT-LABEL. Copy the whole line.
4. Add the public half to the chapter's DigitalOcean account. Sign in to the chapter's DigitalOcean account, open Settings, then Security, then add an SSH key. Paste the line, and name the key crm-SHORT-LABEL. The exact wording on DigitalOcean's screen has not been checked for this guide.
   *You should see:* The key crm-SHORT-LABEL in the account's list of SSH keys.
5. Create the CRM administrator password. In the chapter's Operations vault in Proton Pass, create a login item named CRM administrator. Set the user name to admin. Generate a password of 24 characters with symbols switched off, so it holds letters and numbers only.
   *You should see:* A password of letters and numbers only.
6. Create the folder for the chapter's settings file. Type the line below and press Enter:
   - mkdir -p ~/.config/cbm-SHORT-LABEL
7. Create the chapter's settings file. In a text editor, make a new file with the three lines below, with the password pasted from the CRM administrator item. Save it as ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env. Later steps call this file CHAPTER-ENV-FILE.
   - ESPO_ADMIN_BASE=https://CRM-ADDRESS
   - ESPO_ADMIN_USER=admin
   - ESPO_ADMIN_PASS=the password

   *You should see:* The file holds exactly three lines, with no spaces around the equals signs.

**Done when all of these are true:**

- The server sign-in key exists on the build computer, and its public half is in the chapter's DigitalOcean account.
- The CRM administrator password is in the vault, and holds letters and numbers only.
- The chapter's settings file holds the CRM's address and the administrator's name and password.

**How to check:** The key crm-SHORT-LABEL is listed in DigitalOcean, and the settings file opens with its three lines.

**If it didn't work:** If ssh-keygen says the file already exists, a key for this chapter was made before. Use that key, and skip to adding it to DigitalOcean.

**What usually goes wrong:** Using CRMBuilder's Generate button for the password. It can add a hyphen or an underscore, and the settings file is read by several programs that must all read the password the same way. Letters and numbers only are safe everywhere.

---

## 9.3 Run CRMBuilder's deploy wizard

**Why:** The wizard creates the server in the chapter's hosting account, installs the CRM on it, and gives the CRM its web address.

**Who:** The central support organization inside the chapter's hosting account

**Finish first:**

- step 5.4 Grant the central support organization access to the hosting account
- step 5.8 Create the two tokens CRMBuilder builds with
- step 3.7 Move the domain names' DNS to the chapter's Cloudflare account
- step 9.2 Prepare the build computer

**Do this:**

1. Start CRMBuilder. Type each line below and press Enter:
   - cd ~/Dropbox/Projects/crmbuilder
   - ./start-v2.sh

   *You should see:* CRMBuilder's main window. If a window titled Cloud backend not configured appears instead, the build computer is not connected to CRMBuilder's online service. Connect it before going on.
2. Choose the chapter. Click the strip across the top of the window, which names the current engagement, and choose the chapter's engagement.
   *You should see:* The chapter's engagement named in the strip. If it is not in the list, step 5.8 is not finished.
3. Open the deploy wizard. Click the tab 11 · CRM Deployment, then Instances in the side bar, then Deploy new… on the toolbar. Do not use New Instance: it only records a CRM that already exists.
   *You should see:* A window titled Deploy a new CRM instance, at Step 1 of 5 — Providers.
4. Screen 1, Providers. In the DNS list, choose the entry that matches the DNS provider item in the chapter's Operations vault:
   - Cloudflare — the run creates the record. Choose this when the chapter's DNS is at Cloudflare.
   - Manual DNS — I add the record at the domain's own DNS provider. Choose this when the chapter kept its own DNS provider.

   *You should see:* The entry that matches the vault.
5. Screen 1, Providers. Check the token lines, then click Next:
   - DigitalOcean must read: ✓ Configured — crmbuilder-SHORT-LABEL
   - Cloudflare must read: ✓ Configured — crmbuilder-SHORT-LABEL. With manual DNS it may read Not set.

   *You should see:* The labels exactly as above. Any other label means the server would be built in someone else's account: click Set credentials… and do step 5.8 again.
6. Screen 2, Server. Fill in each box, then click Next. The lists take a moment to fill.
   - Instance name: SHORT-LABEL CRM
   - Region: the region nearest the chapter. For Boston, New York.
   - Size: s-2vcpu-4gb (2 vCPU, 4096 MB)
   - Image: the newest Ubuntu LTS release in the list
   - Extra SSH keys: tick crm-SHORT-LABEL

   *You should see:* crm-SHORT-LABEL ticked. Without it, nobody can open a command line on the server, and steps 9.4 and 9.6 cannot be done.
7. Screen 3, Domain, when you chose Cloudflare. Fill in each box, then click Next:
   - Cloudflare zone: the chapter's domain that the CRM's address ends in
   - Subdomain: the CRM's address up to the first dot. For crm.example.org, crm.
   - Let's Encrypt email: ALERT-ADDRESS

   *You should see:* Instance address showing CRM-ADDRESS exactly.
8. Screen 3, Domain, when you chose manual DNS. Fill in each box, then click Next:
   - CRM address: CRM-ADDRESS. For Boston, crm.bbmentors.org.
   - Let's Encrypt email: ALERT-ADDRESS

   *You should see:* A note saying the run will show the record to add at the domain's DNS provider.
9. Screen 4, Accounts. Fill in each box, then click Next:
   - Administrator username: admin
   - Administrator email: ALERT-ADDRESS
   - Administrator password: paste it from the CRM administrator item in the vault
   - Generate database passwords automatically (recommended): leave ticked
10. Screen 5, Review. Check that Extra SSH keys reads crm-SHORT-LABEL, not (generated key only). Then click Deploy.
    *You should see:* A window titled Deploy run DEP-NNN, with a progress bar and a log.
11. Manual DNS only: add the CRM's record while the run waits. When the status line reads Waiting for DNS, it shows the record to add. The log shows the same line. In the chapter's DNS provider account, add a record with exactly:
    - Type: A
    - Host or name: only the first part of the CRM's address, for crm.bbmentors.org just crm. Squarespace and most providers add the domain themselves, so typing the full address makes the record crm.bbmentors.org.bbmentors.org and the run never sees it. Only if the screen shows the domain is not added (no .bbmentors.org beside the box and no note saying so) type the full address.
    - Value, data or points to: the server's address from the status line
    - Proxy or forwarding: off
    - TTL: the provider's default, or the shortest it offers

    *You should see:* Within a few minutes, the status line moves on to Preparing server. The run waits up to 30 minutes for the record.
12. Wait for the run to finish. It takes place on CRMBuilder's online service, so closing the window does not stop it. To reopen it, click Deploy History, then Open progress….
    *You should see:* The status line reading Deployment complete.
13. Record the server's address. The log shows it on the line beginning Server active at. Add it to the CRM administrator item in the vault, as a note headed Server address. Later steps call it SERVER-IP.

**Done when all of these are true:**

- The run reads Deployment complete.
- The server's address is in the vault.

**How to check:** The new instance is listed on CRMBuilder's Instances page, with the same address under Droplet IP.

**If it didn't work:**

- The run names the stage that failed and keeps what it built. Do not delete anything. The server is billed until the run finishes or the server is deleted.
- Failed at Preparing server, and the log mentions Could not get lock: the new server was still setting itself up. Wait five minutes and click Retry. Retry starts again at the stage that failed.
- Manual DNS, failed at Waiting for DNS: the record was not seen within 30 minutes. Compare the record at the DNS provider with the status line, character by character, then click Retry.
- Deployment complete with verification gaps: the CRM is installed but a check failed. Read the log, and do not go on until the failed check is understood.
- Any other failure: click Retry once. If it fails again, stop the build and keep the log.

**What usually goes wrong:** Not ticking crm-SHORT-LABEL under Extra SSH keys. CRMBuilder's own key never leaves its online service, so without the tick nobody can open a command line on the server. Also, a run left on CRMBuilder's own tokens builds the server in CRMBuilder's hosting account, and nothing says so until someone looks. With manual DNS, typing the full address as the record's host: the provider adds the domain again, the name the run waits for never appears, and the run fails at Waiting for DNS after 30 minutes. Boston's first run did this at Squarespace (09-23-26).

---

## 9.4 Confirm the server works

**Why:** Before anything is copied onto the server, four things must be true. You can open a command line on it, its web address leads to it, its certificate renews by itself, and its CRM version is recorded.

**Who:** The central support organization

**Finish first:**

- step 9.3 Run CRMBuilder's deploy wizard

**Do this:**

1. Open a command line on the server. Type the line below and press Enter:
   - ssh -i ~/.ssh/crm-SHORT-LABEL root@SERVER-IP

   *You should see:* A prompt ending root@ followed by the server's name. The first time, it asks whether to continue connecting: type yes and press Enter.
2. List the programs running on the server. Type the line below and press Enter:
   - docker ps --format '{{.Names}}'

   *You should see:*

   - One name is espocrm, the CRM itself. Later steps call it CRM-CONTAINER. If it is named differently, use that name.
   - One name includes letsencrypt or certbot. That is what renews the certificate.
3. Close the command line. Type exit and press Enter.
4. Check that the CRM's address leads to the server. Type the line below and press Enter:
   - dig +short CRM-ADDRESS

   *You should see:* SERVER-IP, and nothing else.
5. Check the certificate's expiry date. Type the line below and press Enter:
   - echo | openssl s_client -connect CRM-ADDRESS:443 -servername CRM-ADDRESS 2>/dev/null | openssl x509 -noout -enddate

   *You should see:* A line beginning notAfter= with a date about ninety days away.
6. Open https://CRM-ADDRESS in a private browser window, and sign in as admin with the password from the vault.
   *You should see:* The CRM's home screen, with no certificate warning.
7. Read the CRM's version. Open Administration. The version number is shown on that page. Add it to the CRM administrator item in the vault, as a note headed CRM version.
   *You should see:* A version number of 10 or higher.
8. Store the server sign-in key. In the chapter's Operations vault, create an item named CRM server sign-in key, and attach the file ~/.ssh/crm-SHORT-LABEL to it. Share the vault with a second named person.
   *You should see:* The item in the vault, and the second person able to open it.

**Done when all of these are true:**

- A command runs on the server over the chapter's sign-in key, and the key is in the vault where a second person can open it.
- The CRM's address leads to the server.
- The CRM loads at its address with no certificate warning, and the certificate renews by itself.
- The CRM's version, 10 or higher, is in the vault.

**How to check:** Each action above showed what it should.

**If it didn't work:**

- The ssh line asks for a password or says Permission denied: the key was not ticked in step 9.3. Stop the build.
- dig shows an address other than SERVER-IP: the record is proxied. In Cloudflare, set the record to DNS only (a grey cloud). At another DNS provider, switch off proxy or forwarding.
- No letsencrypt or certbot program is running: the certificate will not renew. Stop the build.
- A version below 10: something other than CRMBuilder installed the CRM. Stop the build.

**What usually goes wrong:** A proxied record, shown as an orange cloud in Cloudflare. The certificate is issued by a direct check against the server, and the proxy blocks it. Also, the sign-in key left on one person's laptop only.

---

## 9.5 Install the two paid add-on products

**Why:** The standard permission roles refer to features inside these two products, and the CRM refuses a whole role that names a missing feature.

**Who:** The central support organization with the chapter paying for the licences

**Finish first:**

- step 9.1 Write down the versions to build with
- step 9.4 Confirm the server works

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Buy a licence for each product, Advanced Pack and Google Integration, in the chapter's name and paid by the chapter.
2. Download each product's installation file, at the version in the CRM build versions note.
3. In the CRM, open Administration, then Extensions. Upload the first file and click Install. Then do the same with the second.
   *You should see:* Both products listed as installed, at the versions in the note.

**Done when all of these are true:**

- Both products are installed at the versions in the CRM build versions note.
- Both are licensed to this chapter.

**Note:** They must be installed before step 9.7, because the roles that step creates refer to them.

**How to check:** Both appear under Administration, then Extensions, at the right versions.

**If it didn't work:** If the CRM refuses a file, check that its version supports the CRM version recorded in step 9.4.

**What usually goes wrong:** Installing them after step 9.7 instead of before. The CRM then refuses every role that names one of their features, and the run finishes half done.

---

## 9.6 Copy the standard configuration onto the server

**Why:** The standard's record types, fields, links, screen layouts and rules arrive as two folders of files, copied from Cleveland's test system, and the CRM must be rebuilt to take them in.

**Who:** The central support organization

**Finish first:**

- step 9.4 Confirm the server works
- step 9.5 Install the two paid add-on products

**Do this:**

1. Find the two configuration folders on Cleveland's test system, at 104.131.45.208. Type the line below and press Enter:
   - ssh root@104.131.45.208 "find /var/www/espocrm -type d \( -path '*Espo/Custom' -o -path '*client/custom/src' \) -not -path '*/vendor/*'"

   *You should see:* Two folder paths. The one ending Espo/Custom holds the configuration; later actions call it SOURCE-CONFIG. The one ending client/custom/src holds the screen code; later actions call it SOURCE-SCREEN-CODE.
2. Find the same two folders on the new server. Type the line below and press Enter:
   - ssh -i ~/.ssh/crm-SHORT-LABEL root@SERVER-IP "find / -type d \( -path '*Espo/Custom' -o -path '*custom/src' \) -path '*espocrm*' 2>/dev/null"

   *You should see:* Two folder paths. Later actions call the Espo/Custom one TARGET-CONFIG and the custom/src one TARGET-SCREEN-CODE. If only one appears, stop the build.
3. Copy both folders from the test system to the build computer. Type each line below and press Enter:
   - mkdir -p ~/cbm-standard/config ~/cbm-standard/screen-code
   - rsync -a root@104.131.45.208:SOURCE-CONFIG/ ~/cbm-standard/config/
   - rsync -a root@104.131.45.208:SOURCE-SCREEN-CODE/ ~/cbm-standard/screen-code/

   *You should see:* Each line returning to the prompt with no error.
4. Copy both folders from the build computer to the new server. Type each line below and press Enter:
   - rsync -a -e 'ssh -i ~/.ssh/crm-SHORT-LABEL' ~/cbm-standard/config/ root@SERVER-IP:TARGET-CONFIG/
   - rsync -a -e 'ssh -i ~/.ssh/crm-SHORT-LABEL' ~/cbm-standard/screen-code/ root@SERVER-IP:TARGET-SCREEN-CODE/

   *You should see:* Each line returning to the prompt with no error.
5. Give both folders to the web server's user, number 33. Type the line below and press Enter:
   - ssh -i ~/.ssh/crm-SHORT-LABEL root@SERVER-IP "chown -R 33:33 TARGET-CONFIG TARGET-SCREEN-CODE"
6. Rebuild the CRM. Type the line below and press Enter:
   - ssh -i ~/.ssh/crm-SHORT-LABEL root@SERVER-IP "docker exec -u www-data CRM-CONTAINER php command.php rebuild"

   *You should see:* The line returning with no error, in a few seconds.
7. Delete the copies on the build computer. Type the line below and press Enter:
   - rm -rf ~/cbm-standard
8. Reload the CRM in the browser.
   *You should see:* The normal working screen, with the navigation bar across the top.

**Done when all of these are true:**

- Both folders are on the server and owned by the web server's user.
- The rebuild finished without errors.
- The CRM shows its normal working screen.

**Note:** There are two folders, not one.

**How to check:** The CRM's navigation bar and home screen appear.

**If it didn't work:**

- A blank page: the screen code folder is missing. Copy it again, give it to user 33, rebuild, and reload.
- An error from the rebuild: stop the build and keep the error.

**What usually goes wrong:** Copying only one of the two folders. The applications still work, but the CRM's own screen is blank. Also, Cleveland's test system changes under the applications, so two chapters built a week apart can get different configurations until the standard is versioned (work list item 15).

---

## 9.7 Apply the standard with one script

**Why:** One script creates the teams, the permission roles, the email templates, the CRM's own settings and two accounts, and reads each one back to prove it.

**Who:** The central support organization

**Finish first:**

- step 9.6 Copy the standard configuration onto the server
- step 6.7 Decide where the chapter's help documentation lives

**Do this:**

1. Go to the client intake software's folder. Type the line below and press Enter:
   - cd ~/Dropbox/Projects/cbm-client-intake
2. Run the script without changing anything, to see what it would do. Type the line below and press Enter:
   - uv run python scripts/rehearsal/apply_api_half.py --env ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env --values prds/chapter-network/chapters/SHORT-LABEL-values.yaml

   *You should see:*

   - Nine teams
   - Twelve permission roles
   - Each role attached to its team
   - The email templates
   - The CRM's settings, including the tab bar and the chapter's documentation link
   - Two accounts, customapps and SHORT-LABEL.provision
3. Run it for real. Type the line below and press Enter:
   - uv run python scripts/rehearsal/apply_api_half.py --env ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env --values prds/chapter-network/chapters/SHORT-LABEL-values.yaml --apply

   *You should see:* Each item reported applied and read back identical. Three new lines at the end of CHAPTER-ENV-FILE: ESPO_API_KEY, ESPO_PROVISION_USERNAME and ESPO_PROVISION_PASSWORD. Lines marked unapplyable are explained under If it didn't work.
4. Give the Client Assignment Role the permission it needs to assign a mentor: read all users and edit its own user. The roles captured on 31 August do not include it. First see what would change. Type the line below and press Enter:
   - uv run --env-file ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env python scripts/migrate_client_assignment_role.py

   *You should see:* A plan to raise Client Assignment Role, User, to read all and edit own.
5. Apply it. Type the line below and press Enter:
   - uv run --env-file ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env python scripts/migrate_client_assignment_role.py --apply

   *You should see:* The permission reported applied.
6. Put the new secrets in the chapter's Operations vault, as three items:
   - CRM build settings: the whole of CHAPTER-ENV-FILE
   - CRM key for the applications: the value after ESPO_API_KEY=
   - CRM provisioning administrator: the values after ESPO_PROVISION_USERNAME= and ESPO_PROVISION_PASSWORD=
7. Test the applications' key. Type the line below and press Enter, with the key in place of CRM-KEY:
   - curl -s -o /dev/null -w '%{http_code}\n' -H 'X-Api-Key: CRM-KEY' https://CRM-ADDRESS/api/v1/CMentorProfile?maxSize=1

   *You should see:* 200
8. Test the provisioning administrator. Sign in at https://CRM-ADDRESS with its name and password from the vault, then sign out.
   *You should see:* The CRM's home screen, with Administration in the menu.
9. Set by hand the three things the script does not set yet (open work G1 item 2). Sign in as admin and open Administration. The exact screen labels have not been checked for this guide:
   - The company logo: the file named on the chapter information form under crm: logo_file
   - The site address: https://CRM-ADDRESS
   - A tab in the tab bar that opens the chapter's help documentation, the address on the chapter information form under web: docs_site_url. The script removes Cleveland's documentation tab and adds none.

   *You should see:* The chapter's logo at the top of the screen.
10. Look over the result in the CRM, signed in as admin:
    - Administration, then Teams: every team shows a role.
    - Email Templates: the templates are listed.
    - The documentation tab in the tab bar: it opens this chapter's help documentation, not Cleveland's.

**Done when all of these are true:**

- The script reports every team, role, attachment, template, setting and account applied and read back identical, apart from the expected leftovers described under If it didn't work.
- The Client Assignment Role can read all users.
- The applications' key answers a test request, and is in the vault.
- The provisioning administrator signs in, and its password is in the vault.
- Every team carries a role.
- The logo, the site address and the documentation tab are set.

**How to check:** Each test above showed what it should.

**If it didn't work:**

- Exit 4 with only roleField lines, such as Standard User: Account.cCompanyPartnerProfile: a finished run. Those lines name fields Cleveland's test system has since deleted, and leaving them out is correct.
- A roleScope line: an add-on product is missing. Do step 9.5, then run the script for real again. It skips what it already made.
- curl shows 401: the key was copied wrong. Copy it again from CHAPTER-ENV-FILE. curl shows 403: a permission is missing. Run the script for real again and read its unapplyable lines.
- A team with no role: run the script for real again. If the team is still empty, stop the build.

**What usually goes wrong:** Creating, renaming or editing anything here by hand. Each application page looks for an exact team name, and a team with no role gives its members nothing. Neither shows an error: the feature behind it just shows nothing. The email templates carry no chapter name on purpose and stay identical.

---

## 9.8 Stamp the configuration version

**Why:** The applications report which version of the standard their CRM holds, and they read it from a record this step creates.

**Who:** The central support organization

**Finish first:**

- step 9.7 Apply the standard with one script

**Do this:**

1. In the client intake software's folder, see what the stamp would be. Type the line below and press Enter:
   - uv run --env-file ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env python scripts/build_networkstandard.py

   *You should see:* A plan, and a line giving its fingerprint of sixteen letters and numbers. The next action calls it FINGERPRINT. The files copied in step 9.6 may already carry the record (open work G1 item 3): if the script reports nothing to do, skip the next action.
2. Create the record. Type the line below and press Enter:
   - uv run --env-file ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env python scripts/build_networkstandard.py --apply --production --expect FINGERPRINT

   *You should see:* The record created, and read back with the applications' key.

**Done when:** The record exists, and the applications' key can read it.

**How to check:** The script reports the record read back.

**If it didn't work:** If it says the plan moved, run the first line again and use the new fingerprint.

**What usually goes wrong:** Stamping a CRM that step 9.7 did not finish. A CRM claiming a version it does not hold is worse than one claiming nothing. Also, running the script without --env-file: it then falls back to the settings of Cleveland's test system.

---

## 9.9 Run the checking tool

**Why:** This is the proof that the chapter's CRM matches the standard, and so that the next release of the software will work on it.

**Who:** The central support organization

**Finish first:**

- step 9.8 Stamp the configuration version

**Do this:**

1. In the client intake software's folder, run the check and read its report. Type the line below and press Enter:
   - uv run --env-file ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env sh -c 'python scripts/preflight_crm.py --url "$ESPO_ADMIN_BASE" --key "$ESPO_API_KEY"'

   *You should see:* A last line beginning RESULT:. Today the expected result is DRIFT, listing only the five missing event email templates.
2. Save the result as a file. Type the line below and press Enter:
   - uv run --env-file ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env sh -c 'python scripts/preflight_crm.py --url "$ESPO_ADMIN_BASE" --key "$ESPO_API_KEY" --json' > ~/.config/cbm-SHORT-LABEL/preflight.json
3. Attach ~/.config/cbm-SHORT-LABEL/preflight.json to the CRM build settings item in the vault.
4. Write each difference that is allowed on purpose, with its reason, in the chapter's entry in the list of watched systems (step 12.5).

**Done when:** The checking tool reports that the CRM matches the standard, apart from differences that are written down with their reasons.

**How to check:** The report lists nothing that is not written down in the list of watched systems.

**If it didn't work:**

- RESULT: DRIFT with anything other than the five event email templates: go back to the step that makes the missing item, usually step 9.7, and run it again.
- RESULT: UNCHECKED: the tool could not reach the CRM or its key was refused. Check the address and key in CHAPTER-ENV-FILE.

**What usually goes wrong:** Running the tool without --env-file. It then checks Cleveland's test system instead of the chapter's CRM, and reports on the wrong system.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.12 | 09-23-26 22:55 | Two known defects written into the steps (open work G1 items 2 and 3). Step 9.7 sets the logo, the site address and the documentation tab by hand, because the script sets none of them and removes Cleveland's documentation tab; its finishing test gains that condition. Step 9.8 says the script may report nothing to do, because the copied files can already carry the record. |
| 0.11 | 09-23-26 20:40 | Rewritten and renumbered from twenty steps to nine (Doug, 09-23-26: the stage was terribly hard to understand and use). The old step list hid the work: step 9.10 ran one script that did seven steps, and six steps said only "nothing extra to run". Old to new: 9.1 → 9.1; 9.2 → 9.2 (the key, the password and the settings file) and 9.3 (the wizard); 9.3, 9.4, 9.5 and 9.6 → 9.4; 9.7 → 9.5; 9.8 and 9.9 → 9.6; 9.10 to 9.15, 9.17 and 9.18 → 9.7; 9.19 → 9.8; 9.20 → 9.9. Step 9.16, which could not be done, moved to a list of what is still owed at the top of the stage, with the missing event templates and the unruled server size. The wizard's Cloudflare and manual DNS screens are written as separate actions. The settings file is made before the wizard, so the password rule is stated once. Scripts read the settings file through uv's --env-file rather than a shell pipeline. The manual DNS record's host is now only the first part of the CRM's address, from Boston's first run at Squarespace (a fix from the CRMBuilder session, 09-23-26). Each failure case has its own line. The August build's history moved out of the actions; it stays in 3-Methods-CRM-Google-Applications.md, which keeps the old numbers. |
| 0.10 | 09-23-26 14:27 | The placeholder CHAPTER-SLUG is now SHORT-LABEL, the form's own name for it (Doug, 09-23-26: slug is a terrible name for a user). The guide's index lists every shared placeholder. |
| 0.9 | 09-23-26 13:54 | Manual DNS added (Doug, 09-23-26): CRMBuilder's wizard now asks on its first page whether the CRM's address is managed through Cloudflare or by hand at the chapter's own DNS provider. Step 9.2 chooses from the DNS provider item in the vault, fills in the CRM address box that manual DNS shows, and adds the A record by hand when the run shows it; its failure advice covers the 30-minute wait and Retry. Step 9.5 checks the record at the chapter's DNS provider. Screen labels read from CRMBuilder's code (commit 7b1a5062); the first page's DNS list was seen on screen by Doug on 09-23-26. |
| 0.8 | 09-23-26 13:51 | Step 9.2 rewritten in executive register (Doug, 09-23-26: it said "this computer" without saying which). It names the build computer, the central support organization's own computer with CRMBuilder installed, and uses that name for every command; defines an SSH key at first use; gives the change of folder its own action; and moves explanations out of the actions into what the reader should see. Step 9.8's two "this computer" now say the build computer. |
| 0.7 | 09-23-26 13:41 | Steps 9.1 and 9.3 brought in line with the ruling that a new chapter runs the current CRM release and Cleveland moves up later (Doug, 09-23-26). Step 9.1 writes down "the current release CRMBuilder installs" rather than Cleveland's version, and checks each add-on supports version 10. Step 9.3 records the exact number instead of comparing it, since CRMBuilder cannot install any other. Both finishing tests changed with the step list (version 0.18). |
| 0.6 | 09-23-26 13:39 | Step 9.2 points to step 5.8 for the chapter's engagement, which 5.8 now creates, instead of stopping to ask. |
| 0.5 | 09-23-26 13:35 | Step 9.2 rewritten click by click from CRMBuilder's deploy wizard (Doug, 09-23-26: the step was not clear). Named every screen, box and stage, and three facts the old text hid: CRMBuilder's own sign-in key never leaves its service, so the key ticked under Extra SSH keys must first be made and added to the chapter's DigitalOcean account; the wizard's Generate button can put - or _ in the password, which step 9.10 cannot take; and a Preparing server failure on a fast run is cured by Retry. Step 9.4 now names that key. |
| 0.4 | 09-23-26 00:55 | Step 9.11 now runs scripts/migrate_client_assignment_role.py. The roles captured on 31 August give the Client Assignment Role no User permission, so a client administrator on that team alone was refused on Assign (ruled 09-07-26). Its If it didn't work now tells an expected exit 4 (a field the source deleted) from a real one (an add-on missing); the old advice to install the add-ons and run again never ended. Found in the review before the first real chapter. |
| 0.3 | 09-19-26 00:50 | The script now reads the chapter's name, CRM settings and provisioning account (SHORT-LABEL.provision) from the chapter information form through --values; the step that edited Lakeside's name out of the script by hand is gone. |
| 0.2 | 09-19-26 00:07 | Every command-line action made exact (Doug, 09-19-26: sweep every step): the ssh, docker, find, rsync, chown and rebuild commands for copying the configuration; the trial scripts' exact options, including the name the provisioning account takes and the production option the version record needs; the test request for the applications' key; and the conformance check with its exit codes. Two traps written in: the scripts fill missing values from the repository's own settings, which are Cleveland's, and the settings file's password must be letters and numbers only. |
| 0.1 | 09-18-26 17:05 | First version as data, converted from the methods for building the CRM (3-Methods-CRM-Google-Applications.md, version 0.5) with the step list's finishing tests. Numbered actions, a reason per step, and a check an app can run were added. |
