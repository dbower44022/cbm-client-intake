# Stage 9 — Build the CRM system

**Version:** 0.9  
**Last Updated:** 09-23-26 13:54  
**Generated from** `steps/stage-09.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The CRM is the chapter's system of record: every client, mentor, partner, funder and meeting lives in it, and every application reads and writes it. This stage builds the chapter's own CRM on the chapter's own server and makes it identical to every other chapter's, so that one release of the software works for all of them.

**Who:** The central support organization, working inside the chapter's accounts.  
**Time:** About half a day when nothing goes wrong. The August build of the trial chapter took most of a day, including the failures it found.  
**When this stage is done:** The Google permissions (stage 10) and the applications (stage 11) can start. The applications need the CRM's key, which this stage creates.

**Before you start:**

- The chapter information form, complete and reviewed (stage 8)
- The chapter's hosting account, with the central support organization's access (steps 5.1 and 5.4)
- The chapter's domain names in its Cloudflare account, or at its own DNS provider with manual DNS (step 3.7)
- The chapter's own DigitalOcean token, and its Cloudflare token unless it uses manual DNS, entered in CRMBuilder (step 5.8)
- The chapter's vault, for every secret this stage creates (step 2.7)

**Steps in this stage:**

- 9.1 Obtain the current standard from the central support organization
- 9.2 Create the server
- 9.3 Install the CRM software at the version the standard names
- 9.4 Confirm command line access, and record who holds the key
- 9.5 Point the CRM's web address at the server
- 9.6 Publish the CRM at its own web address
- 9.7 Install the two paid add-on products
- 9.8 Copy on the standard configuration files
- 9.9 Confirm the CRM's own screen loads
- 9.10 Create the teams
- 9.11 Create the permission roles
- 9.12 Attach the roles to the teams
- 9.13 Create the email templates
- 9.14 Apply the instance settings
- 9.15 Apply the navigation tabs and the quick-add list
- 9.16 Apply the standard's duplicate checking, saved views and automated rules
- 9.17 Create the account the applications sign in with
- 9.18 Create the administrator account for the central support organization
- 9.19 Create the configuration version record
- 9.20 Run the checking tool until it reports no differences

---

## 9.1 Obtain the current standard from the central support organization

**Why:** Every later step checks against three version numbers, so they have to be fixed before anything is installed.

**Who:** The central support organization

**Finish first:** nothing.

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Write down three version numbers:
   - The CRM version.
   - The version of each of the two paid add-on products.
   - The release of the standard configuration this chapter will get.
   *You should see:* Three version numbers, written where the rest of the stage can read them.
2. For the CRM version, write down: the current release CRMBuilder installs. A new chapter takes the current release, and Cleveland's systems move up to it later (ruled 09-23-26). CRMBuilder's deploy cannot install any other version, so the exact number is only known once the server exists; step 9.3 records it.
3. For the other two, there is no published statement of the standard yet. Until there is, use the add-on versions Cleveland's production system runs, and the date its configuration was last captured.
   *You should see:* Each add-on version marked by its maker as supporting CRM version 10. If one is not, stop and ask: Cleveland's own add-ons have not yet been checked against version 10.

**Done when all of these are true:**

- The chapter's build has, in writing, the CRM version to install: the current release CRMBuilder installs.
- The build has, in writing, the version of each of the two add-on products.
- The build has, in writing, which release of the standard configuration is being applied.

**Note:** Without these three numbers the later steps have nothing to check against.

**How to check:** The three numbers are written down.

**If it didn't work:** Do not start the build. Ask the central support organization for the three numbers.

**What usually goes wrong:** Writing down the CRM version Cleveland's test system runs, 9.3.4. CRMBuilder cannot install it, and a new chapter does not take it: it takes the current release. The August build installed 10.0.6 and the configuration captured from 9.3.4 rebuilt cleanly on it.

---

## 9.2 Create the server

**Why:** The CRM needs a server of its own, in the chapter's own hosting account, so the chapter owns it.

**Who:** The central support organization inside the chapter's hosting account

**Finish first:**

- step 5.4 Grant the central support organization access to the hosting account
- step 5.8 Create the two tokens CRMBuilder builds with
- step 3.7 Move the domain names' DNS to the chapter's Cloudflare account

**Do this:**

1. Work at the build computer: the central support organization's own computer, the one with CRMBuilder installed. Every command in this step is typed in a terminal window on the build computer.
2. Create an SSH key for the central support organization. An SSH key is the file that lets a person open a command line on the server. Type the line below, press Enter, then press Enter twice more to leave the key without a passphrase:
   - ssh-keygen -t ed25519 -f ~/.ssh/crm-CHAPTER-SLUG -C crm-CHAPTER-SLUG
   *You should see:* Two new files on the build computer: ~/.ssh/crm-CHAPTER-SLUG, the private key, which later steps call KEY-FILE; and ~/.ssh/crm-CHAPTER-SLUG.pub, the public key.
3. Register the public key in the chapter's DigitalOcean account: open Settings, then Security, then add an SSH key. Paste the contents of ~/.ssh/crm-CHAPTER-SLUG.pub, and name the key crm-CHAPTER-SLUG. DigitalOcean's exact screen wording has not been checked for this guide.
   *You should see:* The key crm-CHAPTER-SLUG in the account's list of SSH keys.
4. Create the CRM administrator password in Proton Pass: a new item in the chapter's Operations vault, named CRM administrator, with the user name admin and a generated password of 24 characters, letters and numbers only (symbols off).
   *You should see:* A password of letters and numbers only. Step 9.10 cannot use any other character, which is why CRMBuilder's own Generate button is not used: it can add - or _.
5. Go to CRMBuilder's folder. Type the line below and press Enter:
   - cd ~/Dropbox/Projects/crmbuilder
6. Start CRMBuilder. Type the line below and press Enter:
   - ./start-v2.sh
   *You should see:* CRMBuilder's main window. If a window titled Cloud backend not configured appears instead, the build computer is not connected to CRMBuilder's online service: stop and ask.
7. Select the chapter's engagement. Click the strip across the top of the window, which names the current engagement, and choose the chapter's.
   *You should see:* The chapter's engagement named in the strip. If it is not in the list, step 5.8 is not finished.
8. Open the deploy window. Click the tab 11 · CRM Deployment, then Instances in the side bar, then Deploy new… on the toolbar. Do not use New Instance: it only records a CRM that already exists.
   *You should see:* A window titled Deploy a new CRM instance, open at Step 1 of 5 — Providers.
9. Step 1, Providers. In the DNS list, choose the entry that matches the DNS provider item in the chapter's Operations vault (step 3.7):
   - Cloudflare — the run creates the record: the chapter's DNS is at Cloudflare.
   - Manual DNS — I add the record at the domain's own DNS provider: the chapter kept its own DNS provider.
   *You should see:* The DNS list showing the entry that matches the vault.
10. Step 1, Providers. Confirm both lines name the chapter's own tokens, by the label given in step 5.8, then click Next. With manual DNS, only the DigitalOcean line matters; the Cloudflare line may read Not set:
   - DigitalOcean: ✓ Configured — crmbuilder-CHAPTER-SLUG
   - Cloudflare: ✓ Configured — crmbuilder-CHAPTER-SLUG
   *You should see:* Both labels exactly as above. Any other label, or Not set, means the server would be built in the wrong account: click Set credentials… and repeat step 5.8's token actions first.
11. Step 2, Server. Fill in each box, then click Next. The lists come from the chapter's DigitalOcean account and take a moment to fill.
   - Instance name: CHAPTER-SLUG CRM, using the chapter's short label from step 8.2
   - Region: the region nearest the chapter; for Boston, New York
   - Size: s-2vcpu-4gb (2 vCPU, 4096 MB), a recommendation not yet ruled
   - Image: the newest Ubuntu LTS release in the list
   - Extra SSH keys: tick crm-CHAPTER-SLUG
   *You should see:* crm-CHAPTER-SLUG ticked. Without it, nobody can open a command line on the server, and steps 9.4 and 9.8 cannot be done.
12. Step 3, Domain. Fill in each box from the chapter information form, then click Next:
   - Cloudflare zone: the chapter's domain that the CRM's address ends in
   - Subdomain: the CRM's address up to the first dot; for crm.example.org, crm
   - Let's Encrypt email: the alert receiving address
   *You should see:* Instance address showing the CRM's address exactly as the chapter information form has it, without https://.
13. Step 3, Domain, with manual DNS. The page shows different boxes. Fill in each one from the chapter information form, then click Next:
   - CRM address: the CRM's full address, without https://; for Boston, crm.bbmentors.org
   - Let's Encrypt email: the alert receiving address
   *You should see:* A note on the page saying the run will show the A record to add at the domain's DNS provider.
14. Step 4, Accounts. Fill in each box, then click Next:
   - Administrator username: admin
   - Administrator email: the alert receiving address from the chapter information form
   - Administrator password: paste it from the CRM administrator item in the vault
   - Generate database passwords automatically (recommended): leave ticked
   *You should see:* A reminder to record the administrator password. It is already in the vault; CRMBuilder never shows it again.
15. Step 5, Review. Check every line against what was entered, then click Deploy.
   *You should see:* Extra SSH keys reading crm-CHAPTER-SLUG, not (generated key only). With manual DNS, the line DNS reading manual DNS — you add the A record when the run shows it. Then a window titled Deploy run DEP-NNN, with a progress bar and a log.
16. With manual DNS, the run stops at Waiting for DNS until the CRM's record exists, so add it by hand while the run waits. When the status line reads Waiting for DNS, it also shows the record, in the words Add this DNS record at the domain's DNS provider: type A, name, then the CRM's address, value, then the server's address. The log shows the same line. In the chapter's DNS provider account, add a record with exactly:
   - Type: A
   - Name or host: the CRM's address, or only its first part (for crm.bbmentors.org, crm), whichever the provider's screen asks for
   - Value, data or points to: the server's address from the status line
   - Proxy or forwarding: off
   - TTL: the provider's default, or the shortest it offers
   *You should see:* Within a few minutes, a log line saying the CRM's address resolves to the server's address on public resolvers, and the status line moving on to Preparing server. The run waits up to 30 minutes for the record.
17. Wait for the run to finish. The status line names each of its ten stages in turn:
   - Checking credentials
   - Creating server
   - Waiting for server
   - Setting DNS
   - Waiting for DNS
   - Preparing server
   - Installing CRM
   - Post-install checks
   - Verifying
   - Registering instance
   *You should see:* The status line reading Deployment complete. The run takes place on CRMBuilder's online service, not on the build computer, so closing the window does not stop it. To reopen it, click Deploy History, then Open progress….
18. Record the server's address. The log shows it on the line beginning Server active at. Later steps call it SERVER-IP.
   *You should see:* The same address under Droplet IP, in the Deploy config section of the new instance on the Instances page.
19. In Proton Pass, add the server's address to the CRM administrator item, as a note headed Server address.

**Done when:** A server is running in the chapter's own hosting account and the central support organization can reach it.

**How to check:** The server appears in the chapter's hosting account, the run reads Deployment complete, and the new instance is listed on CRMBuilder's Instances page.

**If it didn't work:** The run keeps what it built, names the stage that failed, and bills for the server until it is finished or deleted. Do not delete anything. If the failed stage is Preparing server and the log mentions Could not get lock, the new server was still setting itself up: wait five minutes and click Retry, which starts again at the stage that failed. With manual DNS, a failure at Waiting for DNS means the record was not seen within 30 minutes: check the record at the chapter's DNS provider against the status line, character by character, then click Retry, which waits again on the same server. Deployment complete with verification gaps means the CRM is installed but a check failed: read the log, and stop and ask before going on. Anything else: stop, and ask the central support organization to retry from the failed stage.

**What usually goes wrong:** Not ticking crm-CHAPTER-SLUG under Extra SSH keys. The run then leaves nobody with a command line on the server, because CRMBuilder's own key never leaves its service, and steps 9.4 and 9.8 become impossible. The August build hit this and had to paste a key through the hosting provider's own console as a rescue. Also, a run left on CRMBuilder's own tokens builds the server in CRMBuilder's hosting account, and nothing says so until someone looks.

---

## 9.3 Install the CRM software at the version the standard names

**Why:** Every chapter must run the same CRM version, or a release built for one may break another.

**Who:** The central support organization

**Finish first:**

- step 9.1 Obtain the current standard from the central support organization
- step 9.2 Create the server

**Do this:**

1. Sign in to the new CRM as the administrator the wizard created, and open the Administration page.
   *You should see:* The installed version number, shown on the Administration page. It is 10 or higher.
2. In Proton Pass, add the number to the CRM administrator item in the chapter's Operations vault, as a note headed CRM version.
3. Send the number to the central support organization, which records it against the chapter.
   *You should see:* A reply confirming it is recorded.

**Done when:** The installed version is the current release CRMBuilder installs, and its exact number is recorded where the central support organization can find it.

**Note:** Ruled 09-23-26: a new chapter takes the current release, and Cleveland's systems move up to it later.

**How to check:** The version on the CRM's administration page is 10 or higher, and matches the number the central support organization recorded.

**If it didn't work:** A number below 10 means something other than CRMBuilder's deploy installed the CRM. Stop, and ask the central support organization.

**What usually goes wrong:** Not recording the number. Until Cleveland moves up (task C1 in the chapter network task list), the network runs two major CRM versions, and a problem found on one may not happen on the other. The recorded number is what tells the two apart.

---

## 9.4 Confirm command line access, and record who holds the key

**Why:** Copying the configuration files (step 9.8) needs a command line on the server, and the key must not live on one laptop.

**Who:** The central support organization

**Finish first:**

- step 9.2 Create the server

**Do this:**

1. In a terminal, type the line below and press Enter, with SERVER-IP the server's address and KEY-FILE the private key ~/.ssh/crm-CHAPTER-SLUG, both from step 9.2:
   - ssh -i KEY-FILE root@SERVER-IP
   *You should see:* The server's prompt, ending root@ followed by the server's name.
2. Type the line below and press Enter, to confirm the CRM is running in its container:
   - docker ps --format '{{.Names}}'
   *You should see:* A list of container names, one of them espocrm. Later steps call that name CRM-CONTAINER; if it is named differently, use that name instead.
3. Type exit and press Enter.
4. In Proton Pass, add an item to the chapter's Operations vault named CRM server sign-in key, and attach KEY-FILE to it.
   *You should see:* The item in the vault, with a second named person able to open it.

**Done when:** The central support organization can open a command line on the server, and the key that allows it is recorded in the secrets store with at least two people able to reach it. The server can be created without this access, and the next steps cannot be done without it.

**How to check:** A command runs on the server and returns, and a second person can open the key in the vault.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The key exists on one person's laptop only.

---

## 9.5 Point the CRM's web address at the server

**Why:** People and the applications reach the CRM by its name, so the name must lead to the server.

**Who:** The central support organization

**Finish first:**

- step 3.7 Move the domain names' DNS to the chapter's Cloudflare account
- step 9.2 Create the server

**Do this:**

1. Nothing to do by hand. The wizard wrote the record in step 9.2. Open the chapter's Cloudflare account, then the domain, then DNS.
   *You should see:* An A record for the CRM's address, pointing at the server, marked "DNS only" with a grey cloud.
2. With manual DNS, the record was added by hand during step 9.2. Open the domain's DNS records in the chapter's DNS provider account instead.
   *You should see:* An A record for the CRM's address, pointing at the server, with no proxy or forwarding.

**Done when:** The domain name record for the CRM address resolves to the server.

**How to check:** A name lookup on the CRM's address returns the server's own address, not one of Cloudflare's.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The proxy switched on, an orange cloud. The CRM's certificate is issued by a direct check against the server, and the proxy blocks it.

---

## 9.6 Publish the CRM at its own web address

**Why:** A secure connection protects every sign-in, and a certificate that is not renewed automatically takes the whole system down about ninety days later.

**Who:** The central support organization

**Finish first:**

- step 9.5 Point the CRM's web address at the server

**Do this:**

1. Open https://CRM-ADDRESS in a private browser window.
   *You should see:* The CRM's sign-in page, with no certificate warning.
2. Sign in to the server as in step 9.4 and type the line below and press Enter, to list the running containers:
   - docker ps --format '{{.Names}}'
   *You should see:* A container whose name includes letsencrypt or certbot, which is what renews the certificate. The exact name depends on the installer version and is not checked for this guide; if no such container is listed, stop and ask.
3. Type the line below and press Enter, with the CRM's address in place of CRM-ADDRESS, to read the certificate's expiry date:
   - echo | openssl s_client -connect CRM-ADDRESS:443 -servername CRM-ADDRESS 2>/dev/null | openssl x509 -noout -enddate
   *You should see:* A line beginning notAfter= with a date about ninety days away.

**Done when:** The CRM loads at its address over a secure connection, and the security certificate is set to renew by itself. A certificate that has to be renewed by hand will expire and take the system down.

**How to check:** The sign-in page loads with no warning, and the renewal is scheduled.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A certificate that has to be renewed by hand. It expires about ninety days after go-live and the whole system stops.

---

## 9.7 Install the two paid add-on products

**Why:** The standard permission roles refer to features inside these two products, and the CRM refuses a role that names a missing feature.

**Who:** The central support organization with the chapter paying for the licences

**Finish first:**

- step 9.3 Install the CRM software at the version the standard names
- step 9.1 Obtain the current standard from the central support organization

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Buy a licence for each of the two products in the chapter's name.
2. In the CRM, open Administration, then Extensions, and upload each product.
   *You should see:* Both products listed as installed, at the versions from step 9.1.

**Done when all of these are true:**

- Both are installed at the versions the standard names.
- Both are licensed to this chapter.
- Both are listed in the CRM's own list of installed products.

**Note:** They must be installed before the permission roles are created, because the roles refer to them.

**How to check:** Both appear in the CRM's list of installed products, at the right versions.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Doing this after the permission roles instead of before. The CRM then rejects each whole role. The August build hit this: seventy-one role entries had to be stripped out and the run finished in a partial state.

---

## 9.8 Copy on the standard configuration files

**Why:** The standard's records, fields, links, screen layouts and rules arrive as two sets of files, and the CRM must be rebuilt to take them in.

**Who:** The central support organization

**Finish first:**

- step 9.4 Confirm command line access, and record who holds the key
- step 9.7 Install the two paid add-on products

**Do this:**

1. Sign in to the source system, Cleveland's test system, and find the two configuration folders. Type the line below and press Enter:
   - ssh root@104.131.45.208 "find /var/www/espocrm -type d \( -path '*Espo/Custom' -o -path '*client/custom/src' \) -not -path '*/vendor/*'"
   *You should see:* Two folder paths, one ending Espo/Custom and one ending client/custom/src. Later actions call them SOURCE-CONFIG and SOURCE-SCREEN-CODE. In August the first was under data/espocrm/custom.
2. Sign in to the new server and find the same two folders there. Type the line below and press Enter:
   - ssh -i KEY-FILE root@SERVER-IP "find / -type d \( -path '*Espo/Custom' -o -path '*custom/src' \) -path '*espocrm*' 2>/dev/null"
   *You should see:* Two folder paths. Later actions call them TARGET-CONFIG and TARGET-SCREEN-CODE. On the newer installer the first is under data/espocrm/persistent/custom, and the screen code sits in a second folder beside it (August finding F13). If only one appears, stop and ask.
3. On the build computer, copy both folders down, then up to the new server. Type each line below and press Enter:
   - mkdir -p ~/cbm-standard/config ~/cbm-standard/screen-code
   - rsync -a root@104.131.45.208:SOURCE-CONFIG/ ~/cbm-standard/config/
   - rsync -a root@104.131.45.208:SOURCE-SCREEN-CODE/ ~/cbm-standard/screen-code/
   - rsync -a -e 'ssh -i KEY-FILE' ~/cbm-standard/config/ root@SERVER-IP:TARGET-CONFIG/
   - rsync -a -e 'ssh -i KEY-FILE' ~/cbm-standard/screen-code/ root@SERVER-IP:TARGET-SCREEN-CODE/
   *You should see:* Each command returning to the prompt with no error. In August the configuration folder held 791 files.
4. Make the web server user the owner of both folders. The web server user inside the CRM's container is number 33. Type the line below and press Enter:
   - ssh -i KEY-FILE root@SERVER-IP "chown -R 33:33 TARGET-CONFIG TARGET-SCREEN-CODE"
5. Rebuild the CRM. Type the line below and press Enter:
   - ssh -i KEY-FILE root@SERVER-IP "docker exec -u www-data CRM-CONTAINER php command.php rebuild"
   *You should see:* The command returning with no error. In August it took three seconds.
6. Delete ~/cbm-standard from the build computer.

**Done when all of these are true:**

- Both sets of configuration files are in place.
- Both sets are owned by the web server user.
- The rebuild command has finished without errors.

**Note:** There are two sets, not one.

**How to check:** The rebuild log shows no errors, and step 9.9 shows a working screen.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Copying only one of the two sets. The applications still work, but the CRM's own screen is blank. Also, until the standard is versioned (work list item 15), the source is Cleveland's test system, which changes under the application.

---

## 9.9 Confirm the CRM's own screen loads

**Why:** A blank screen is the only sign that one of the two sets of files is missing, so it is checked by eye before going on.

**Who:** The central support organization

**Finish first:**

- step 9.8 Copy on the standard configuration files

**Do this:**

1. Open the CRM's address in a browser and sign in as the administrator.
   *You should see:* The normal working screen, with the navigation bar across the top.

**Done when:** An administrator signs in and sees the normal working screen. A blank page here means one of the two sets of files is missing.

**How to check:** The navigation bar and the home screen appear.

**If it didn't work:** A blank page means the screen code folder from step 9.8 is missing. Copy it, rebuild, and look again.

---

## 9.10 Create the teams

**Why:** Every page in the applications is opened by team membership, and each gate looks for an exact team name.

**Who:** The central support organization

**Finish first:**

- step 9.9 Confirm the CRM's own screen loads

**Do this:**

1. Make the chapter's settings file, CHAPTER-ENV-FILE, at ~/.config/cbm-CHAPTER-SLUG/CHAPTER-SLUG.env, outside the code repository. Put these three lines in it, using the administrator account the deployment wizard created:
   - ESPO_ADMIN_BASE=https://CRM-ADDRESS
   - ESPO_ADMIN_USER=the wizard's administrator user name
   - ESPO_ADMIN_PASS=the wizard's administrator password
2. The administrator password must be letters and numbers only, because later steps pass this file's values on a command line. If the wizard's password has any other character, change it in the CRM first (Administration, then Users), and put the new one in the file.
3. Type the line below and press Enter. It changes nothing, and reports what it would do:
   - uv run python scripts/rehearsal/apply_api_half.py --env ~/.config/cbm-CHAPTER-SLUG/CHAPTER-SLUG.env --values CHAPTER-VALUES-FILE
   *You should see:* A list of teams, roles, attachments, email templates, two accounts and settings it would create.
4. Type the line below and press Enter. It creates everything in steps 9.10 to 9.14, 9.17 and 9.18:
   - uv run python scripts/rehearsal/apply_api_half.py --env ~/.config/cbm-CHAPTER-SLUG/CHAPTER-SLUG.env --values CHAPTER-VALUES-FILE --apply
   *You should see:* Nine teams reported applied, and the new values ESPO_API_KEY, ESPO_PROVISION_USERNAME and ESPO_PROVISION_PASSWORD added to the end of CHAPTER-ENV-FILE.
5. Put CHAPTER-ENV-FILE's contents in the chapter's Operations vault as an item named CRM build settings.

**Done when:** Every team the standard names exists, spelled exactly as the standard spells it.

**How to check:** The teams list in the CRM matches the standard, letter for letter.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A misspelled team name. The feature behind it becomes unreachable, and the error names nothing useful.

---

## 9.11 Create the permission roles

**Why:** Roles decide what each team may read and change. They are what keeps a mentor to their own clients.

**Who:** The central support organization

**Finish first:**

- step 9.7 Install the two paid add-on products
- step 9.10 Create the teams

**Do this:**

1. Nothing extra to run for the roles themselves. The script in step 9.10 creates the roles, checking each one against what this CRM has before writing it.
   *You should see:* Every role reported applied and read back identical. Lines marked unapplyable are explained under If it didn't work.
2. Give the Client Assignment Role the User permission it needs to assign a mentor. The roles captured on 31 August predate this ruling (Doug, 09-07-26). In the folder ~/Dropbox/Projects/cbm-client-intake, type the line below and press Enter. It changes nothing:
   - env $(grep -v '^#' ~/.config/cbm-CHAPTER-SLUG/CHAPTER-SLUG.env | xargs) uv run python scripts/migrate_client_assignment_role.py
   *You should see:* A plan to raise Client Assignment Role, User, to read all and edit own.
3. Type the line below and press Enter:
   - env $(grep -v '^#' ~/.config/cbm-CHAPTER-SLUG/CHAPTER-SLUG.env | xargs) uv run python scripts/migrate_client_assignment_role.py --apply
   *You should see:* The grant reported applied. Running the first line again reports nothing to do.

**Done when:** Every role the standard names exists, and reading each one back matches what was sent.

**How to check:** The script reports every role read back identical, with nothing removed.

**If it didn't work:** The script ends with exit 4 whenever it had to leave an entry out, and it always does here. Read the unapplyable lines. A roleField line, such as Standard User: Account.cCompanyPartnerProfile, names a field the source CRM has since deleted; it is expected, and leaving it out is correct. A roleScope line names a whole feature the CRM does not have, which means an add-on product is missing: install it (step 9.7) and run step 9.10's apply line again. Exit 4 with only roleField lines is a finished run.

**What usually goes wrong:** Two things, both seen in August. An entry naming a feature the CRM does not have: the CRM refuses the entire role, not just that entry. And an entry naming a field since deleted on the source: the target refuses the whole role for it, so the source needs cleaning.

---

## 9.12 Attach the roles to the teams

**Why:** A team gives its members permissions only through the roles attached to it.

**Who:** The central support organization

**Finish first:**

- step 9.11 Create the permission roles

**Do this:**

1. Nothing extra to run. The script in step 9.10 attaches them.
   *You should see:* Every attachment reported applied.
2. In the CRM, open Administration, then Teams, and open each team.
   *You should see:* Every team carrying a role. None empty.

**Done when:** Each team carries the role it is meant to carry, and no team is left without one. A team with no role gives its members no access at all.

**How to check:** No team in the list has an empty role.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A team with no role. Its members can read nothing, and nobody notices until someone on that team tries to work. Two of Cleveland's own test-system teams are in this state.

---

## 9.13 Create the email templates

**Why:** The applications send their standard emails, such as the mentor assignment notice, from these templates.

**Who:** The central support organization

**Finish first:**

- step 9.9 Confirm the CRM's own screen loads

**Do this:**

1. Nothing extra to run. The script in step 9.10 creates them.
   *You should see:* The templates listed in the CRM under Email Templates.

**Done when:** Every template the standard names exists.

**How to check:** Every template the standard names is in the CRM.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Editing them per chapter. They carry no chapter name, on purpose, and must stay identical. Also, five event templates the standard names exist nowhere yet (work list item 18).

---

## 9.14 Apply the instance settings

**Why:** The CRM's own name, sending name and address, logo and locale are the chapter's, and anything the CRM sends directly uses them.

**Who:** The central support organization

**Finish first:**

- step 9.9 Confirm the CRM's own screen loads

**Do this:**

1. Nothing extra to run. The script in step 9.10 applies them from the chapter information form and reads them back.
   *You should see:* Each setting reported equal to what was sent.

**Done when all of these are true:**

- The chapter's name is set.
- The sending name is set.
- The sending address is set.
- The web address is set.
- The logo is set.
- The time zone is set.
- The date format is set.
- The time format is set.
- The currency is set.
- The language is set.
- The week start is set.
- All of them are set from the chapter information form, and reading them back matches.

**How to check:** Each setting reads back equal to the form.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The sending name here is separate from anything the applications show. Anything the CRM sends directly carries this name. Also, currency fields refuse to save unless the currency setting is right.

---

## 9.15 Apply the navigation tabs and the quick-add list

**Why:** Staff find their way around the CRM by its tab bar, which must be the standard one with the chapter's own help link.

**Who:** The central support organization

**Finish first:**

- step 9.14 Apply the instance settings
- step 6.7 Decide where the chapter's help documentation lives

**Do this:**

1. Nothing extra to run. The script in step 9.10 applies them.
2. Open the CRM and click the documentation tab.
   *You should see:* The chapter's own help documentation, not another chapter's.

**Done when all of these are true:**

- The tabs match the standard.
- The chapter's own documentation link is in place of any other chapter's.
- The list of records staff can add quickly matches the standard.

**How to check:** The tab bar matches, and the documentation tab opens this chapter's documentation.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The documentation link is the one tab that differs per chapter, and it is easy to leave pointing at Cleveland's.

---

## 9.16 Apply the standard's duplicate checking, saved views and automated rules

**Why:** The client intake software behaves differently depending on the CRM's duplicate checking, so every chapter must have the same settings.

**Who:** The central support organization

**Finish first:**

- step 9.9 Confirm the CRM's own screen loads

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Not possible yet. The standard does not say what these settings are, because nobody has examined them on either existing system (work list item 3).

**Done when:** The settings the standard names are applied and read back correctly. The standard does not yet say what they are, because nobody has ever examined them on the existing systems. Deciding them is work owed before any chapter reaches this step. See the work list document.

**How to check:** Cannot be checked until the standard says what is expected.

**If it didn't work:** Record the step as blocked and carry on.

**What usually goes wrong:** Duplicate checking is not only a convenience. The intake software's behaviour depends on it, and that dependency has never been tested either way.

---

## 9.17 Create the account the applications sign in with

**Why:** The applications reach the CRM with an account of their own, and the key it creates is the first secret stage 11 needs.

**Who:** The central support organization

**Finish first:**

- step 9.12 Attach the roles to the teams

**Do this:**

1. Nothing extra to run. The script in step 9.10 created the account customapps, attached its role, and added its key to CHAPTER-ENV-FILE as ESPO_API_KEY.
2. Copy the value after ESPO_API_KEY= into a new item in the chapter's Operations vault named CRM key for the applications.
   *You should see:* The item in the Operations vault.
3. Type the line below and press Enter, with the key in place of CRM-KEY, to make one test request:
   - curl -s -o /dev/null -w '%{http_code}\n' -H 'X-Api-Key: CRM-KEY' https://CRM-ADDRESS/api/v1/CMentorProfile?maxSize=1
   *You should see:* 200. A 401 means the key is wrong; a 403 means a permission was missed in step 9.11.

**Done when all of these are true:**

- The account exists.
- Its key has been recorded in the secrets store.
- A test request using that key succeeds.

**How to check:** A request using the key returns a normal answer, not a refusal.

**If it didn't work:** A refusal means a permission was missed in step 9.11. Stop and ask.

**What usually goes wrong:** A refusal here becomes an invisible feature later: the applications show nothing rather than an error.

---

## 9.18 Create the administrator account for the central support organization

**Why:** Only an administrator can create CRM accounts, and the applications use this account to create mentor logins.

**Who:** The central support organization

**Finish first:**

- step 9.9 Confirm the CRM's own screen loads

**Do this:**

1. Nothing extra to run. The script in step 9.10 created the administrator account CHAPTER-SLUG.provision and added its name and password to CHAPTER-ENV-FILE as ESPO_PROVISION_USERNAME and ESPO_PROVISION_PASSWORD.
2. Copy both values into a new item in the chapter's Operations vault named CRM provisioning administrator.
   *You should see:* The item in the Operations vault, with the user name and password.
3. Sign in at https://CRM-ADDRESS with that name and password once, then sign out.
   *You should see:* The CRM's home screen, with Administration in the menu.

**Done when:** The account exists and its password is in the secrets store, not on anyone's computer.

**How to check:** The account signs in, and the password is in the vault only.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The password ends up on a laptop. On Cleveland's production system it exists only inside the running application.

---

## 9.19 Create the configuration version record

**Why:** The applications report which version of the standard their CRM holds, and they read it from this record.

**Who:** The central support organization

**Finish first:**

- step 9.17 Create the account the applications sign in with

**Do this:**

1. In ~/Dropbox/Projects/cbm-client-intake, type the line below and press Enter. It reads the four values it needs from CHAPTER-ENV-FILE, and changes nothing. Every value must come from that file: the script fills any missing value from the repository's own .env file, which holds Cleveland's settings.
   - env $(grep -v '^#' ~/.config/cbm-CHAPTER-SLUG/CHAPTER-SLUG.env | xargs) uv run python scripts/build_networkstandard.py
   *You should see:* A plan and a line giving its fingerprint, sixteen letters and numbers. Later actions call it FINGERPRINT.
2. Type the line below and press Enter. The production option is required for any system that is not Cleveland's test system:
   - env $(grep -v '^#' ~/.config/cbm-CHAPTER-SLUG/CHAPTER-SLUG.env | xargs) uv run python scripts/build_networkstandard.py --apply --production --expect FINGERPRINT
   *You should see:* The record created and read back by the applications' key. If it says the plan moved, run the first line again and read the new plan.

**Done when:** The record that says which version of the standard this CRM holds exists and can be read by the applications' own key.

**How to check:** A request with the applications' key returns the record.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Writing a version after an incomplete run. A CRM claiming a version it does not hold is worse than one claiming nothing.

---

## 9.20 Run the checking tool until it reports no differences

**Why:** This is the proof that the chapter's CRM matches the standard, and so that the next release will work on it.

**Who:** The central support organization

**Finish first:**

- step 9.10 Create the teams
- step 9.11 Create the permission roles
- step 9.12 Attach the roles to the teams
- step 9.13 Create the email templates
- step 9.14 Apply the instance settings
- step 9.15 Apply the navigation tabs and the quick-add list
- step 9.16 Apply the standard's duplicate checking, saved views and automated rules
- step 9.17 Create the account the applications sign in with
- step 9.18 Create the administrator account for the central support organization
- step 9.19 Create the configuration version record

**Do this:**

1. In ~/Dropbox/Projects/cbm-client-intake, type the line below and press Enter. Pass both the address and the key: with either missing, the script uses Cleveland's own settings instead.
   - env $(grep -v '^#' ~/.config/cbm-CHAPTER-SLUG/CHAPTER-SLUG.env | xargs) sh -c 'uv run python scripts/preflight_crm.py --url "$ESPO_ADMIN_BASE" --key "$ESPO_API_KEY" --json' > ~/.config/cbm-CHAPTER-SLUG/preflight.json; echo exit $?
   *You should see:* exit 0 (conformant), exit 1 (something differs) or exit 3 (could not be checked, usually a key or network problem).
2. Type the line below and press Enter, to read the result as a report:
   - env $(grep -v '^#' ~/.config/cbm-CHAPTER-SLUG/CHAPTER-SLUG.env | xargs) sh -c 'uv run python scripts/preflight_crm.py --url "$ESPO_ADMIN_BASE" --key "$ESPO_API_KEY"'
   *You should see:* A last line beginning RESULT: CONFORMANT, DRIFT or UNCHECKED. Today the expected result is DRIFT, with only the five missing event email templates listed.
3. Write each difference that is allowed on purpose, with its reason, into the chapter's entry in the list of watched systems (step 12.5). Keep preflight.json in the chapter's Operations vault.

**Done when:** The tool runs using the applications' own key and reports that the CRM matches the standard. Any difference that is allowed on purpose is listed and explained in writing.

**How to check:** The tool reports nothing to fix, or only differences that are written down and explained.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Today no system can reach "nothing to fix": Cleveland's systems and the trial chapter all lack the same five event email templates (work list item 18). Until they exist, the honest result is a recorded, explained difference.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.9 | 09-23-26 13:54 | Manual DNS added (Doug, 09-23-26): CRMBuilder's wizard now asks on its first page whether the CRM's address is managed through Cloudflare or by hand at the chapter's own DNS provider. Step 9.2 chooses from the DNS provider item in the vault, fills in the CRM address box that manual DNS shows, and adds the A record by hand when the run shows it; its failure advice covers the 30-minute wait and Retry. Step 9.5 checks the record at the chapter's DNS provider. Screen labels read from CRMBuilder's code (commit 7b1a5062); the first page's DNS list was seen on screen by Doug on 09-23-26. |
| 0.8 | 09-23-26 13:51 | Step 9.2 rewritten in executive register (Doug, 09-23-26: it said "this computer" without saying which). It names the build computer, the central support organization's own computer with CRMBuilder installed, and uses that name for every command; defines an SSH key at first use; gives the change of folder its own action; and moves explanations out of the actions into what the reader should see. Step 9.8's two "this computer" now say the build computer. |
| 0.7 | 09-23-26 13:41 | Steps 9.1 and 9.3 brought in line with the ruling that a new chapter runs the current CRM release and Cleveland moves up later (Doug, 09-23-26). Step 9.1 writes down "the current release CRMBuilder installs" rather than Cleveland's version, and checks each add-on supports version 10. Step 9.3 records the exact number instead of comparing it, since CRMBuilder cannot install any other. Both finishing tests changed with the step list (version 0.18). |
| 0.6 | 09-23-26 13:39 | Step 9.2 points to step 5.8 for the chapter's engagement, which 5.8 now creates, instead of stopping to ask. |
| 0.5 | 09-23-26 13:35 | Step 9.2 rewritten click by click from CRMBuilder's deploy wizard (Doug, 09-23-26: the step was not clear). Named every screen, box and stage, and three facts the old text hid: CRMBuilder's own sign-in key never leaves its service, so the key ticked under Extra SSH keys must first be made and added to the chapter's DigitalOcean account; the wizard's Generate button can put - or _ in the password, which step 9.10 cannot take; and a Preparing server failure on a fast run is cured by Retry. Step 9.4 now names that key. |
| 0.4 | 09-23-26 00:55 | Step 9.11 now runs scripts/migrate_client_assignment_role.py. The roles captured on 31 August give the Client Assignment Role no User permission, so a client administrator on that team alone was refused on Assign (ruled 09-07-26). Its If it didn't work now tells an expected exit 4 (a field the source deleted) from a real one (an add-on missing); the old advice to install the add-ons and run again never ended. Found in the review before the first real chapter. |
| 0.3 | 09-19-26 00:50 | The script now reads the chapter's name, CRM settings and provisioning account (CHAPTER-SLUG.provision) from the chapter information form through --values; the step that edited Lakeside's name out of the script by hand is gone. |
| 0.2 | 09-19-26 00:07 | Every command-line action made exact (Doug, 09-19-26: sweep every step): the ssh, docker, find, rsync, chown and rebuild commands for copying the configuration; the trial scripts' exact options, including the name the provisioning account takes and the production option the version record needs; the test request for the applications' key; and the conformance check with its exit codes. Two traps written in: the scripts fill missing values from the repository's own settings, which are Cleveland's, and the settings file's password must be letters and numbers only. |
| 0.1 | 09-18-26 17:05 | First version as data, converted from the methods for building the CRM (3-Methods-CRM-Google-Applications.md, version 0.5) with the step list's finishing tests. Numbered actions, a reason per step, and a check an app can run were added. |
