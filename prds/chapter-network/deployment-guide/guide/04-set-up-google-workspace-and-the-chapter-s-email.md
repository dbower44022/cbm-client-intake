# Stage 4 — Set up Google Workspace and the chapter's email

**Version:** 0.4  
**Last Updated:** 09-23-26 13:54  
**Generated from** `steps/stage-04.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

Google Workspace is Google's paid service for an organization's email, calendars and documents. The software reads and sends the chapter's mail, creates calendar events and stores documents through it, so several of the mailboxes made here are used by the software and have rules of their own. This stage also takes the domain registrar account off the founder's personal email.

**Who:** The chapter's setup contact and its Google Workspace administrator, with the central support organization.  
**Time:** Most of a day, spread over two or three days while DNS records are seen and the nonprofit application is answered.  
**When this stage is done:** The hosting and video meeting accounts can be opened with chapter addresses (stage 5). The Google permissions the software needs (stage 10) depend on the accounts made here.

**Before you start:**

- The agreement signed (stage 2)
- The domain names registered and in the chapter's Cloudflare account, or at its own DNS provider with manual DNS (stage 3)
- The nonprofit determination letter, for the discount (step 1.5)

**Steps in this stage:**

- 4.1 Confirm the chapter will hold its own Google Workspace
- 4.2 Create the Google Workspace account
- 4.3 Verify the domain
- 4.4 Switch mail delivery to Google
- 4.5 Create the chapter's own administrator account
- 4.6 Create the central support organization's administrator account
- 4.7 Create the shared operations mailbox
- 4.8 Create the alert sending mailbox
- 4.9 Decide who receives the system's warning messages
- 4.10 Create the members group
- 4.11 Create the staff mailboxes
- 4.12 Require two-step sign-in
- 4.13 Apply for the nonprofit discount
- 4.14 Move control of the registrar account to a chapter mailbox

---

## 4.1 Confirm the chapter will hold its own Google Workspace

**Why:** Every chapter hosts its own email on its own Google Workspace, so the chapter has to take on that account and its cost before anything is set up.

**Who:** chapter's board, advised by the central support organization

**Finish first:**

- step 2.6 Sign the agreement

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Tell the board what holding its own Google Workspace means:
   - The account is in the chapter's own name, on the chapter's own domain.
   - The chapter pays for it, with the nonprofit discount once it is granted (step 4.13).
   - The chapter's mail, documents and calendars stay with the chapter if it ever leaves.
   - The central support organization works inside it only by the chapter's grant.
2. The board records that the chapter will hold its own Google Workspace.

**Done when:** The board has recorded that the chapter will hold its own Google Workspace, in its own name and on its own domain.

**Note:** Ruled 09-18-26: every chapter hosts its own email on its own Google Workspace. The central support organization does not provide Google Workspace.

**How to check:** The board minutes record it.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 4.2 Create the Google Workspace account

**Why:** The chapter's mailboxes, calendars and shared documents all live in this account.

**Who:** The chapter — the setup contact

**Finish first:**

- step 4.1 Confirm the chapter will hold its own Google Workspace
- step 3.4 Register and pay for the domain names

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Open the chapter's record from step 3.2 and read which domain name is the email domain. Everything below uses that domain name, called EMAIL-DOMAIN.
2. In a browser, go to https://workspace.google.com and choose to get started. The exact wording of Google's screens has not been checked for this guide.
3. Answer Google's sign-up questions with these values:
   - Business name: the chapter's name, exactly as chosen in step 1.1
   - Number of employees: the number of staff who will have mailboxes
   - Region: United States
   - Current email address: the founding email address from step 3.1
   - Does the business have a domain: yes, and enter EMAIL-DOMAIN
4. When Google asks for the first user, enter the setup contact's own details:
   - First name and last name: the setup contact's own name, not a role such as Admin
   - Username: FIRSTNAME.LASTNAME, so the address is FIRSTNAME.LASTNAME@EMAIL-DOMAIN
   - Password: a new password, stored straight away in the chapter's Board vault (step 2.7)

   *You should see:* An account created, with this user as its first administrator. It becomes the chapter's own administrator account in step 4.5.
5. Choose the Business Starter plan, or the plan the cost agreement names (step 2.2), and pay with the chapter's own card (step 1.6). The nonprofit discount is applied for later, in step 4.13.
6. In a new browser window, go to https://admin.google.com and sign in as FIRSTNAME.LASTNAME@EMAIL-DOMAIN.
   *You should see:* The Google admin console's home page. Google will ask to verify the domain; that is step 4.3.

**Done when:** The account exists on the chapter's email domain and the first administrator can sign in.

**How to check:** The setup contact signs in to the Google Workspace admin console.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Signing up with the website domain name when the chapter chose a separate email domain name. The mailboxes then land on the wrong domain name.

---

## 4.3 Verify the domain

**Why:** Google will not deliver mail for a domain until the chapter proves it owns it.

**Who:** The chapter and the central support organization — the chapter's setup contact, with the central support organization's help

**Finish first:**

- step 4.2 Create the Google Workspace account
- step 3.7 Move the domain names' DNS to the chapter's Cloudflare account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the Google Workspace admin console, start domain verification and choose the method that adds a TXT record. Copy the value Google shows.
   *You should see:* A value beginning google-site-verification= followed by a long code. The code is different for every domain.
2. In the chapter's Cloudflare account, open the domain, then DNS, then Records, and choose Add record. Enter exactly:
   - Type: TXT
   - Name: @ (the domain itself)
   - Content: the whole value from Google, starting google-site-verification=
   - TTL: Auto

   *You should see:* The new TXT record in the list. Leave any other TXT records as they are.
3. With manual DNS, add the TXT record in the chapter's DNS provider account instead (step 3.7). Its screens differ by provider and are not given here; the record's values are the same.
4. Return to the admin console and choose to verify.
   *You should see:* The domain shown as verified. A new record can take from minutes to a day to be seen.

**Done when:** Google reports the domain as verified.

**How to check:** The admin console shows the domain as verified.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Impatience. A new DNS record can take from minutes to a day to be seen. Wait before assuming the record is wrong.

---

## 4.4 Switch mail delivery to Google

**Why:** Mail sent to the chapter's addresses must reach Google, and mail the chapter sends must prove it is genuine or it lands in spam folders.

**Who:** The chapter and the central support organization — the chapter's setup contact, with the central support organization's help

**Finish first:**

- step 4.3 Verify the domain

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Four DNS records are needed on the chapter's email domain, all added in the chapter's Cloudflare account (open the domain, then DNS, then Records). With manual DNS, add all four in the chapter's DNS provider account instead (step 3.7); its screens differ by provider and are not given here, and the records' values are the same:
   - One MX record, which sends incoming mail to Google.
   - One SPF record, which lists who may send mail as the domain.
   - One DKIM record, which lets receivers check a message's signature.
   - One DMARC record, which tells receivers what to do with mail that fails the other two.
2. Delete every existing MX record on the domain. Then choose Add record and enter exactly:
   - Type: MX
   - Name: @ (the domain itself)
   - Mail server: smtp.google.com
   - Priority: 1
   - TTL: Auto

   *You should see:* One MX record only, pointing at smtp.google.com. Cloudflare shows it as DNS only by itself. Cleveland's email domain uses exactly this record.
3. Look for an existing TXT record beginning v=spf1. A domain may have only one. If one exists, edit it; if not, choose Add record. Enter exactly:
   - Type: TXT
   - Name: @
   - Content: v=spf1 include:_spf.google.com ~all
   - TTL: Auto

   *You should see:* Exactly one TXT record beginning v=spf1.
4. In the Google Workspace admin console, open Apps, then Google Workspace, then Gmail, then Authenticate email. If the menu differs, search the admin console for Authenticate email. Choose the domain, then generate a new record with these settings:
   - Key length: 2048
   - Prefix selector: google

   *You should see:* A record name, google._domainkey, and a long value beginning v=DKIM1; k=rsa; p=.
5. In Cloudflare, choose Add record and enter exactly:
   - Type: TXT
   - Name: google._domainkey
   - Content: the whole value from the admin console, beginning v=DKIM1
   - TTL: Auto
6. Wait at least an hour, then return to Authenticate email in the admin console and choose Start authentication.
   *You should see:* The status for the domain reads that it is authenticating email with DKIM.
7. In Cloudflare, choose Add record and enter exactly, putting the first administrator's chapter address in place of REPORT-ADDRESS. Receivers send their reports to it. Change it to the alert receiving address once step 4.9 has decided that address:
   - Type: TXT
   - Name: _dmarc
   - Content: v=DMARC1; p=none; rua=mailto:REPORT-ADDRESS
   - TTL: Auto

   *You should see:* One TXT record named _dmarc.
8. From a personal account outside the chapter, send a message to the first administrator's chapter address.
   *You should see:* The message arrives in the chapter mailbox.
9. From the chapter mailbox, reply to that personal account. In the personal account, open the message and show its original, or its full headers.
   *You should see:*

   - SPF: PASS
   - DKIM: PASS
   - DMARC: PASS
10. Put a reminder in the chapter's calendar for four weeks' time, to change the DMARC record from p=none to p=quarantine once the reports show only the chapter's own mail. Cleveland's email domain now runs at p=reject.

**Done when:** A message sent from outside to an address on the domain arrives in the Google mailbox.

**How to check:** The outside message arrives, and the reply shows SPF, DKIM and DMARC all passing.

**If it didn't work:** Do not change the records again straight away. A changed record can take up to a day to be seen everywhere. Check the four records against the values above, character by character, then ask the central support organization.

**What usually goes wrong:** Three things. Leaving an old MX record from a previous mail provider: some mail then goes to the old provider and is never seen. Adding a second SPF record instead of editing the first: receivers then treat SPF as broken. And skipping DKIM or DMARC: everything seems to work, but the software's welcome emails to new mentors land in spam folders. Any other service that will send mail as the chapter's domain, such as a newsletter service or the website's contact form, must be added to the SPF record too; ask the central support organization.

---

## 4.5 Create the chapter's own administrator account

**Why:** The chapter must always be able to run its own Google Workspace, whatever happens to the central support organization.

**Who:** The chapter

**Finish first:**

- step 4.2 Create the Google Workspace account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Sign in to https://admin.google.com as the first administrator from step 4.2.
2. Open Account, then Admin roles. Check the first administrator holds the Super Admin role. The menu wording has not been checked for this guide.
   *You should see:* Super Admin listed for FIRSTNAME.LASTNAME@EMAIL-DOMAIN.
3. Create a second chapter officer's user the same way as step 4.11, then open that user's page, open Admin roles and privileges, and assign Super Admin.
   *You should see:* Two chapter people holding Super Admin.
4. Record both names and addresses on the chapter's account list (step 5.7) as the holders of the Google Workspace top-level sign-in.
5. The second officer signs in at https://admin.google.com with their own chapter address.
   *You should see:* The admin console's home page.

**Done when:** A named person at the chapter holds a Google Workspace administrator account on a chapter address.

**How to check:** The named person signs in to the admin console with their chapter address.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The chapter's only administrator being the central support organization. That breaks the rule that the chapter can always withdraw the central support organization's access.

---

## 4.6 Create the central support organization's administrator account

**Why:** The central support organization needs its own named administrator account to enter the software's permission grant in step 10.3.

**Who:** The chapter and the central support organization — the chapter's administrator creates it; the central support organization uses it

**Finish first:**

- step 4.5 Create the chapter's own administrator account
- step 2.4 Agree the access the central support organization will hold

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Sign in to https://admin.google.com as the chapter's administrator.
2. Open Directory, then Users, and choose Add new user. Enter:
   - First name: the central support person's first name
   - Last name: the central support person's last name
   - Primary email: FIRSTNAME.LASTNAME@EMAIL-DOMAIN, using the central support person's own name, never a shared name such as support
3. Let Google generate the password. Copy it straight into the chapter's Operations vault, and tell the central support person privately where to find it. Never email it.
4. Open the new user's page, open Admin roles and privileges, and assign Super Admin. Entering the software's permission grant in step 10.3 needs it.
   *You should see:* Super Admin listed for the central support person's account.
5. The central support person signs in at https://admin.google.com with the new address, sets their own password, and turns on two-step sign-in straight away.
   *You should see:* The chapter's admin console, reached from their own account.

**Done when:** The central support organization holds its own named administrator account, separate from the chapter's.

**How to check:** The central support organization signs in to the chapter's admin console with its own account.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The account uses a paid licence, like any user. Budget for it in the cost agreement (step 2.2).

---

## 4.7 Create the shared operations mailbox

**Why:** The software reads the chapter's public email and sends as this address, so every staff member sees the same conversation.

**Who:** chapter's administrator

**Finish first:**

- step 4.5 Create the chapter's own administrator account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Sign in to https://admin.google.com as the chapter's administrator. Open Directory, then Users, and choose Add new user.
2. Enter exactly:
   - First name: the chapter's name, for example Akron Business Mentors
   - Last name: Info
   - Primary email: info@EMAIL-DOMAIN
3. Let Google generate the password and copy it straight into the chapter's Operations vault.
4. Open Directory, then Users, and find info@EMAIL-DOMAIN.
   *You should see:* info@EMAIL-DOMAIN listed as a user with a Google Workspace licence. It must not appear under Directory, then Groups.
5. Write info@EMAIL-DOMAIN on the chapter information form as the shared operations mailbox. The software reads it as OPS_MAILBOX.

**Done when:** The shared address the software reads and sends from exists as a real licensed mailbox, not as an alias or a group. An alias will not work.

**How to check:** The address appears in the admin console as a user with a licence.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Creating the address as a group or an alias. The software can only act as a real mailbox, and it fails later with an error that does not name the cause. Cleveland learned this when its administrator address turned out to be a group. Also, only one deployment may ever read a given shared operations mailbox.

---

## 4.8 Create the alert sending mailbox

**Why:** The software sends its warning messages from this address, and Google refuses to send as a group or an alias.

**Who:** chapter's administrator

**Finish first:**

- step 4.5 Create the chapter's own administrator account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Use the shared operations mailbox from step 4.7 as the sending address. Cleveland does the same, and it saves a licence.
2. On the chapter information form, write info@EMAIL-DOMAIN as the alert sending address, or leave it empty. The software reads it as ALERT_EMAIL_FROM, and when it is empty it sends from OPS_MAILBOX anyway.
3. Only if the chapter wants a separate sending address: create a second user exactly as in step 4.7, with Last name Alerts and Primary email alerts@EMAIL-DOMAIN, and write that address on the form instead.
   *You should see:* The sending address listed under Directory, then Users, with a licence, and not under Groups.

**Done when:** The address the software sends its warning messages from exists as a real licensed mailbox. An alias or a group will be refused.

**How to check:** The address appears in the admin console as a user with a licence.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A group or an alias. It is refused, the same as in step 4.7.

---

## 4.9 Decide who receives the system's warning messages

**Why:** A warning nobody reads changes nothing, so the receiving address must reach named people.

**Who:** The chapter and the central support organization

**Finish first:**

- step 4.5 Create the chapter's own administrator account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Sign in to https://admin.google.com. Open Directory, then Groups, and choose Create group. Enter:
   - Name: System Administrators
   - Group email: admin@EMAIL-DOMAIN
   - Description: Receives the system's warning messages
2. In the group's access settings, let people outside the organization post to the group. The hosting provider's alerts come from outside the chapter. The setting's exact wording has not been checked for this guide.
3. Add these members to the group:
   - At least one named officer of the chapter
   - At least one named person from the central support organization, by their own address
4. Write admin@EMAIL-DOMAIN on the chapter information form as the alert receiving address. The software reads it as ALERT_EMAIL_TO. Write the members' names beside it on the chapter's account list (step 5.7).
5. From a personal account outside the chapter, send a test message to admin@EMAIL-DOMAIN.
   *You should see:* The test message arrives with every member of the group.

**Done when:** The receiving address is decided and it reaches a person who reads it during the working week, not an unattended mailbox.

**How to check:** The named people are written down beside the address. The real test is step 12.4, once the software can send.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** An address nobody reads. The warnings then arrive and change nothing.

---

## 4.10 Create the members group

**Why:** When a new mentor's mailbox is created, the software adds the mentor to this group, so the chapter can write to all its members at once.

**Who:** chapter's administrator

**Finish first:**

- step 4.5 Create the chapter's own administrator account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Sign in to https://admin.google.com. Open Directory, then Groups, and choose Create group. Enter:
   - Name: All Members
   - Group email: allmembers@EMAIL-DOMAIN, or another address the chapter prefers
   - Description: Every member of the chapter
2. In the group's access settings, set who can post. That is the chapter's choice. Only the group's own members posting is the usual choice.
3. Add yourself as a test member, then remove yourself.
   *You should see:* The member appears in the group's member list and then disappears.
4. Write the group's address on the chapter information form as the members group. The software reads it as GOOGLE_MEMBERS_GROUP. Leaving it empty turns this feature off.

**Done when:** The group exists at its own address and the administrator can add and remove members.

**How to check:** The group appears in the admin console, and the administrator adds and removes a test member.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Adding members to the group needs one more permission in the software's grant than the rest. Step 10.3 lists it.

---

## 4.11 Create the staff mailboxes

**Why:** Staff sign in and are addressed at their chapter address only, never a personal one.

**Who:** chapter's administrator

**Finish first:**

- step 4.5 Create the chapter's own administrator account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Sign in to https://admin.google.com. For each member of staff the chapter names now (the full list is confirmed later, in step 14.1), open Directory, then Users, and choose Add new user. Enter:
   - First name: their first name
   - Last name: their last name
   - Primary email: FIRSTNAME.LASTNAME@EMAIL-DOMAIN
   - Secondary email: their personal address, used only to send them their sign-in details
2. Let Google generate a password, and choose the option that asks for a new password at the first sign-in. Send the sign-in details to the secondary email. The option wording has not been checked for this guide.
3. Do not create mentors' mailboxes here. The software creates each mentor's mailbox from their mentor record (step 15.9).
4. Open Directory, then Users.
   *You should see:* Every member of staff listed, each with a licence.

**Done when:** Every member of staff who will use the system has a mailbox on the chapter's domain. Mentors' mailboxes are created later, from their mentor records (step 15.9).

**How to check:** Every name on the staff list (step 14.1) has a mailbox.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A mentor's mailbox created by hand. The software may then pick a different address for that mentor. Also, a staff member's personal address used in the software causes duplicate calendar invitations.

---

## 4.12 Require two-step sign-in

**Why:** The chapter's mailboxes hold client and mentor records, and a stolen password must not be enough to read them.

**Who:** chapter's administrator

**Finish first:**

- step 4.5 Create the chapter's own administrator account
- step 4.6 Create the central support organization's administrator account
- step 4.7 Create the shared operations mailbox
- step 4.8 Create the alert sending mailbox
- step 4.9 Decide who receives the system's warning messages
- step 4.10 Create the members group
- step 4.11 Create the staff mailboxes

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Sign in to https://admin.google.com. Open Security, then Authentication, then 2-step verification. The menu wording has not been checked for this guide.
2. Set exactly:
   - Allow users to turn on 2-step verification: on
   - Enforcement: on, from a date one week away
   - New user enrollment period: 1 week
   - Methods: any except verification codes sent by text message or phone call

   *You should see:* The settings saved for the whole organization.
3. Sign in as info@EMAIL-DOMAIN and turn on two-step sign-in at https://myaccount.google.com/signinoptions/twosv, using an authenticator app held by two named people, not one person's phone.
4. On the same page, generate backup codes for info@EMAIL-DOMAIN and put them in the chapter's Operations vault. Do the same for any other shared mailbox.
5. After the enforcement date, open Directory, then Users, and add the 2-step verification enrollment column.
   *You should see:* Every user shown as enrolled.

**Done when:** Two-step sign-in is enforced for every account, and recovery is possible without one person.

**How to check:** The admin console reports two-step sign-in as enforced, each user enrolled, and the shared mailboxes' recovery codes are in the vault.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A shared mailbox whose second step is one person's phone. When that person is away, nobody can sign in to it.

---

## 4.13 Apply for the nonprofit discount

**Why:** The discount is claimed in the chapter's own name and lowers the Google Workspace bill the chapter pays every month.

**Who:** The chapter

**Finish first:**

- step 1.5 Obtain nonprofit tax status, or a sponsorship arrangement
- step 4.2 Create the Google Workspace account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In a browser, go to https://www.google.com/nonprofits and choose to get started. Sign in as the chapter's administrator from step 4.5.
2. Fill in the application with the chapter's legal name, its employer identification number from step 1.3, and its address, exactly as they appear on the determination letter from step 1.5.
3. Google's verification partner, Goodstack (formerly called Percent), checks the chapter's nonprofit status. If it asks for evidence, upload the determination letter from step 1.5. That this is still the verification partner has not been checked for this guide.
4. Write the date the application went in on the chapter's account list (step 5.7), with the expected answer date Google gives.
5. Once approved, activate Google Workspace for Nonprofits from the Google for Nonprofits account, and choose the chapter's existing Google Workspace domain. The exact screens have not been checked for this guide.
   *You should see:* The admin console's billing page shows the nonprofit plan.

**Done when:** The application has been submitted with the chapter's nonprofit evidence, and the expected answer date is recorded.

**How to check:** The application is submitted, and the answer date is written down.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A chapter under a sponsoring nonprofit has no status of its own to apply with. See step 1.5 and the open question in the plan.

---

## 4.14 Move control of the registrar account to a chapter mailbox

**Why:** The domain names must not stay tied to one volunteer's personal email.

**Who:** The chapter — the setup contact

**Finish first:**

- step 4.4 Switch mail delivery to Google

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Sign in to the registrar account from step 3.3. Open its account profile or contact settings. Registrars name this page differently; if it cannot be found, search the registrar's help pages for how to change the account email.
2. Change the account's sign-in and contact email to info@EMAIL-DOMAIN, and confirm the change from the message sent there.
3. Delete the founding email address from step 3.1 from every contact field on the account.
4. Sign in to Cloudflare, open My Profile, and change the email address to info@EMAIL-DOMAIN. Confirm the change from the message sent there. With manual DNS, do the same in the chapter's DNS provider account, unless the registrar hosts the DNS.
   *You should see:* Both accounts show info@EMAIL-DOMAIN.
5. Sign out of the registrar and use its forgotten-password link with info@EMAIL-DOMAIN.
   *You should see:* The password reset message arrives in info@EMAIL-DOMAIN. Do not complete the reset unless you mean to; if you do, put the new password in the chapter's vault.

**Done when all of these are true:**

- The registrar account's contact address is a chapter mailbox.
- The founder's personal address has been removed.
- A password reset test lands in the chapter mailbox.

**How to check:** The password reset message arrives in the chapter mailbox.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A loop. If the chapter's email is ever down because of a domain name problem, the registrar's password reset goes to that same broken email. Keep the registrar's recovery codes from step 3.6 safe for this case.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.4 | 09-23-26 13:54 | Manual DNS added (Doug, 09-23-26): steps 4.3 and 4.4 say that a chapter keeping its own DNS provider adds the same records there, and step 4.14 moves that provider account's email too. |
| 0.3 | 09-19-26 00:05 | Every action outside steps 4.3 and 4.4 made precise (Doug, 09-19-26): the web addresses to open, the admin console paths, the exact user and group names to create (info@, admin@, allmembers@), the fields to fill in, the two-step sign-in settings, and the nonprofit application route. Screen wording not checked on screen is marked as such. |
| 0.2 | 09-19-26 00:20 | Steps 4.3 and 4.4 rewritten with the exact DNS records to add in Cloudflare, field by field: the verification record, and the MX, SPF, DKIM and DMARC records, with a header check that all three pass (Doug, 09-19-26). Values read from Cleveland's live email domain. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for setting up Google Workspace (8-Methods-Organization-Domains-Google.md, version 0.5) with the step list's finishing tests. Step 4.14 also moves the Cloudflare account off the founding address. |
