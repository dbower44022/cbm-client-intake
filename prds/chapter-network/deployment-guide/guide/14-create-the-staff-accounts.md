# Stage 14 — Create the staff accounts

**Version:** 0.2  
**Last Updated:** 09-19-26 00:15  
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

1. Make a list with one line per member of staff, giving:
   - Their full name.
   - Their chapter email address, on the chapter's own domain.
   - Their team or teams, spelled exactly as below.
2. Choose each person's teams from these seven, spelled exactly as written:
   - Client Administration Team
   - Mentor Administration Team
   - Mentor Team
   - Partner Management Team
   - Sponsor Management Team
   - Marketing Admin Team
   - Analytics Admin Team
3. Give each person the fewest teams that cover their work. A person with two jobs gets two teams.
4. Leave mentors off the list.
5. Have the chapter approve the list in writing.
   *You should see:* A list of names, chapter email addresses and teams, with the chapter's approval.

**Done when all of these are true:**

- A list names every member of staff, with their email address and their team.
- The list is approved by the chapter.

**Note:** Mentors are not on this list. Their accounts are created from their mentor records, at the end of the records stage (step 15.9).

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

1. Sign in to the CRM at https://CRM-ADDRESS as the central support organization's administrator, and open Administration, then Users.
2. For each person on the list, choose Create User and fill in:
   - User Name: their chapter email address
   - Type: Regular. Never Admin.
   - First Name and Last Name: from the list
   - Email: their chapter email address
   - Teams: the teams from the list
   - Default Team: their first team
   - Roles: leave empty. Permissions come from the teams.

   *You should see:* The user saved. These field labels are EspoCRM's standard ones and have not been checked on the chapter's version.
3. Set a password and send it to the person. EspoCRM's user screen offers to generate a password and email the person their sign-in details; use that option. Its exact label has not been checked.
   *You should see:* The person receives an email with their user name and a sign-in link.
4. For a partner or funder manager, also open https://APP-ADDRESS/mentoradmin/, create a mentor profile for them, and fill in its CBM email field with exactly their user name before saving. The software then links the existing account instead of creating a second one.
   *You should see:* The mentor profile linked to their existing account, with no second account created.

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

1. In the CRM, open Administration, then Users, and filter the list by Type equal to Admin.
   *You should see:*

   - Exactly two accounts
   - The central support organization's own administrator account (step 9.18)
   - The account the applications use to create logins
2. If any other account is an administrator, change its Type to Regular and tell the chapter why.

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

1. In the CRM, open Administration, then Auth Log. It records every sign-in by user name. The label is EspoCRM's standard one and has not been checked on the chapter's version.
2. Tick off every person on the staff list who appears there with a successful sign-in.
   *You should see:* Every person on the list ticked.
3. Chase anyone not ticked. Ask them to check their spam folder first. A person who lost their welcome email opens https://APP-ADDRESS/ and chooses Forgot your password?

**Done when:** Each member of staff has signed in at least once and set their own password.

**How to check:** No account on the list has a blank last sign-in date.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The welcome email going to spam, because the chapter's sending address is new. Ask each person to check spam before re-sending.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.2 | 09-19-26 00:15 | Every action made precise (Doug, 09-19-26): the seven team names as written, the exact user fields to fill in, the administrator filter, and the Auth Log check. Unchecked EspoCRM labels are marked as unchecked. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for creating the staff accounts (5-Methods-Form-Accounts-Checks.md, version 0.4) with the step list's finishing tests. |
