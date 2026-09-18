# Stage 15 — Bring in the chapter's records and create the mentor accounts

**Version:** 0.1  
**Last Updated:** 09-18-26 17:30  
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

1. Ask every member of staff where they keep records today, not only the setup contact. All of these count:
   - Spreadsheets.
   - Another CRM.
   - An email list.
   - A mentoring platform.
2. For each source, write down:
   - Where it is.
   - What kind of records it holds.
   - Roughly how many.
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

1. Export each source to a spreadsheet file, one file per kind of record.
2. Count the rows in each file and write the count beside the file name.
3. Compare each count with what the old system says it holds.
   *You should see:* The same numbers.
4. Keep the files where only the people doing the load can reach them. They hold personal details.

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

1. List every column of every file in one table.
2. Beside each column, write the CRM record and field it goes to, or "not brought across" and why. The data model (data-model.md) names the records and their links.
3. For each column feeding a choice list, list the old values and the CRM value each becomes. Funders are "Sponsor", never "Donor". A company's type is one of:
   - Client
   - Sponsor
   - Partner
   - Other
4. For mentors, map their chapter email address, not their personal one. Their account is built on it in step 15.9.
   *You should see:* No column without a line in the table.

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

1. Create a new server from the CRM server's latest backup, as in the restore test (step 12.3). This also completes the CRM server half of that test.
2. Load the records into the new server, in link order. A company first, then its contacts, then its client profile, then its engagements. A mentor is a contact plus a mentor profile.
3. There is no loading tool yet (work list item 12). Use the CRM's own import screen one kind of record at a time, or a script written for this chapter that uses the intake forms' find-or-create rules. The script is better when there are engagements to load.
4. Compare the counts in the copy with the counts from step 15.2, and open a handful of records.
   *You should see:* The same counts, with any difference explained, and records that look right.
5. Delete the new server the same day, and write down when.

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

1. Use the rule the intake forms already use. A person is the same person when the email address matches. A company is the same company when the name matches. A company has at most one client profile.
2. Where two rows match, keep one record. Fill its empty fields from the other row, and never overwrite a field that already holds a value.
3. Write the rule down and have the chapter approve it.
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

1. Run exactly the load that ran on the trial copy, into the chapter's live CRM.
2. Compare the counts with the export.
   *You should see:* The same counts, with any difference explained in writing.
3. After the mentor accounts exist (step 15.9), run scripts/audit_assignment_stamps.py with its repair option, so mentors can see their loaded clients. The nightly repair check also does this.

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
2. Open each in the CRM and compare it with the old record.
3. Write down which records were checked, and anything wrong.
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

1. Search Mentor Administration by surname before entering anyone, to avoid a second record for a mentor the load already brought in.
2. For a large group, have each mentor fill in the public volunteer form, which creates both the contact and the mentor record and records their agreement to the code of ethics.
3. For a few, enter each one in Mentor Administration.
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

1. Never create a mentor's account by hand.
2. Open the mentor in Mentor Administration and set their status to Active.
   *You should see:*
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

1. On the CRM's user administration screen, read the last sign-in date for each mentor's account.
   *You should see:* A date for every mentor.
2. Chase anyone with a blank date. Ask them to check their spam folder first.

**Done when:** Each mentor has signed in at least once and set their own password.

**How to check:** No mentor's account has a blank last sign-in date.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The welcome email lands in spam, because the chapter's sending address is new.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:30 | First version as data, converted from the methods for loading records (10-Methods-Website-Pages-Records.md, version 0.2) and for the mentor steps (5-Methods-Form-Accounts-Checks.md, version 0.4) with the step list's finishing tests. |
