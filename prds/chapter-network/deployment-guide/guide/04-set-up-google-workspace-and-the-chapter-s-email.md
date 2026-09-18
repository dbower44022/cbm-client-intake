# Stage 4 — Set up Google Workspace and the chapter's email

**Version:** 0.1  
**Last Updated:** 09-18-26 17:20  
**Generated from** `steps/stage-04.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

Google Workspace is Google's paid service for an organization's email, calendars and documents. The software reads and sends the chapter's mail, creates calendar events and stores documents through it, so several of the mailboxes made here are used by the software and have rules of their own. This stage also takes the domain registrar account off the founder's personal email.

**Who:** The chapter's setup contact and its Google Workspace administrator, with the central support organization.  
**Time:** Most of a day, spread over two or three days while DNS records are seen and the nonprofit application is answered.  
**Before you start:** The agreement signed (stage 2); The domain names registered and in the chapter's Cloudflare account (stage 3); The nonprofit determination letter, for the discount (step 1.5)  
**When this stage is done:** The hosting and video meeting accounts can be opened with chapter addresses (stage 5). The Google permissions the software needs (stage 10) depend on the accounts made here.

**Steps in this stage:** 4.1 Choose the Google Workspace branch, 4.2 Create the Google Workspace account, 4.3 Verify the domain, 4.4 Switch mail delivery to Google, 4.5 Create the chapter's own administrator account, 4.6 Create the central support organization's administrator account, 4.7 Create the shared operations mailbox, 4.8 Create the alert sending mailbox, 4.9 Decide who receives the system's warning messages, 4.10 Create the members group, 4.11 Create the staff mailboxes, 4.12 Require two-step sign-in, 4.13 Apply for the nonprofit discount, 4.14 Move control of the registrar account to a chapter mailbox

---

## 4.1 Choose the Google Workspace branch

**Why:** Whether the chapter holds its own Google Workspace decides how hard it would be to leave later.

**Who:** chapter's board, advised by the central support organization  
**Finish first:** step 2.6

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Explain the two branches. In the first, the chapter holds its own Google Workspace and grants the software's machine account permission inside it. In the second, the central support organization provides the chapter a domain inside a Google Workspace it holds.
2. Give the board in writing what the second branch means on leaving. The chapter's mail, documents and calendars would sit in an account the central support organization controls. They can be moved out, but it is real work.
3. The board chooses and minutes the choice. It is proposed, not ruled, that every chapter that can should take the first branch. The rest of this stage is written for the first branch only.

**Done when:** The chapter has chosen either to hold its own Google Workspace or to have one provided by the central support organization, the choice is recorded, and the board has seen in writing what the provided option means if the chapter later leaves.

**How to check:** The board minutes record the choice and the written explanation.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Choosing the second branch for speed without reading the consequence. Nothing in the software differs between the branches, so nothing warns anyone later.

---

## 4.2 Create the Google Workspace account

**Why:** The chapter's mailboxes, calendars and shared documents all live in this account.

**Who:** The chapter — the setup contact  
**Finish first:** step 4.1, step 3.4

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Check step 3.2's record of which domain name is the email domain.
2. Sign up for Google Workspace using the chapter's email domain name.
3. When Google asks for the first administrator, use the setup contact's own name on a chapter address, not a role name. This account becomes the chapter's own administrator account in step 4.5.
4. Put the sign-in and its recovery codes in the chapter's vault.
5. Sign in to the Google Workspace admin console.
   *You should see:* The admin console's home page.

**Done when:** The account exists on the chapter's email domain and the first administrator can sign in.

**How to check:** The setup contact signs in to the Google Workspace admin console.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Signing up with the website domain name when the chapter chose a separate email domain name. The mailboxes then land on the wrong domain name.

---

## 4.3 Verify the domain

**Why:** Google will not deliver mail for a domain until the chapter proves it owns it.

**Who:** The chapter and the central support organization — the chapter's setup contact, with the central support organization's help  
**Finish first:** step 4.2, step 3.7

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the Google Workspace admin console, find the verification record Google gives for the domain.
2. In the chapter's Cloudflare account, open the domain's DNS records and add the verification record exactly as Google gives it. Add it in Cloudflare, not at the registrar.
3. Return to the admin console and ask it to check.
   *You should see:* The domain shown as verified. A new record can take from minutes to a day to be seen.

**Done when:** Google reports the domain as verified.

**How to check:** The admin console shows the domain as verified.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Impatience. A new DNS record can take from minutes to a day to be seen. Wait before assuming the record is wrong.

---

## 4.4 Switch mail delivery to Google

**Why:** Mail sent to the chapter's addresses must reach Google, and mail the chapter sends must not land in spam folders.

**Who:** The chapter and the central support organization — the chapter's setup contact, with the central support organization's help  
**Finish first:** step 4.3

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the Google Workspace admin console, find the mail delivery records Google gives.
2. In the chapter's Cloudflare account, set those records, replacing any mail records already there. Cloudflare shows mail records as DNS only by itself.
3. Also add the records Google recommends so the chapter's own mail is not marked as spam. The admin console lists them.
4. From a personal account outside the chapter, send a message to the first administrator's chapter address.
   *You should see:* The message arrives in the Google mailbox.

**Done when:** A message sent from outside to an address on the domain arrives in the Google mailbox.

**How to check:** A message from an outside account arrives in the first administrator's mailbox.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Skipping the records that stop the chapter's own mail being marked as spam. Everything works, and the software's welcome emails to new mentors land in spam folders.

---

## 4.5 Create the chapter's own administrator account

**Why:** The chapter must always be able to run its own Google Workspace, whatever happens to the central support organization.

**Who:** The chapter  
**Finish first:** step 4.2

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. The first administrator from step 4.2 is this account. Give it the highest administrator level Google Workspace offers.
2. Give a second person at the chapter the same level, so one person leaving does not lock the chapter out.
3. The named person signs in to the admin console with their chapter address.
   *You should see:* The admin console's home page.

**Done when:** A named person at the chapter holds a Google Workspace administrator account on a chapter address.

**How to check:** The named person signs in to the admin console with their chapter address.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The chapter's only administrator being the central support organization. That breaks the rule that the chapter can always withdraw the central support organization's access.

---

## 4.6 Create the central support organization's administrator account

**Why:** The central support organization needs its own named administrator account to enter the software's permission grant in step 10.3.

**Who:** The chapter and the central support organization — the chapter's administrator creates it; the central support organization uses it  
**Finish first:** step 4.5, step 2.4

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. The chapter's administrator creates a user for the central support organization's named person, with a licence.
2. Give it the highest administrator level. Step 10.3 needs it.
3. Hand over its sign-in details privately, never in an email to a group.
4. The central support organization's person signs in to the chapter's admin console with the account.
   *You should see:* The chapter's admin console.

**Done when:** The central support organization holds its own named administrator account, separate from the chapter's.

**How to check:** The central support organization signs in to the chapter's admin console with its own account.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The account uses a paid licence, like any user. Budget for it in the cost agreement (step 2.2).

---

## 4.7 Create the shared operations mailbox

**Why:** The software reads the chapter's public email and sends as this address, so every staff member sees the same conversation.

**Who:** chapter's administrator  
**Finish first:** step 4.5

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the admin console, create a user for the shared address, usually info@ the chapter's email domain, with its own licence. Do not create it as a group or as a second name for someone's mailbox.
2. Put its sign-in and recovery codes in the chapter's vault.
3. Look it up in the admin console's list of users.
   *You should see:* The address listed as a user with a licence, not in the list of groups.

**Done when:** The shared address the software reads and sends from exists as a real licensed mailbox, not as an alias or a group. An alias will not work.

**How to check:** The address appears in the admin console as a user with a licence.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Creating the address as a group or an alias. The software can only act as a real mailbox, and it fails later with an error that does not name the cause. Cleveland learned this when its administrator address turned out to be a group. Also, only one deployment may ever read a given shared operations mailbox.

---

## 4.8 Create the alert sending mailbox

**Why:** The software sends its warning messages from this address, and Google refuses to send as a group or an alias.

**Who:** chapter's administrator  
**Finish first:** step 4.5

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Either create a separate licensed user for the address, or use the shared operations mailbox from step 4.7. Cleveland uses its shared operations mailbox for both, which saves a licence.
2. Record the address on the chapter information form.
   *You should see:* The address listed in the admin console as a user with a licence.

**Done when:** The address the software sends its warning messages from exists as a real licensed mailbox. An alias or a group will be refused.

**How to check:** The address appears in the admin console as a user with a licence.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A group or an alias. It is refused, the same as in step 4.7.

---

## 4.9 Decide who receives the system's warning messages

**Why:** A warning nobody reads changes nothing, so the receiving address must reach named people.

**Who:** The chapter and the central support organization  
**Finish first:** step 4.5

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Choose one receiving address. Unlike the sending address, it may be a group.
2. Forward it to named people at the chapter and at the central support organization, as Cleveland's alert address forwards to its named system administrators.
3. Write the named people down beside the address.

**Done when:** The receiving address is decided and it reaches a person who reads it during the working week, not an unattended mailbox.

**How to check:** The named people are written down beside the address. The real test is step 12.4, once the software can send.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** An address nobody reads. The warnings then arrive and change nothing.

---

## 4.10 Create the members group

**Why:** When a new mentor's mailbox is created, the software adds the mentor to this group, so the chapter can write to all its members at once.

**Who:** chapter's administrator  
**Finish first:** step 4.5

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the admin console, create a group for all the chapter's members, at its own address.
2. Add a test member, then remove them.
   *You should see:* The test member appears in the group and then disappears.
3. Record the group's address on the chapter information form. The group is optional; if its address is left off the form, the software skips that part.

**Done when:** The group exists at its own address and the administrator can add and remove members.

**How to check:** The group appears in the admin console, and the administrator adds and removes a test member.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Adding members to the group needs one more permission in the software's grant than the rest. Step 10.3 lists it.

---

## 4.11 Create the staff mailboxes

**Why:** Staff sign in and are addressed at their chapter address only, never a personal one.

**Who:** chapter's administrator  
**Finish first:** step 4.5

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. For each member of staff, create a licensed user, first name and last name at the chapter's email domain.
2. Do not create mentors' mailboxes here. The software creates each mentor's mailbox from their mentor record (step 15.9).
   *You should see:* Every member of staff listed in the admin console.

**Done when:** Every member of staff who will use the system has a mailbox on the chapter's domain. Mentors' mailboxes are created later, from their mentor records (step 15.9).

**How to check:** Every name on the staff list (step 14.1) has a mailbox.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A mentor's mailbox created by hand. The software may then pick a different address for that mentor. Also, a staff member's personal address used in the software causes duplicate calendar invitations.

---

## 4.12 Require two-step sign-in

**Why:** The chapter's mailboxes hold client and mentor records, and a stolen password must not be enough to read them.

**Who:** chapter's administrator  
**Finish first:** step 4.5, step 4.6, step 4.7, step 4.8, step 4.9, step 4.10, step 4.11

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the admin console, turn on two-step sign-in, then enforce it for the whole organization. Give users a short grace period to set it up.
2. Set a second step on the shared mailboxes too. Put their recovery codes in the chapter's vault.
   *You should see:* The admin console reports two-step sign-in as enforced, and each user shows as enrolled.

**Done when:** Two-step sign-in is enforced for every account, and recovery is possible without one person.

**How to check:** The admin console reports two-step sign-in as enforced, each user enrolled, and the shared mailboxes' recovery codes are in the vault.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A shared mailbox whose second step is one person's phone. When that person is away, nobody can sign in to it.

---

## 4.13 Apply for the nonprofit discount

**Why:** The discount is claimed in the chapter's own name and lowers the Google Workspace bill the chapter pays every month.

**Who:** The chapter  
**Finish first:** step 1.5, step 4.2

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Apply through Google's nonprofit programme, which checks the chapter's nonprofit status before granting the discount.
2. Include the determination letter from step 1.5.
3. Write down the date the application went in and the expected answer date.

**Done when:** The application has been submitted with the chapter's nonprofit evidence, and the expected answer date is recorded.

**How to check:** The application is submitted, and the answer date is written down.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A chapter under a sponsoring nonprofit has no status of its own to apply with. See step 1.5 and the open question in the plan.

---

## 4.14 Move control of the registrar account to a chapter mailbox

**Why:** The domain names must not stay tied to one volunteer's personal email.

**Who:** The chapter — the setup contact  
**Finish first:** step 4.4

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the registrar account, change the contact and sign-in address to a chapter mailbox that more than one person can reach. The shared operations mailbox from step 4.7 is one choice.
2. Remove the founding email address from step 3.1.
3. Do the same in the Cloudflare account from step 3.7, which was also opened with the founding address.
4. Ask the registrar for a password reset.
   *You should see:* The password reset message arrives in the chapter mailbox.

**Done when:** The registrar account's contact address is a chapter mailbox, the founder's personal address has been removed, and a password reset test lands in the chapter mailbox.

**How to check:** The password reset message arrives in the chapter mailbox.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A loop. If the chapter's email is ever down because of a domain name problem, the registrar's password reset goes to that same broken email. Keep the registrar's recovery codes from step 3.6 safe for this case.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for setting up Google Workspace (8-Methods-Organization-Domains-Google.md, version 0.5) with the step list's finishing tests. Step 4.14 also moves the Cloudflare account off the founding address. |
