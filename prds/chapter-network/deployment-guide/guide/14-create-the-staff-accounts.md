# Stage 14 — Create the staff accounts

**Version:** 0.1  
**Last Updated:** 09-18-26 17:20  
**Generated from** `steps/stage-14.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

Each member of the chapter's staff needs their own account to use the applications, on the team that opens the pages their job needs. Only an administrator can create an account, and nobody at the chapter is an administrator, so the central support organization does this from a list the chapter approves. Mentors are not created here: their accounts come from their mentor records at the end of the records stage (step 15.9).

**Who:** The central support organization, from a list the chapter writes and approves.  
**Time:** About an hour for a dozen staff, plus the time it takes everyone to sign in.  
**When this stage is done:** Bringing in the chapter's records and creating the mentor accounts (stage 15). The mentor administrator's account, created here, is what creates the mentor accounts.

**Before you start:**

- The CRM is built, with its teams and roles (stage 9)
- The applications are deployed (stage 11)
- Each member of staff has a mailbox on the chapter's domain (step 4.11)

**Steps in this stage:**

- 14.1 Agree which staff get an account and which team they are on
- 14.2 Create the staff accounts
- 14.3 Confirm nobody at the chapter holds an administrator account
- 14.4 Confirm every member of staff has signed in

---

## 14.1 Agree which staff get an account and which team they are on

**Why:** A person's team decides which pages they can open, so the list has to be right before any account exists.

**Who:** The chapter and the central support organization — the chapter writes the list; the central support organization checks it

**Finish first:**

- step 9.12 Attach the roles to the teams

**Do this:**

1. List each member of staff with their chapter email address and their team. The seven teams that open a page are:
   - Client Administration Team
   - Mentor Administration Team
   - Mentor Team
   - Partner Management Team
   - Sponsor Management Team
   - Marketing Admin Team
   - Analytics Admin Team
2. Give each person the fewest teams that cover their work. A person with two jobs gets two teams.
3. Leave mentors off the list.
4. Have the chapter approve the list in writing.
   *You should see:* A list of names, chapter email addresses and teams, with the chapter's approval.

**Done when all of these are true:**

- A list names every member of staff, with their email address and their team.
- The list is approved by the chapter.
- Mentors are not on this list. Their accounts are created from their mentor records, at the end of the records stage (step 15.9).

**How to check:** Every person on the list has a chapter email address and at least one team.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A personal email address on the list. Members of the chapter are addressed at their chapter address only. A personal address causes duplicate calendar invitations and mail going to the wrong place.

---

## 14.2 Create the staff accounts

**Why:** Each person needs an ordinary account on the right team before they can use the applications.

**Who:** The central support organization

**Finish first:**

- step 14.1 Agree which staff get an account and which team they are on

**Do this:**

1. Create each account as an ordinary user, not an administrator, with the teams from the list. The trial script scripts/rehearsal/stage4_users.py did this for the trial chapter; it has its seven made-up people written into it, so for a real chapter adapt it to read the list, or create the accounts by hand on the CRM's user administration screen.
2. Send each person their sign-in details by email from the CRM.
   *You should see:* Each account listed in the CRM, on its team.
3. For a partner or funder manager, create a mentor profile in Mentor Administration too. Fill in its chapter email address first, exactly matching their account's user name, so the software links the existing account instead of creating a second one.

**Done when:** Every person on the list has an account in the CRM on the right team.

**How to check:** Each person signs in to the applications and sees a tile for each of their teams, and no others.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Two known failures. A team with no role attached gives its members no access at all; check step 9.12 before blaming the account. And a partner or funder manager with no mentor profile cannot be chosen as a manager, because the pages that choose one list mentor profiles, not accounts.

---

## 14.3 Confirm nobody at the chapter holds an administrator account

**Why:** An administrator can change the CRM's setup, which would end the rule that every chapter runs the same software.

**Who:** The central support organization

**Finish first:**

- step 14.2 Create the staff accounts

**Do this:**

1. On the CRM's user administration screen, filter the list to administrators.
   *You should see:* Exactly two accounts, the central support organization's own administrator (step 9.18) and the account the applications use to create logins.

**Done when:** The only administrator accounts belong to the central support organization. Chapter staff hold ordinary accounts.

**How to check:** The list of administrators holds those two and nothing else.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A chapter asks for administrator access "just to fix one thing". Refuse it, and route the request through the support system (step 18.1).

---

## 14.4 Confirm every member of staff has signed in

**Why:** An account nobody has used is an account with a password somebody else may still know.

**Who:** The chapter and the central support organization — the chapter chases; the central support organization checks

**Finish first:**

- step 14.2 Create the staff accounts

**Do this:**

1. On the CRM's user administration screen, read the last sign-in date for each account.
2. Chase anyone with no date. A person who lost their welcome email uses "Forgot your password?" on the applications' sign-in page.
   *You should see:* A last sign-in date for every account.

**Done when:** Each member of staff has signed in at least once and set their own password.

**How to check:** No account on the list has a blank last sign-in date.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The welcome email going to spam, because the chapter's sending address is new. Ask each person to check spam before re-sending.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for creating the staff accounts (5-Methods-Form-Accounts-Checks.md, version 0.4) with the step list's finishing tests. |
