# Stage 8 — Fill in the chapter information form

**Version:** 0.3  
**Last Updated:** 09-19-26 14:45  
**Generated from** `steps/stage-08.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The chapter information form holds the roughly thirty-five values that differ from one chapter to the next: its name, its addresses, its Google details, its feature switches and the names of its secrets. Everything after this stage is built from the form, so a wrong or missing value here becomes a fault in every later stage. In the onboarding app, this stage is the interview.

**Who:** The chapter's setup contact and someone from the central support organization, together. The form uses the names the software uses, so a chapter cannot fill in most of it alone.  
**Time:** One to two hours, once the website, the policy documents and Google Workspace exist.  
**When this stage is done:** Building the CRM (stage 9). Nothing after this stage can start until the form is complete, and everything after it becomes routine once it is.

**Before you start:**

- The agreement is signed (step 2.6)
- The chapter's vault exists (step 2.7)
- Google Workspace is set up (stage 4)
- The website is published and the four policy documents have their addresses (stages 6 and 7)

**Steps in this stage:**

- 8.1 Obtain the blank form
- 8.2 Fill in the chapter's name and identity
- 8.3 Fill in the web addresses
- 8.4 Fill in the Google details
- 8.5 Fill in the CRM details
- 8.6 Decide every feature switch
- 8.7 List the secrets by name
- 8.8 Put the chapter's secrets into the store
- 8.9 Review the completed form
- 8.10 Store the form where the central support organization can reach it

---

## 8.1 Obtain the blank form

**Why:** Everyone has to work from the same current form, and each part needs a named person to fill it in.

**Who:** The chapter and the central support organization — the central support organization supplies the form; the chapter names the people

**Finish first:**

- step 2.6 Sign the agreement

**Do this:**

1. Copy the block of text under "The blank form" at the end of prds/chapter-network/chapter-values.md into a new file named CHAPTER-SLUG-values.yaml, for example akron-values.yaml.
   *You should see:*
   - A chapter section
   - A web section
   - A google section
   - A zoom section
   - A crm section
   - A secrets section
   - A flags section
2. Send the trial chapter's filled-in form, prds/chapter-network/rehearsal-2026-08-31/lakeside-values.yaml, alongside it as a worked example.
3. Add a comment line at the top of each section naming who fills it in:
   - chapter and web: the chapter's setup contact
   - google and zoom: the chapter's setup contact, checked by the central support organization
   - crm, secrets and flags: the central support organization
   *You should see:* Every section with a name at its top.

**Done when:** The chapter has the current blank form and knows who fills in each part.

**How to check:** Every section of the form has a name beside it.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The blank form falls behind the software. A new setting that differs by chapter gets added to the software but not to the form. Run the information check in the plan again whenever the software gains a per-chapter setting.

---

## 8.2 Fill in the chapter's name and identity

**Why:** The chapter's name appears on every page the software shows, and the short label names its servers and secrets.

**Who:** The chapter

**Finish first:**

- step 1.1 Choose the chapter's name
- step 8.1 Obtain the blank form

**Do this:**

1. Fill in the chapter section, key by key:
   - name: the chapter's name exactly as it should appear on every page, capital letters included. Example: Lakeside Business Mentors. It becomes the setting ORGANIZATION_NAME.
   - slug: one lower-case word with no spaces, used to name the chapter's servers and secrets. Example: lakeside.
   - timezone: the time zone's standard name. Examples: America/New_York, America/Chicago, America/Denver, America/Phoenix.
   - currency: USD
   - locale: en_US
2. If the time zone is not America/New_York, add the comment "not supported yet" beside it. The software has Eastern time written into its code (work list item 17).

**Done when all of these are true:**

- The chapter name is filled in.
- The short label is filled in.
- The time zone is filled in.
- The currency is filled in.
- The language is filled in.

**How to check:** The name matches the legal name, or the trading name the board chose, letter for letter.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The time zone. A chapter outside the Eastern United States gets wrong dates on birthday greetings, assignment dates and the public events page, and nothing reports an error.

---

## 8.3 Fill in the web addresses

**Why:** The software links to the website, the events page, the help documentation and the four policy documents, and a broken link on the consent box is a legal problem.

**Who:** The chapter checked by the central support organization

**Finish first:**

- step 6.2 Publish the website
- step 6.7 Decide where the chapter's help documentation lives
- step 7.6 Record the four web addresses
- step 8.1 Obtain the blank form

**Do this:**

1. Fill in the web section, key by key, copying every address from a browser's address bar:
   - app_base_url: https://apps.CHAPTER-DOMAIN/ — the address the applications will have. It does not answer until step 11.10.
   - website_base_url: the website's home address from step 6.2. Example: https://lakesidebusinessmentors.org
   - events_public_base_url: leave empty. Empty means the applications' own events page, APP-ADDRESS/webinars/, which is what every chapter now uses.
   - docs_site_url: the answer from step 6.7.
   - policy_client_conduct_url, policy_mentor_ethics_url, policy_terms_url and policy_privacy_url: the four addresses from stage 7, one per key.
   - chapter_tokens_url: the colour file's address from step 6.5.
2. In a terminal, run this once for each address except app_base_url, putting the address in place of ADDRESS:
   - curl -sI ADDRESS
   *You should see:* A first line of HTTP/2 200 for every one.

**Done when all of these are true:**

- The application address is filled in.
- The website address is filled in.
- The events page address is left empty, so the software uses its own events page.
- The documentation address is filled in.
- The colour file address is filled in.
- The four policy addresses are filled in.

**How to check:** Every address, opened in a private browser window, shows the right page.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A policy address that does not load. The public application form links to all four policies from its consent box.

---

## 8.4 Fill in the Google details

**Why:** Mail, calendars, documents and mentor mailboxes all run through the chapter's Google Workspace, and each needs an exact address.

**Who:** The chapter checked by the central support organization

**Finish first:**

- step 4.1 Confirm the chapter will hold its own Google Workspace
- step 4.7 Create the shared operations mailbox
- step 4.8 Create the alert sending mailbox
- step 4.9 Decide who receives the system's warning messages
- step 4.10 Create the members group
- step 8.1 Obtain the blank form

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Fill in the google section, key by key, copying each address from the Google Workspace admin console:
   - primary_domain: the chapter's email domain. Example: cbmentors.org is Cleveland's.
   - ops_mailbox: the shared operations mailbox from step 4.7. Example: info@CHAPTER-DOMAIN
   - alert_email_from: the alert sending mailbox from step 4.8. It must be a mailbox with a licence, never a group.
   - alert_email_to: the address that receives warnings, from step 4.9. It may be a group.
   - members_group: the members group from step 4.10. Example: members@CHAPTER-DOMAIN
   - mentor_email_domain: the domain mentors' mailboxes are made on. Usually the same as primary_domain. It becomes the setting MENTOR_EMAIL_DOMAIN.
   - shared_drive_id: leave empty for now. The shared drive is created in step 10.5, which writes its identifier here: the part of the drive's web address after /drive/folders/.
   - zoom_host_email: the Zoom host address from step 5.5, or leave empty for a chapter with no webinars. The default is Cleveland's host, so a webinar chapter must set it.
2. Fill in the zoom section from step 5.5, or leave both empty for a chapter with no webinars:
   - account_id: the Zoom app's account identifier.
   - client_id: the Zoom app's client identifier.
3. In the Google Workspace admin console, open Users and find ops_mailbox and alert_email_from.
   *You should see:* Both listed as users with a licence. Neither is a group.

**Done when all of these are true:**

- The main domain is filled in.
- The shared operations mailbox is filled in.
- The alert sending address is filled in.
- The alert receiving address is filled in.
- The members group is filled in.
- The mentor email domain is filled in.

**How to check:** Each mailbox named on the form is listed as a mailbox, with a licence, in the Google Workspace admin console.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Writing a group where a mailbox is needed. The alert sending address and the shared operations mailbox must both be real licensed mailboxes. A group fails later, with an error that does not name the cause.

---

## 8.5 Fill in the CRM details

**Why:** The CRM has its own name, sending name, sending address and logo, and anything it sends directly carries them.

**Who:** The central support organization

**Finish first:**

- step 6.6 Produce the chapter's logo image
- step 8.1 Obtain the blank form

**Do this:**

1. Fill in the crm section, key by key:
   - base_url: the CRM's address, published in step 9.6. Example: https://crm.CHAPTER-DOMAIN — Cleveland's is https://crm.clevelandbusinessmentors.org
   - application_name: the name shown inside the CRM. Usually the chapter's name.
   - outbound_from_name: the name on mail the CRM sends. Usually the chapter's name.
   - outbound_from_address: a mailbox from stage 4 that the CRM sends from. Example: info@CHAPTER-DOMAIN
   - logo_file: the logo's file name from step 6.6. Example: lakeside-logo.png

**Done when all of these are true:**

- The CRM address is filled in.
- The name shown inside the CRM is filled in.
- The sending name is filled in.
- The sending address is filled in.
- The logo file is filled in.

**How to check:** The section is complete, and the sending address is a real mailbox.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 8.6 Decide every feature switch

**Why:** Each switch turns a part of the software on or off, and a switch left blank gives a chapter behaviour nobody chose.

**Who:** The chapter and the central support organization — the central support organization proposes; the chapter agrees

**Finish first:**

- step 8.2 Fill in the chapter's name and identity
- step 8.3 Fill in the web addresses
- step 8.4 Fill in the Google details
- step 8.5 Fill in the CRM details

**Do this:**

1. Fill in the flags section. Write true or false for each switch; never leave one blank. These are the starting values for a new chapter, which the central support organization proposes and the chapter agrees:
   - analytics_enabled: true
   - events_enabled: true
   - events_public_api: true once the chapter runs public events, otherwise false
   - gmail_sync: false until step 11.14 passes
   - gcal_events: false until step 11.16 passes
   - gdrive_docs: false until step 11.17 passes
   - mentor_provision_users: true
   - google_directory_check: false until step 11.18 passes
   - google_create_mailbox: false until step 11.18 passes
   - gdrive_identity: service (this one is a word, not true or false)
   - zoom_events: false until the chapter's Zoom app is working
   - record_quick_add: true
   - setup_enabled: true
   - async_delivery: true
   - espo_dry_run: false
   - deploy_on_push: false
   *You should see:* Sixteen switches, none blank.
2. Add the comment "follows the release branch" beside deploy_on_push. The application follows the release branch, never the development branch (step 11.9).

**Done when:** Each switch has been deliberately set to on or off, and the branch the application follows is recorded as the release branch rather than the development branch.

**How to check:** No switch on the form is blank.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A switch in the software that the form does not list. Until 09-18-26 the blank form was missing five switches the trial chapter needed, and it can fall behind again whenever the software gains one.

---

## 8.7 List the secrets by name

**Why:** Each secret needs a named holder before it exists, so that none is ever held by one person alone.

**Who:** The central support organization

**Finish first:**

- step 8.6 Decide every feature switch

**Do this:**

1. Fill in the secrets section with these names, exactly as written, and nothing else:
   - ESPO_API_KEY — the CRM key the applications use. Created in step 9.17.
   - ESPO_PROVISION_USERNAME — the name of the administrator account that creates logins. Created in step 9.18.
   - ESPO_PROVISION_PASSWORD — that account's password. Created in step 9.18.
   - DATABASE_URL — the database address. Held by the hosting platform, which supplies it to the application (step 11.4). No person holds it, and it never goes in the vault.
   - SESSION_SECRET — created in step 11.1.
   - APP_ENCRYPTION_KEY — the encryption key for stored data. Created in step 11.2, and never changed afterwards.
   - GOOGLE_SERVICE_ACCOUNT_JSON — the Google key. Created in step 10.2.
2. For a chapter that runs public webinars, add ZOOM_CLIENT_SECRET, the Zoom app's secret from step 5.5, as an eighth.
3. Add a comment beside each name with its holder. Write no secret value anywhere on the form.
   *You should see:* Seven or eight names, each with a holder, and no values.

**Done when all of these are true:**

- All seven are listed by name with the holder named beside each.
- The video meeting app's secret is listed too, for a chapter that runs webinars.
- No secret value is written on the form.

**Note:** Seven, not six: besides the six the planning documents name, the applications use an encryption key for stored data that the settings generator creates quietly on first run. Changing it later destroys the data it protects, so it is permanent from the moment it exists.

**How to check:** Seven names, or eight for a webinar chapter, each with a holder, and no values.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Listing six and missing the encryption key. Changing that key later makes every stored secret permanently unreadable.

---

## 8.8 Put the chapter's secrets into the store

**Why:** A secret that exists only in a file on one computer is lost when that person or that computer is.

**Who:** The central support organization

**Finish first:**

- step 8.7 List the secrets by name
- step 2.7 Set up the chapter's password vault

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Open the chapter's Operations vault in Proton Pass.
2. For each name on the list from step 8.7 whose step has already happened, check there is an entry titled with exactly that name, for example ESPO_API_KEY. The machine secrets are created later, in stages 9 to 11, and go straight into the vault under the same titles as each is made.
   *You should see:* An entry for every secret that exists so far, titled with its name from the list.
3. Ask a second named person to open each entry in their own Proton Pass.
   *You should see:* The second person can open every entry.

**Done when all of these are true:**

- Every secret a person holds is in the chapter's Proton Pass Operations vault (step 2.7). That is all seven except the database connection, which the hosting platform holds (step 11.4).
- At least two named people can reach each one.
- None of them exists only in a file on one person's computer.

**How to check:** A second named person opens each secret without help.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Treating a file on one laptop as good enough. Regenerating the deployment settings from the hosting provider scrambles the passwords inside them. Cleveland has lost working passwords that way.

---

## 8.9 Review the completed form

**Why:** A wrong value becomes a fault in every later stage, and a second reader catches what the first misses.

**Who:** The chapter and the central support organization — the chapter's setup contact and someone from the central support organization

**Finish first:**

- step 8.2 Fill in the chapter's name and identity
- step 8.3 Fill in the web addresses
- step 8.4 Fill in the Google details
- step 8.5 Fill in the CRM details
- step 8.6 Decide every feature switch
- step 8.7 List the secrets by name

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Sit down together, the chapter's setup contact and someone from the central support organization, with the form open.
2. Read every key and its value aloud, section by section.
3. Run the curl check from step 8.3 on every address again:
   - curl -sI ADDRESS
   *You should see:* A first line of HTTP/2 200 for every address except app_base_url.
4. Read every switch aloud with its value.
5. Add two comment lines at the top of the form:
   - # reviewed by: NAME-ONE and NAME-TWO
   - # reviewed on: MM-DD-YY

**Done when:** Two people have read the whole form together in one sitting and both have signed it off.

**How to check:** Both names and the date are at the top of the form.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 8.10 Store the form where the central support organization can reach it

**Why:** Stages 9 to 12 are built from the form, so the people building them have to be able to open it.

**Who:** The central support organization

**Finish first:**

- step 8.9 Review the completed form

**Do this:**

1. Check the form holds no secret value. Every line under secrets must be a name only.
2. Save the form in the software's code repository at exactly this path, beside the trial chapter's form's folder: prds/chapter-network/chapters/CHAPTER-SLUG-values.yaml
3. Commit it with the message "docs(chapter-network): CHAPTER-SLUG chapter information form", and push it.
4. Ask a second person at the central support organization to open the file from the remote repository.
   *You should see:* The file opens, with both reviewers' names at the top.

**Done when:** The form is in the agreed place and the central support organization has confirmed it can open it.

**How to check:** A second person at the central support organization opens it.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A secret pasted into the form by mistake. The code repository is not a secrets store.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.3 | 09-19-26 14:45 | Steps 8.7 and 8.8: the database connection is held by the hosting platform and never goes in the vault, matching step 11.3 (Doug, 09-19-26). |
| 0.2 | 09-19-26 00:05 | Every action made precise (Doug, 09-19-26): each section of the form filled key by key with what goes in it and an example, the sixteen switches with their starting values, the secret names with the step that creates each, vault entry titles, curl checks for every address, and the exact file path the finished form is saved at. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for filling in the chapter information form (5-Methods-Form-Accounts-Checks.md, version 0.4) with the step list's finishing tests. Each form field is now produced by a named step. |
