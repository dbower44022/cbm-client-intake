# Stage 8 — Fill in the chapter information form

**Version:** 0.1  
**Last Updated:** 09-18-26 17:20  
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

1. Copy the blank form from the last section of prds/chapter-network/chapter-values.md.
   *You should see:*
   - A section for the chapter
   - A section for web addresses
   - A section for Google
   - A section for Zoom
   - A section for the CRM
   - A section for secrets
   - A section for feature switches
2. Send the trial chapter's filled-in form, prds/chapter-network/rehearsal-2026-08-31/lakeside-values.yaml, alongside it as a worked example.
3. Write a name beside each section. The chapter's setup contact fills in the name, the web addresses and the policy addresses. The central support organization fills in the CRM details, the feature switches and the list of secrets.
   *You should see:* Every section with a name beside it.

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

1. Write the chapter's name exactly as it should appear on every page, capital letters included. For example, Akron Business Mentors.
2. Write the short label, one lower-case word, for example akron. It names the chapter's servers and secrets.
3. Write the chapter's time zone.
   *You should see:* A time zone name such as America/Denver.
4. If the time zone is not Eastern, write "not supported yet" beside it. The software has Eastern time written into its code (work list item 17).
5. Write the currency and language. They are almost always US dollars and US English.

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

1. Leave the application address empty. It does not exist until the applications are deployed, and step 11.10 fills it in.
2. Open the chapter's website in a browser, and copy its address into the form.
3. Copy in the events page address, the help documentation address and the colour file address.
4. Open each of the four policy documents in a private browser window, and copy each address into the form.
   *You should see:* Each policy document's page, with the chapter's own name on it.

**Done when all of these are true:**

- The application address is filled in.
- The website address is filled in.
- The events page address is filled in.
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

- step 4.1 Choose the Google Workspace branch
- step 4.7 Create the shared operations mailbox
- step 4.8 Create the alert sending mailbox
- step 4.9 Decide who receives the system's warning messages
- step 4.10 Create the members group
- step 8.1 Obtain the blank form

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Write the Google Workspace branch the chapter chose in step 4.1.
2. Copy these from the Google Workspace admin console:
   - The main domain.
   - The shared operations mailbox.
   - The alert sending address.
   - The alert receiving address.
   - The members group.
3. Copy the shared drive's identifier, the string of letters at the end of its web address.
4. Write the mentor email domain, the domain mentors' addresses are created on.
5. For a chapter that runs public webinars, copy the Zoom host address and the Zoom app's account and client identifiers from step 5.5. Otherwise write "no webinars".

**Done when all of these are true:**

- The branch chosen is filled in.
- The main domain is filled in.
- The shared operations mailbox is filled in.
- The alert sending address is filled in.
- The alert receiving address is filled in.
- The members group is filled in.
- The shared drive is filled in.
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

1. Write the CRM's address, the address it will be published at in step 9.6.
2. Write the name shown inside the CRM and the sending name. Both are usually the chapter's name.
3. Write the sending address, a mailbox from stage 4.
4. Attach the logo image from step 6.6.

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

1. Go down the switch list on the form and write on or off for each one. Never leave one blank.
   *You should see:* Thirteen switches, each with on or off.
2. Set every switch that uses Google to off for now. They are switched on only after the Google checks in steps 11.14 to 11.18 pass.
3. Record that the application follows the release branch, not the development branch.

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

1. List the seven secrets by name:
   - The CRM key the applications use.
   - The name of the administrator account that creates logins.
   - The password of that administrator account.
   - The database address.
   - The session secret.
   - The encryption key for stored data.
   - The Google key.
2. For a chapter that runs public webinars, add the Zoom app's secret as an eighth.
3. Write the holder beside each one. Write no secret value on the form.
   *You should see:* Seven or eight names, each with a holder, and no values.

**Done when all of these are true:**

- All seven are listed by name with the holder named beside each.
- The video meeting app's secret is listed too, for a chapter that runs webinars.
- No secret value is written on the form.
- Seven, not six: besides the six the planning documents name, the applications use an encryption key for stored data that the settings generator creates quietly on first run. Changing it later destroys the data it protects, so it is permanent from the moment it exists.

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
2. For each secret on the list from step 8.7, check it has an entry. Most arrive as accounts are created; the machine secrets arrive in stages 9 to 11 and go straight into the vault as each is made.
   *You should see:* An entry for every secret that exists so far.
3. Ask a second named person to open each entry.

**Done when all of these are true:**

- All seven of the chapter's secrets are held in the chapter's Proton Pass Operations vault (step 2.7).
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

1. Sit down together and go through the form line by line.
2. Open every address.
3. Read every switch aloud with its setting.
4. Write both names and the date at the top of the form.

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

1. Add the form to the chapter-network folder in the software's code repository, as the trial chapter's form was.
2. Check the form holds no secret value.
3. Ask a second person at the central support organization to open it.

**Done when:** The form is in the agreed place and the central support organization has confirmed it can open it.

**How to check:** A second person at the central support organization opens it.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A secret pasted into the form by mistake. The code repository is not a secrets store.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for filling in the chapter information form (5-Methods-Form-Accounts-Checks.md, version 0.4) with the step list's finishing tests. Each form field is now produced by a named step. |
