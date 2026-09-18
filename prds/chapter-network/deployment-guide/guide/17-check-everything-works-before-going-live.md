# Stage 17 — Check everything works before going live

**Version:** 0.1  
**Last Updated:** 09-18-26 17:20  
**Generated from** `steps/stage-17.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

This stage proves the chapter's system works end to end before any real client uses it: each team reaches its own pages and nobody else's, and a public application travels from the website through assignment to a mentor. Every check is done as an ordinary user. An administrator skips every permission check, so a check done as an administrator proves nothing, and several of Cleveland's permission faults stayed hidden for weeks for exactly that reason.

**Who:** The central support organization, signed in as test users; the chapter for the website check.  
**Time:** About two hours. Most of the checks can be run by a script.  
**Before you start:** The staff accounts exist (stage 14); The mentor accounts exist (steps 15.8 to 15.10); The chapter's pages are on its website (stage 13)  
**When this stage is done:** The handover to normal support (stage 18). The chapter can take real clients.

**Steps in this stage:** 17.1 Create one ordinary test user per team, 17.2 Confirm each test user sees only what their team allows, 17.3 Submit the public application form, 17.4 Assign the submission, 17.5 Confirm the mentor sees it, 17.6 Confirm the submission closes, 17.7 Confirm the CRM's own screen works for an ordinary user, 17.8 Confirm the website pages work for a member of the public, 17.9 Remove the test records

---

## 17.1 Create one ordinary test user per team

**Why:** Each team's permissions can only be proven by someone who holds that team and nothing else.

**Who:** The central support organization  
**Finish first:** step 14.2, step 15.9

**Do this:**

1. Create seven ordinary accounts, one per team that opens a page, each with exactly one team. scripts/rehearsal/stage4_users.py did this for the trial chapter; change the chapter name in it, or create the accounts by hand.
2. For the Mentor Team test user, create a mentor record in Mentor Administration and set it to Active, so the account is linked to it (step 15.9).
3. Put the test users' passwords in the chapter's vault.

**Done when:** There is one non-administrator test account for each team.

**How to check:** Each test user signs in, and the sign-in reports exactly one team.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Giving test users a second team "to make testing easier". The check then proves nothing about the single-team case real staff are in.

---

## 17.2 Confirm each test user sees only what their team allows

**Why:** A permission gap either locks staff out of their work or shows them records they must not see, and only a per-team test finds it.

**Who:** The central support organization  
**Finish first:** step 17.1

**Do this:**

1. Sign in as each test user and try every restricted page in the applications.
   *You should see:* Each user opens their own team's pages and is refused on the rest. The Mentor Team user also opens the directory and My Email; partner and funder managers also open My Email.
2. Compare the results with the trial chapter's table, prds/chapter-network/rehearsal-2026-08-31/nonadmin-gate-matrix.json.
   *You should see:* The same pattern of allowed and refused.
3. Check the settings page separately. When it is switched on, an ordinary user should be refused with a message saying it is for administrators.

**Done when:** Every test user can open their own team's pages and is refused on every other team's pages. Administrator accounts skip all permission checks, so this must be done as ordinary users.

**How to check:** The new table matches the trial chapter's table.

**If it didn't work:** A "not found" answer is not a refusal. Find out why the page answered that way before calling it a pass.

**What usually goes wrong:** Reading "not found" as "refused". In August the settings page answered "not found" to every test user, and the record cannot say why.

---

## 17.3 Submit the public application form

**Why:** The public form is how clients arrive, so it is tested from the chapter's own website the way a client would use it.

**Who:** The chapter and the central support organization — the central support organization, or anyone at the chapter  
**Finish first:** step 17.2, step 13.2

**Do this:**

1. Open the chapter's website in a private browser window and follow its link to the client application form.
2. Open all four policy links on the consent box.
   *You should see:* Each of the chapter's own policy documents.
3. Submit the form with a made-up business and a test email address the chapter controls. Write down the made-up names; step 17.9 removes them.
   *You should see:* A thank-you message with a reference number.

**Done when:** A submission made from the public website arrives in the system.

**How to check:** The submission appears in Submission Admin.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A broken policy link on the consent box.

---

## 17.4 Assign the submission

**Why:** Assigning a new client to a mentor is the client administrator's main task, and it depends on several permissions at once.

**Who:** The central support organization signed in as the Client Administration Team test user  
**Finish first:** step 17.3

**Do this:**

1. Open Client Administration and find the new engagement.
2. Assign it to the Mentor Team test user's mentor record.
   *You should see:* The engagement shows the mentor and the status "Pending Acceptance", and the email to the mentor opens ready to send.

**Done when:** A client administrator test user assigns it to a mentor.

**How to check:** The engagement shows the mentor and the status "Pending Acceptance".

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Two known failures. An empty mentor list: a mentor appears only when Active, accepting new clients and linked to an account. And a refusal about users: the client administration role needs permission to read users; Cleveland's role lacked it, and production still needs the fix.

---

## 17.5 Confirm the mentor sees it

**Why:** The assignment only matters if the mentor can find the client and work with them.

**Who:** The central support organization signed in as the Mentor Team test user  
**Finish first:** step 17.4

**Do this:**

1. Open Client Management and find the engagement.
   *You should see:* The engagement listed, and it opens.
2. Open My Mentor Profile.
   *You should see:* The mentor's own details.

**Done when:** The mentor test user finds the assignment and can open their own profile.

**How to check:** The engagement opens, and the profile page shows the mentor's own details.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Client Management is empty. Nearly always the mentor record is not linked to the account, or the engagement was assigned to a duplicate mentor record with the same name. Check the link first.

---

## 17.6 Confirm the submission closes

**Why:** A submission that never reaches Completed means the background worker is not delivering to the CRM.

**Who:** The central support organization signed in as the Marketing Admin Team test user  
**Finish first:** step 17.3

**Do this:**

1. Open Submission Admin and find the submission.
   *You should see:* Intake status Completed, closed, with the reason "Process completed".

**Done when:** The submission shows as completed and closed to the user who handles submissions.

**How to check:** The submission reads Completed and closed.

**If it didn't work:** A submission stuck at Received means the background worker is not running or cannot reach the CRM. Read the application's health page, which reports whether the worker is alive.

---

## 17.7 Confirm the CRM's own screen works for an ordinary user

**Why:** Staff also use the CRM directly, and a missing screen file shows an ordinary user a blank page.

**Who:** The central support organization  
**Finish first:** step 17.1

**Do this:**

1. Sign in to the CRM's own address as any test user.
   *You should see:* The CRM's home screen and navigation bar.

**Done when:** A non-administrator signs in to the CRM itself and sees a working screen.

**How to check:** The home screen and menu appear.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A blank page. The CRM's screen code folder was not copied (step 9.8). The trial chapter hit exactly this.

---

## 17.8 Confirm the website pages work for a member of the public

**Why:** The public pages are what clients and volunteers see first, on computers and on phones.

**Who:** The chapter  
**Finish first:** step 13.2

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Open the chapter's website in a private browser window on a computer.
2. Open the mentor directory, one mentor, the events programme and one event.
   *You should see:* Each page with the chapter's own content and name.
3. Do the same on a phone.
   *You should see:* One column, no sideways scrolling, no text cut off.

**Done when:** Someone not signed in to anything opens the mentor directory and events pages on the chapter's website and they work.

**How to check:** Each page shows the chapter's own content and name, on a computer and a phone.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A page with no styling at all, when the page and its stylesheet disagree. Cleveland shipped exactly this for an hour. Also, the public mentor directory page is not built yet (step 13.1).

---

## 17.9 Remove the test records

**Why:** Test records left behind turn up in the chapter's reports and lists.

**Who:** The central support organization  
**Finish first:** step 17.2, step 17.3, step 17.4, step 17.5, step 17.6, step 17.7, step 17.8

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the CRM, delete the made-up company, its contact, its client profile and its engagement.
2. Leave the submission in Submission Admin, closed. It is the record that the path worked.
3. Set the seven test users to inactive, so the check can be repeated after a later release.
4. Write down what was removed in the chapter's handover notes.

**Done when:** The test submissions, test assignments and test users created for this stage are gone or disabled, and it is written down what was removed.

**How to check:** No record with the made-up names remains, and the seven test users cannot sign in.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A test record left behind turns up in the chapter's reports. The analytics pages count every engagement.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for checking everything works before going live (5-Methods-Form-Accounts-Checks.md, version 0.4) with the step list's finishing tests. |
