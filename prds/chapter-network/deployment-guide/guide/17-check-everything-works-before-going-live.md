# Stage 17 — Check everything works before going live

**Version:** 0.3  
**Last Updated:** 09-23-26 00:55  
**Generated from** `steps/stage-17.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

This stage proves the chapter's system works end to end before any real client uses it: each team reaches its own pages and nobody else's, and a public application travels from the website through assignment to a mentor. Every check is done as an ordinary user. An administrator skips every permission check, so a check done as an administrator proves nothing, and several of Cleveland's permission faults stayed hidden for weeks for exactly that reason.

**Who:** The central support organization, signed in as test users; the chapter for the website check.  
**Time:** About two hours. Most of the checks can be run by a script.  
**When this stage is done:** The handover to normal support (stage 18). The chapter can take real clients.

**Before you start:**

- The staff accounts exist (stage 14)
- The mentor accounts exist (steps 15.8 to 15.10)
- The chapter's pages are on its website (stage 13). Only step 17.8 and the website half of step 17.3 need it; everything else can run without it

**Steps in this stage:**

- 17.1 Create one ordinary test user per team
- 17.2 Confirm each test user sees only what their team allows
- 17.3 Submit the public application form
- 17.4 Assign the submission
- 17.5 Confirm the mentor sees it
- 17.6 Confirm the submission closes
- 17.7 Confirm the CRM's own screen works for an ordinary user
- 17.8 Confirm the website pages work for a member of the public
- 17.9 Remove the test records

---

## 17.1 Create one ordinary test user per team

**Why:** Each team's permissions can only be proven by someone who holds that team and nothing else.

**Who:** The central support organization

**Finish first:**

- step 14.2 Create the staff accounts
- step 15.9 Create the mentor accounts

**Do this:**

1. In these steps, CRM-ADDRESS is the chapter's CRM address, APP-ADDRESS is the chapter's application address, and SLUG is the chapter's short label, all from the chapter information form.
2. Sign in to CRM-ADDRESS as the central support organization's administrator. Open Administration, then Users, and create these six accounts. The exact labels on the create-user screen are not verified. Use these values:
   - User name SLUG.test.clientadmin, team Client Administration Team
   - User name SLUG.test.mentoradmin, team Mentor Administration Team
   - User name SLUG.test.partner, team Partner Management Team
   - User name SLUG.test.funder, team Sponsor Management Team
   - User name SLUG.test.marketing, team Marketing Admin Team
   - User name SLUG.test.analytics, team Analytics Admin Team
3. For each of the six, also set:
   - Type: Regular, never Admin
   - Exactly one team, the one named above
   - Active: yes
   - A password of 20 letters and digits, stored first in the chapter's vault under the user name
   *You should see:* Six accounts in the Users list, each with one team.
4. Create the seventh, the Mentor Team test user, through Mentor Administration so it is linked to a mentor record (step 15.9). Sign in to APP-ADDRESS/mentoradmin/ as a mentor administrator, add a mentor named Test Mentor SLUG, fill in the required fields, set Accepting New Clients to yes, and set the status to Active. The exact label of the accepting field on screen is not verified.
   *You should see:* The mentor marked Complete, with a login created. Its user name is set by the software from the mentor's name; write it down.
5. Accepting new clients matters: the Assign list in step 17.4 offers only mentors who are Active, accepting new clients and linked to a login. Without it the list is empty and step 17.4 looks broken.
6. If the chapter has Create missing mailboxes switched on, setting the status creates a real Google mailbox for the test mentor, which takes a paid licence. Write the address down; step 17.9 deletes it.
7. Store the seventh account's password in the chapter's vault under its user name.

**Done when:** There is one non-administrator test account for each team.

**How to check:** Each test user signs in at APP-ADDRESS/, and the portal shows tiles for exactly one team.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Giving test users a second team "to make testing easier". The check then proves nothing about the single-team case real staff are in.

---

## 17.2 Confirm each test user sees only what their team allows

**Why:** A permission gap either locks staff out of their work or shows them records they must not see, and only a per-team test finds it.

**Who:** The central support organization

**Finish first:**

- step 17.1 Create one ordinary test user per team

**Do this:**

1. The test uses twelve addresses. Each returns the page's own session check: an allowed user gets an answer, a refused user gets a refusal naming the team needed. They are:
   - APP-ADDRESS/assignments/api/session
   - APP-ADDRESS/mentoradmin/api/session
   - APP-ADDRESS/mentorprofile/api/session
   - APP-ADDRESS/mentorsessions/api/session
   - APP-ADDRESS/partnersessions/api/session
   - APP-ADDRESS/sponsorsessions/api/session
   - APP-ADDRESS/ops/api/session
   - APP-ADDRESS/directory/mentors/api/session
   - APP-ADDRESS/myemail/api/session
   - APP-ADDRESS/analytics/api/session
   - APP-ADDRESS/events/api/session
   - APP-ADDRESS/setup/api/settings
2. For the first test user, open a private browser window, sign in at APP-ADDRESS/, then open each of the twelve addresses in the same window. Write down for each whether it answered with information or refused. Close the window, and repeat for each of the other six test users.
3. Compare what you wrote with what each test user must be allowed. Every address not listed for a user must be refused:
   - SLUG.test.clientadmin: assignments only
   - SLUG.test.mentoradmin: mentoradmin only
   - The Mentor Team test user: mentorprofile, mentorsessions, directory and myemail
   - SLUG.test.partner: partnersessions and myemail
   - SLUG.test.funder: sponsorsessions and myemail
   - SLUG.test.marketing: ops and events
   - SLUG.test.analytics: analytics only
   - setup: refused for all seven
   *You should see:* The same pattern as the trial chapter's record, prds/chapter-network/rehearsal-2026-08-31/nonadmin-gate-matrix.json, for the first eleven addresses. That record shows Not Found for the setup address, which is not the right answer; the next action says what is.
4. For the setup address, read the refusal. The right answer, when the settings page is switched on, is a refusal saying System Settings is restricted to administrators.
   *You should see:* That refusal, not "Not Found".

**Done when:** Every test user can open their own team's pages and is refused on every other team's pages. Administrator accounts skip all permission checks, so this must be done as ordinary users.

**How to check:** The pattern written down matches the list above for every test user.

**If it didn't work:** A "Not Found" answer is not a refusal. It means the page is switched off or the address is wrong. Find out which before calling it a pass. Any other difference from the table: stop, and ask the central support organization.

**What usually goes wrong:** Reading "not found" as "refused". In August the settings page answered "not found" to every test user, and the record cannot say why.

---

## 17.3 Submit the public application form

**Why:** The public form is how clients arrive, so it is tested from the chapter's own website the way a client would use it.

**Who:** The chapter and the central support organization — the central support organization, or anyone at the chapter

**Finish first:**

- step 17.2 Confirm each test user sees only what their team allows

**Do this:**

1. Open the chapter's website address in a private browser window and follow its link to the client application form. If stage 13 has not put the link on the website yet, open APP-ADDRESS/client-intake/ directly, carry on, and follow the website's link once stage 13 is done.
   *You should see:* The form at APP-ADDRESS/client-intake/.
2. Open each of the four policy links beside the consent box.
   *You should see:* Each of the chapter's own four policy documents, not Cleveland's.
3. Fill in the form with these made-up values, and write them down; step 17.9 removes them:
   - Business name: Test Bakery DELETE-ME
   - First name: Test
   - Last name: Applicant DELETE-ME
   - Email: an address on a mailbox the chapter controls
   - Every other required field: any plausible made-up value
4. Tick the consent box and submit.
   *You should see:* A thank-you message with a reference number. Write the reference number down.

**Done when:** A submission made from the public website arrives in the system.

**How to check:** The submission appears in Submission Admin at APP-ADDRESS/ops/, under its reference number.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A broken policy link on the consent box.

---

## 17.4 Assign the submission

**Why:** Assigning a new client to a mentor is the client administrator's main task, and it depends on several permissions at once.

**Who:** The central support organization signed in as the Client Administration Team test user

**Finish first:**

- step 17.3 Submit the public application form

**Do this:**

1. Sign in at APP-ADDRESS/ as SLUG.test.clientadmin and open Client Administration at APP-ADDRESS/assignments/.
2. Find the row for Test Bakery DELETE-ME. Its status is Submitted.
3. Use the row's Assign action and choose the Mentor Team test user's mentor, Test Mentor SLUG.
   *You should see:*
   - The row showing Test Mentor SLUG
   - The status Pending Acceptance
   - The email to the mentor opening, ready to send
4. Close the email without sending it.

**Done when:** A client administrator test user assigns it to a mentor.

**How to check:** The engagement shows Test Mentor SLUG and the status Pending Acceptance.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Two known failures. An empty mentor list: a mentor appears only when Active, accepting new clients and linked to an account. And a refusal about users: the client administration role needs permission to read users; Cleveland's role lacked it, and production still needs the fix.

---

## 17.5 Confirm the mentor sees it

**Why:** The assignment only matters if the mentor can find the client and work with them.

**Who:** The central support organization signed in as the Mentor Team test user

**Finish first:**

- step 17.4 Assign the submission

**Do this:**

1. In a new private browser window, sign in at APP-ADDRESS/ as the Mentor Team test user and open Client Management at APP-ADDRESS/mentorsessions/.
   *You should see:* Test Bakery DELETE-ME in the list, and it opens.
2. Open My Mentor Profile at APP-ADDRESS/mentorprofile/.
   *You should see:* Test Mentor SLUG's own details.

**Done when:** The mentor test user finds the assignment and can open their own profile.

**How to check:** The engagement opens, and the profile page shows the mentor's own details.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Client Management is empty. Nearly always the mentor record is not linked to the account, or the engagement was assigned to a duplicate mentor record with the same name. Check the link first.

---

## 17.6 Confirm the submission closes

**Why:** A submission that never reaches Completed means the background worker is not delivering to the CRM.

**Who:** The central support organization signed in as the Marketing Admin Team test user

**Finish first:**

- step 17.3 Submit the public application form

**Do this:**

1. In a new private browser window, sign in at APP-ADDRESS/ as SLUG.test.marketing and open Submission Admin at APP-ADDRESS/ops/.
2. Find the submission by the reference number from step 17.3.
   *You should see:*
   - Intake status: Completed
   - Response status: Closed
   - Close reason: Process completed

**Done when:** The submission shows as completed and closed to the user who handles submissions.

**How to check:** The submission reads Completed and Closed.

**If it didn't work:** A submission stuck at Received means the background worker is not running or cannot reach the CRM. Open APP-ADDRESS/healthz and read the worker section: a heartbeat older than 180 seconds means the worker is not running.

---

## 17.7 Confirm the CRM's own screen works for an ordinary user

**Why:** Staff also use the CRM directly, and a missing screen file shows an ordinary user a blank page.

**Who:** The central support organization

**Finish first:**

- step 17.1 Create one ordinary test user per team

**Do this:**

1. In a new private browser window, open CRM-ADDRESS and sign in as SLUG.test.clientadmin.
   *You should see:* The CRM's home screen, with the navigation bar across the top.

**Done when:** A non-administrator signs in to the CRM itself and sees a working screen.

**How to check:** The home screen and navigation bar appear.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A blank page. The CRM's screen code folder was not copied (step 9.8). The trial chapter hit exactly this.

---

## 17.8 Confirm the website pages work for a member of the public

**Why:** The public pages are what clients and volunteers see first, on computers and on phones.

**Who:** The chapter

**Finish first:**

- step 13.2 Send the events address to the events programme page

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. On a computer, open a private browser window, go to the chapter's website address, and follow its link to the events programme.
   *You should see:* The page at APP-ADDRESS/webinars/, with the chapter's name, menu and events.
2. Open one event from the calendar.
   *You should see:* The event's own page, with its title, date and a sign-up form.
3. The mentor directory: skip it. The public mentor directory page is not built yet (step 13.1). Write "not built" beside it.
4. Repeat the two events checks on a phone.
   *You should see:* One column, no sideways scrolling, no text cut off.

**Done when:** Someone not signed in to anything opens the mentor directory and events pages on the chapter's website and they work.

**How to check:** Each page shows the chapter's own content and name, on a computer and a phone.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A page with no styling at all, when the page and its stylesheet disagree. Cleveland shipped exactly this for an hour. Also, the public mentor directory page is not built yet (step 13.1).

---

## 17.9 Remove the test records

**Why:** Test records left behind turn up in the chapter's reports and lists.

**Who:** The central support organization

**Finish first:**

- step 17.2 Confirm each test user sees only what their team allows
- step 17.3 Submit the public application form
- step 17.4 Assign the submission
- step 17.5 Confirm the mentor sees it
- step 17.6 Confirm the submission closes
- step 17.7 Confirm the CRM's own screen works for an ordinary user
- step 17.8 Confirm the website pages work for a member of the public

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Sign in to CRM-ADDRESS as the central support organization's administrator and delete these records, in this order:
   - The engagement for Test Bakery DELETE-ME
   - The client profile for Test Bakery DELETE-ME
   - The contact Test Applicant DELETE-ME
   - The company Test Bakery DELETE-ME
2. Leave the submission in Submission Admin, closed. It is the record that the path worked.
3. In the CRM, open Administration, then Users, and set each of the seven test users to inactive, so the check can be repeated after a later release:
   - SLUG.test.clientadmin
   - SLUG.test.mentoradmin
   - The Mentor Team test user
   - SLUG.test.partner
   - SLUG.test.funder
   - SLUG.test.marketing
   - SLUG.test.analytics
4. In Mentor Administration, set Test Mentor SLUG's status to Inactive.
5. If step 17.1 created a Google mailbox for the test mentor, delete it in admin.google.com, so it stops taking a licence.
6. Write in the chapter's handover notes: the date, the four records deleted, and the seven users set inactive.

**Done when all of these are true:**

- The test submissions created for this stage are gone or disabled.
- The test assignments created for this stage are gone or disabled.
- The test users created for this stage are gone or disabled.
- It is written down what was removed.

**How to check:** A CRM search for DELETE-ME finds nothing, and each of the seven test users is refused at sign-in.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A test record left behind turns up in the chapter's reports. The analytics pages count every engagement.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.3 | 09-23-26 00:55 | Three corrections from the review before the first real chapter. Step 17.1 sets the test mentor to accepting new clients, without which the Assign list in step 17.4 is empty, and step 17.9 deletes any Google mailbox that created. Step 17.2 no longer points at a record whose settings-page answer the next action calls wrong. Step 17.3 no longer waits on stage 13: the website link is checked once it exists, and the rest of the form check runs without it. |
| 0.2 | 09-19-26 00:04 | Actions made precise (Doug, 09-19-26): exact test user names and teams, the twelve session-check addresses and the expected result per test user from the August table, exact made-up values for the test application, the pages and statuses to look for at each step, and the records and users to remove. The exact labels of the CRM's user screens are not verified, and the steps say so. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for checking everything works before going live (5-Methods-Form-Accounts-Checks.md, version 0.4) with the step list's finishing tests. |
