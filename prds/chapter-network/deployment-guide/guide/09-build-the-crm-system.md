# Stage 9 — Build the CRM system

**Version:** 0.1  
**Last Updated:** 09-18-26 17:05  
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
- The chapter's domain names in its Cloudflare account (step 3.7)
- The chapter's own DigitalOcean and Cloudflare tokens entered in CRMBuilder (step 5.8)
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
2. There is no published statement of the standard yet (work list item 2). Until there is, use the versions Cleveland's production system runs, and the date its configuration was last captured.

**Done when all of these are true:**

- The chapter's build has, in writing, the CRM version to install.
- The build has, in writing, the version of each of the two add-on products.
- The build has, in writing, which release of the standard configuration is being applied.
- Without these three numbers the later steps have nothing to check against.

**How to check:** The three numbers are written down.

**If it didn't work:** Do not start the build. Ask the central support organization for the three numbers.

**What usually goes wrong:** Skipping this and installing whatever version is newest. The August build did exactly that and ended up a whole major version ahead of Cleveland. It worked, but nobody planned it.

---

## 9.2 Create the server

**Why:** The CRM needs a server of its own, in the chapter's own hosting account, so the chapter owns it.

**Who:** The central support organization inside the chapter's hosting account

**Finish first:**

- step 5.4 Grant the central support organization access to the hosting account
- step 5.8 Create the two tokens CRMBuilder builds with
- step 3.7 Move the domain names' DNS to the chapter's Cloudflare account

**Do this:**

1. In CRMBuilder, open the chapter's engagement and start the deployment wizard.
2. Check the wizard names the chapter's own DigitalOcean and Cloudflare credentials, not CRMBuilder's.
   *You should see:* The chapter's hosting account and its Cloudflare zone, by name.
3. Enter the CRM's address from the chapter information form.
4. Tick the box for extra sign-in keys.
   *You should see:* The box ticked. Without it nobody can open a command line on the server.
5. Start the run, and wait for it to finish.
   *You should see:*
   - The server created
   - The CRM's address written into Cloudflare
   - The address resolving
   - The CRM installed
   - Each phase reported complete

**Done when:** A server is running in the chapter's own hosting account and the central support organization can reach it.

**How to check:** The server appears in the chapter's hosting account and answers.

**If it didn't work:** The run keeps what it built and names the phase that failed. Do not delete anything. Ask the central support organization to retry from the failed phase.

**What usually goes wrong:** Not ticking the extra keys box. The wizard then leaves nobody with a command line on the server, and steps 9.4 and 9.8 become impossible. The August build hit this and had to paste a key through the hosting provider's own console as a rescue.

---

## 9.3 Install the CRM software at the version the standard names

**Why:** Every chapter must run the same CRM version, or a release built for one may break another.

**Who:** The central support organization

**Finish first:**

- step 9.1 Obtain the current standard from the central support organization
- step 9.2 Create the server

**Do this:**

1. Sign in to the new CRM as the administrator the wizard created, and open the Administration page.
   *You should see:* The installed version number, shown on the Administration page.
2. Compare it with the CRM version from step 9.1.
   *You should see:* The same number.

**Done when:** The installed version matches the version named in the step above, not simply the newest available.

**How to check:** The version on the CRM's administration page matches step 9.1.

**If it didn't work:** Stop, and ask the central support organization. Do not carry on with a different version.

**What usually goes wrong:** The wizard installs whatever version is newest. In August the configuration captured from an older version rebuilt cleanly on a newer one, so a difference is not automatically fatal. It is simply unplanned.

---

## 9.4 Confirm command line access, and record who holds the key

**Why:** Copying the configuration files (step 9.8) needs a command line on the server, and the key must not live on one laptop.

**Who:** The central support organization

**Finish first:**

- step 9.2 Create the server

**Do this:**

1. Open a terminal and sign in to the server over a secure shell, using the key from step 9.2.
   *You should see:* The server's command prompt.
2. Put the key in the chapter's vault, in the Operations vault.
   *You should see:* The key listed in the vault, with a second named person able to open it.

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

1. Open the CRM's address in a browser.
   *You should see:* The CRM's sign-in page, with no certificate warning.
2. On the server's command line, confirm the certificate renewal is scheduled.
   *You should see:* An active renewal timer or scheduled job. The exact name depends on the installer version, so look rather than assume.

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
- They must be installed before the permission roles are created, because the roles refer to them.

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

1. On the new server, find where the installer keeps the CRM's custom files. An older installer uses a folder called custom; a newer one uses a folder called persistent, with the screen code in a second folder beside it.
   *You should see:* Two folders, one for the configuration and one for the screen code.
2. Copy both sets of files from the source onto the new server, into those two folders.
3. Make the web server user the owner of both folders.
4. Run the CRM's rebuild command inside its container.
   *You should see:* The rebuild finishing with no errors. In August it took three seconds.

**Done when all of these are true:**

- Both sets of configuration files are in place.
- Both sets are owned by the web server user.
- The rebuild command has finished without errors.
- There are two sets, not one.

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

1. Run the trial script scripts/rehearsal/apply_api_half.py with the chapter's settings file and without the apply option.
   *You should see:* A list of what it would create, and nothing written.
2. Run it again with the apply option. It does steps 9.10 to 9.14, 9.17 and 9.18 in one run, creating:
   - The teams.
   - The roles.
   - The roles' attachments to the teams.
   - The email templates.
   - Two accounts.
   - The instance settings.
   *You should see:* Every team reported applied.

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

1. Nothing extra to run. The script in step 9.10 creates the roles, checking each one against what this CRM has before writing it.
   *You should see:* Every role reported applied and read back identical, and no entries reported removed.

**Done when:** Every role the standard names exists, and reading each one back matches what was sent.

**How to check:** The script reports every role read back identical, with nothing removed.

**If it didn't work:** If the script reports entries it had to remove, the run is incomplete. Install the add-on products (step 9.7) and run it again.

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

1. Nothing extra to run. The script in step 9.10 does three things:
   - Creates the account.
   - Attaches its role.
   - Writes its key to the settings file.
2. Move the key into the chapter's vault, and delete it from the settings file.
   *You should see:* The key in the Operations vault.
3. Make one test request to the CRM with the key.
   *You should see:* A normal answer. An empty list is fine.

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

1. Nothing extra to run. The script in step 9.10 creates it and writes its password to the settings file.
2. Move the password into the chapter's vault, and delete it from the settings file.
   *You should see:* The name and password in the Operations vault.

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

1. Run scripts/build_networkstandard.py without the apply option.
   *You should see:* A plan and a fingerprint.
2. Run it again with the apply option and the fingerprint from the dry run.
   *You should see:* The record created. The script refuses if anything moved in between.

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

1. Run scripts/preflight_crm.py with the applications' key and the machine-readable output option. Keep the output file.
   *You should see:* A result code and a list of differences.
2. Read the result code. Nothing to fix, something differs, and could not be checked are three different answers. The third usually means a key or network problem, not a CRM problem.

**Done when:** The tool runs using the applications' own key and reports that the CRM matches the standard. Any difference that is allowed on purpose is listed and explained in writing.

**How to check:** The tool reports nothing to fix, or only differences that are written down and explained.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Today no system can reach "nothing to fix": Cleveland's systems and the trial chapter all lack the same five event email templates (work list item 18). Until they exist, the honest result is a recorded, explained difference.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:05 | First version as data, converted from the methods for building the CRM (3-Methods-CRM-Google-Applications.md, version 0.5) with the step list's finishing tests. Numbered actions, a reason per step, and a check an app can run were added. |
