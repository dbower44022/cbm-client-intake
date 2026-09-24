# Stage 15 — Bring in the chapter's records and create the mentor accounts

**Version:** 0.3  
**Last Updated:** 09-23-26 14:27  
**Generated from** `steps/stage-15.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

A chapter arrives with clients, companies, partners, funders and mentors it already knows about. This stage moves those records into the CRM without duplicates, then gives every mentor an account created from their mentor record. A chapter starting from nothing skips the load but still enters its mentors.

**Who:** The chapter provides and checks the records; the central support organization does the load. The chapter's mentor administrator creates the mentor accounts.  
**Time:** Not known yet. It depends on how many records the chapter has and how clean they are. No chapter's records have ever been loaded.  
**When this stage is done:** Staff can be trained (stage 16), and the final checks can run against the chapter's real records (stage 17).

**Before you start:**

- The CRM system (stage 9)
- Backups switched on and restored once (stage 12)
- The staff accounts, including the mentor administrator's (stage 14)

**Steps in this stage:**

- 15.1 Decide whether there are records to bring in
- 15.2 Export the existing records
- 15.3 Map the old fields to the CRM's fields
- 15.4 Do a trial load on a copy
- 15.5 Resolve duplicates
- 15.6 Do the real load
- 15.7 Check a sample
- 15.8 Enter every mentor the load did not bring in
- 15.9 Create the mentor accounts
- 15.10 Confirm every mentor has signed in

---

## 15.1 Decide whether there are records to bring in

**Why:** A record source nobody mentions before go-live turns up later as missing history.

**Who:** The chapter decides; the central support organization records it

**Finish first:**

- step 9.20 Run the checking tool until it reports no differences

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Ask every member of staff, not only the setup contact, where they keep records today. All of these count:
   - Spreadsheets.
   - Another CRM.
   - An email list.
   - A mentoring platform.
2. Write one line per source, giving:
   - Where it is: the system's name, or the file's location.
   - What it holds: clients, companies, mentors, partners, funders or meetings.
   - Roughly how many records.

   *You should see:* A written list of sources, or a written note that there are none.

**Done when:** Either the sources are listed, or a note records that the chapter starts with nothing. A chapter starting with nothing skips the load (steps 15.2 to 15.7) but not the mentor steps after it (steps 15.8 to 15.10).

**How to check:** A written list of sources, or a written note that there are none.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A source nobody mentions until after go-live.

---

## 15.2 Export the existing records

**Why:** The load works from files, and the row counts are how the load is later proved complete.

**Who:** The chapter

**Finish first:**

- step 15.1 Decide whether there are records to bring in

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Export each source to a spreadsheet file in CSV format, one file per kind of record, named SOURCE-KIND.csv, for example oldcrm-contacts.csv.
2. Count the data rows in each file, not counting the heading row, and write the count beside the file name.
3. Compare each count with the number the old system reports.
   *You should see:* The same numbers.
4. Keep the files in the chapter's Board vault or another place only the people doing the load can reach. They hold personal details.

**Done when:** Every source has been exported to a file, and the number of records in each file is written down.

**How to check:** One file per source per kind of record, each with its row count written down.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** An export that silently drops columns or rows.

---

## 15.3 Map the old fields to the CRM's fields

**Why:** Every old column has to land in the right CRM field, or be left out on purpose, so nothing is lost by accident.

**Who:** The central support organization with someone from the chapter who knows the old records

**Finish first:**

- step 15.2 Export the existing records

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Make one table with a line for every column of every file, and these columns:
   - File
   - Column
   - CRM record: Company, Contact, Client Profile, Engagement, Mentor Profile, Partner Profile or Sponsor Profile
   - CRM field
   - Or: not brought across, and why
2. Use data-model.md in the software's code repository for the records and their links. For the exact field names, sign in to the CRM as the administrator and open Administration, then Entity Manager, then the record, then Fields.
3. For each column feeding a choice list, list every old value and the CRM value it becomes. A company's type is one of these, exactly:
   - Client
   - Sponsor
   - Partner
   - Other
4. Funders are Sponsor, never Donor. For mentors, map their chapter email address to the CBM email field, not their personal address.
   *You should see:* No column in any file without a line in the table.

**Done when:** Every column in every export file is either mapped to a CRM field or marked as not being brought across, with a reason.

**How to check:** No column in any file is left without a line in the table.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A choice-list value mapped by guesswork. It is refused at load time, or the software drops it to save the rest of the record and stores nothing. Also, phone numbers with fewer than ten or more than fifteen digits are dropped.

---

## 15.4 Do a trial load on a copy

**Why:** A trial on a copy of the chapter's own CRM proves what the real load will do, without touching the live system.

**Who:** The central support organization

**Finish first:**

- step 15.3 Map the old fields to the CRM's fields
- step 15.5 Resolve duplicates

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Create a new server from the CRM server's latest backup, exactly as in step 12.3: `doctl compute droplet backups SERVER-ID`, then `doctl compute droplet create load-trial-SHORT-LABEL --image BACKUP-IMAGE-ID --region REGION --size SIZE --wait`. This also completes the CRM server half of the restore test.
   *You should see:* A new server, NEW-SERVER-IP, holding a copy of the chapter's CRM.
2. Load the records into the copy at https://NEW-SERVER-IP, in this order, so each record's link already exists when it is loaded:
   - Companies.
   - Contacts.
   - Client profiles.
   - Engagements.
   - Mentor profiles, each linked to its contact.
   - Partner and sponsor profiles.
3. There is no loading tool yet (work list item 12). For each kind of record, use the CRM's own import: open the record's list, then the menu, then Import, and upload the file. The exact menu label has not been checked on the chapter's version. Engagements need links the import screen may not set; if so, stop and ask the central support organization, which will write a script for this chapter.
4. In the copy, open each kind of record's list and read its total.
   *You should see:* The same counts as step 15.2, with any difference explained.
5. Open five records of each kind and compare them with the file.
6. Delete the copy the same day and write down when:
   - doctl compute droplet delete load-trial-SHORT-LABEL --force

**Done when:** The load has been run somewhere that is not the live system, and the result has been looked at.

**How to check:** The counts in the copy match the export, with any difference explained.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The trial copy holds real personal details. Never run the trial on the shared training system, which holds Cleveland's records, or on the trial chapter.

---

## 15.5 Resolve duplicates

**Why:** Two records for one person or company split their history, and a mentor assigned to the wrong duplicate cannot see their client.

**Who:** The central support organization proposes the rule; the chapter approves it

**Finish first:**

- step 15.2 Export the existing records

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Apply the rule the intake forms already use, and write it down:
   - A person is the same person when the email address matches.
   - A company is the same company when the name matches.
   - A company has at most one client profile.
2. Where two rows match, keep one. Fill its empty fields from the other row, and never overwrite a field that already holds a value.
3. Have the chapter approve the written rule.
   *You should see:* No two contacts share an email address, and no two companies share a name, unless the chapter decided they are different.

**Done when:** The rule for deciding what counts as the same person or company is written down and has been applied.

**How to check:** No two contacts share an email address and no two companies share a name, unless the chapter decided otherwise.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Two records for one mentor. An engagement assigned to the wrong one is invisible to the mentor. The CRM's own duplicate checking has never been examined (work list item 3).

---

## 15.6 Do the real load

**Why:** This puts the chapter's history into its live CRM, exactly as the trial proved it.

**Who:** The central support organization

**Finish first:**

- step 15.4 Do a trial load on a copy
- step 15.5 Resolve duplicates

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Run exactly the load that ran on the trial copy, in the same order, into the chapter's live CRM at https://CRM-ADDRESS.
2. In the CRM, open each kind of record's list and read its total.
   *You should see:* The same counts as step 15.2, with any difference explained in writing.
3. After the mentor accounts exist (step 15.9), give the mentors access to their loaded clients. Open a console on the application's web part, putting the application's ID in place of APP-ID:
   - doctl apps console APP-ID web
4. In that console, report what is missing, then repair it:
   - PYTHONPATH=/app .venv/bin/python scripts/audit_assignment_stamps.py
   - PYTHONPATH=/app .venv/bin/python scripts/audit_assignment_stamps.py --heal

   *You should see:* The second run reports the missing users merged. A third run without --heal reports nothing missing. The nightly repair check does the same work if this is skipped.

**Done when:** The records are in the live CRM and the counts match what was exported, with any difference explained.

**How to check:** The counts in the CRM match the export, with any difference explained in writing.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A list read with a page size over 200. The CRM refuses it rather than returning fewer rows, and inside a step that tolerates errors the refusal reads as "no records". A loading script must read in pages of 200 or fewer.

---

## 15.7 Check a sample

**Why:** Counts can match while details are wrong, so someone who knows the old records looks at real examples.

**Who:** The chapter — someone who knows the old records

**Finish first:**

- step 15.6 Do the real load

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Pick at least ten records of each kind, including:
   - The oldest.
   - The newest.
   - A few with unusual details.
   - The rows that caused trouble in the trial.
2. Open each in the CRM at https://CRM-ADDRESS and compare it field by field with the old record.
3. Write down, for each record checked:
   - Its name.
   - Right, or what was corrected.

   *You should see:* A written list, each record marked right or corrected.

**Done when:** Somebody who knows the old records has opened a sample in the CRM and confirmed they are right.

**How to check:** A written list of checked records, each marked right or corrected.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Checking only the records that were easy to load.

---

## 15.8 Enter every mentor the load did not bring in

**Why:** A mentor's account is created from their mentor record, so every mentor needs one before step 15.9.

**Who:** The chapter — the mentor administrator

**Finish first:**

- step 14.2 Create the staff accounts
- step 15.7 Check a sample

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Open https://APP-ADDRESS/mentoradmin/ and search by surname for each mentor before entering anyone, so no mentor the load already brought in gets a second record.
2. For a large group, send each mentor the public volunteer form at https://APP-ADDRESS/volunteer/. Each submission creates the contact and the mentor record, and records the mentor's agreement to the code of ethics.
3. For a few mentors, enter each one directly in Mentor Administration, with their chapter email address in the CBM email field.
   *You should see:* Every current mentor in the Mentor Administration list, each with a linked contact.

**Done when:** Every current mentor has a mentor record in the CRM, with a linked contact. For a chapter starting with nothing, this is every mentor.

**How to check:** The Mentor Administration list holds every current mentor, each with a linked contact.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The same mentor entered twice, once by the load and once by hand. Assignments then go to the wrong one, and the mentor sees no clients.

---

## 15.9 Create the mentor accounts

**Why:** Creating a mentor's account from their record links the two and sends the sign-in details, and an account made by hand turns into a duplicate.

**Who:** The chapter — the mentor administrator, with the central support organization present for the first few

**Finish first:**

- step 15.8 Enter every mentor the load did not bring in

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Never create a mentor's account by hand in the CRM.
2. Open https://APP-ADDRESS/mentoradmin/, open the mentor, and on the Status tab set Status to Active. Save.
   *You should see:*

   - A status window listing each step as it runs
   - The mentor's mailbox created, if Google is switched on
   - The mentor's CRM account created on the Mentor Team
   - The account linked to the mentor record
   - The mentor emailed their sign-in details

**Done when:** Every current mentor has an account, created from their mentor record in Mentor Administration, and none was created by hand.

**How to check:** Each mentor shows as complete in the Mentor Administration list.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** An account created by hand before the mentor record has its chapter email address. The software then creates a second account with a number added to the address, and sends a second welcome email.

---

## 15.10 Confirm every mentor has signed in

**Why:** An account nobody has signed in to is a mentor who has not started, or a welcome email lost in spam.

**Who:** The chapter — the mentor administrator chases; the central support organization checks

**Finish first:**

- step 15.9 Create the mentor accounts

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the CRM, open Administration, then Auth Log, as in step 14.4. The label has not been checked on the chapter's version.
2. Tick off every mentor who appears there with a successful sign-in.
   *You should see:* Every mentor ticked.
3. Chase anyone not ticked. Ask them to check their spam folder first. A mentor who lost the welcome email opens https://APP-ADDRESS/ and chooses Forgot your password?

**Done when:** Each mentor has signed in at least once and set their own password.

**How to check:** No mentor's account has a blank last sign-in date.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The welcome email lands in spam, because the chapter's sending address is new.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.3 | 09-23-26 14:27 | The placeholder CHAPTER-SLUG is now SHORT-LABEL, the form's own name for it (Doug, 09-23-26: slug is a terrible name for a user). The guide's index lists every shared placeholder. |
| 0.2 | 09-19-26 00:15 | Every action made precise (Doug, 09-19-26): exact file naming, the mapping table's columns, the load order, the restore-copy commands, the audit script run inside the application's web part, and exact addresses for Mentor Administration and the volunteer form. |
| 0.1 | 09-18-26 17:30 | First version as data, converted from the methods for loading records (10-Methods-Website-Pages-Records.md, version 0.2) and for the mentor steps (5-Methods-Form-Accounts-Checks.md, version 0.4) with the step list's finishing tests. |
