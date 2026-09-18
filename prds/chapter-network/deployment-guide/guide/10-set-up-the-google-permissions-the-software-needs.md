# Stage 10 — Set up the Google permissions the software needs

**Version:** 0.1  
**Last Updated:** 09-18-26 17:20  
**Generated from** `steps/stage-10.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The applications read and send the chapter's email, keep calendars in step, file documents on the shared drive and create mentor mailboxes. They do all of it through one machine account that the chapter's own Google administrator allows to act on the chapter's behalf. This stage creates that account and its permission, before the applications are deployed, because the applications need its key when they start.

**Who:** The central support organization, inside the chapter's Google account, with the chapter's own Google administrator at the keyboard for the permission grant.  
**Time:** Not known yet. This stage has never been done on a new chapter. Book an hour with the chapter's Google administrator for step 10.3.  
**When this stage is done:** The applications can be deployed with their Google key (stage 11), and the Google checks at the end of stage 11 can run.

**Before you start:**

- The chapter's Google Workspace, with its shared operations mailbox (stage 4)
- The chapter's vault, for the key this stage creates (step 2.7)

**Steps in this stage:**

- 10.1 Create the machine account
- 10.2 Download and store its key
- 10.3 Enter the permission grant
- 10.4 Name the mailbox the software acts as
- 10.5 Create the shared drive and add the machine account

---

## 10.1 Create the machine account

**Why:** The applications act on Google through an account made for a program, not a person, so no one person's sign-in is involved.

**Who:** The central support organization inside the chapter's Google account

**Finish first:**

- step 4.5 Create the chapter's own administrator account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the chapter's Google Cloud project, create a service account. The exact screen names are not verified for this guide, so follow Google's own current wording.
   *You should see:* The new service account, with a client identifier (a long number).
2. Write the client identifier down. Step 10.3 needs it.

**Done when:** The account the software will use exists in the chapter's Google account.

**How to check:** The service account appears in the project with a client identifier.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 10.2 Download and store its key

**Why:** The key file is the whole of the chapter's Google access in one file, so it goes straight into the vault and nowhere else.

**Who:** The central support organization

**Finish first:**

- step 10.1 Create the machine account
- step 2.7 Set up the chapter's password vault

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Create a key for the service account, in the JSON format, and download it.
   *You should see:* One file, downloaded.
2. Put the file in the chapter's Operations vault.
   *You should see:* The key file listed in the vault.
3. Delete the downloaded file from the computer, and empty the computer's bin.

**Done when:** The key file is stored as a secret and is not left on anyone's laptop or in email.

**How to check:** The file is in the vault, and a search of the downloads folder finds nothing.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The file stays in a downloads folder. It is not password-protected, and it gives whoever holds it the chapter's Google access.

---

## 10.3 Enter the permission grant

**Why:** The machine account can do nothing until the chapter's Google administrator allows it, and each permission missed here fails much later with an error that names nothing useful.

**Who:** The chapter and the central support organization — the chapter's Google administrator types; the central support organization reads out the list

**Finish first:**

- step 10.1 Create the machine account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. The chapter's Google administrator signs in to the chapter's Google admin console. Nobody else can do this step.
2. Open the setting that allows a service account to act on behalf of users in the domain (called domain-wide delegation). The exact menu path is not verified for this guide.
3. Add the client identifier from step 10.1.
4. Paste in the standard list of permissions. It covers:
   - Reading and sending mail.
   - Managing calendar events.
   - Reading and changing user accounts in the directory.
   - Managing groups.
   - Files on the shared drive.
5. Read each permission back against the standard list, one at a time, aloud.
   *You should see:* Every permission on the list, and nothing missing.
6. Save.
   *You should see:* The grant listed with the client identifier and the full list beside it.

**Done when:** The grant is entered in the chapter's own Google admin console with the exact list of permissions, and the list has been checked item by item against the standard. A missing permission fails later with a message that names nothing useful.

**How to check:** The grant is listed with the client identifier and every permission on the standard list.

**If it didn't work:** If a Google check in stage 11 fails later, come back to this list first, before looking anywhere else.

**What usually goes wrong:** A permission missed. It does not fail here. It fails later, and the error does not say which permission is missing. Directory access needs two permissions, reading and changing; a grant with only the reading one fails at the very last check (step 11.18).

---

## 10.4 Name the mailbox the software acts as

**Why:** The applications act as one mailbox when they read and send the chapter's mail, and Google refuses anything that is not a real mailbox.

**Who:** The chapter and the central support organization

**Finish first:**

- step 4.7 Create the shared operations mailbox

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In the chapter's Google admin console, open the list of users and find the shared operations mailbox.
   *You should see:* It is listed as a user with a licence, not as a group or an alias.
2. Write its address on the chapter information form as the shared operations mailbox.

**Done when:** The mailbox is named, and it is a real licensed mailbox rather than a group or an alias. A group or alias is refused.

**How to check:** The address appears in the users list with a licence attached.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A group address or a forwarding alias. Both look like email addresses and neither works, and the refusal names nothing useful. If the address has no licence, it is not a mailbox.

---

## 10.5 Create the shared drive and add the machine account

**Why:** Every record's documents are kept on one shared drive the chapter owns, and the applications file them there as the machine account.

**Who:** The central support organization inside the chapter's Google account

**Finish first:**

- step 10.1 Create the machine account

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In Google Drive, create a shared drive for the chapter's documents.
   *You should see:* The new shared drive in the list of shared drives.
2. Add the service account from step 10.1 as a member, with permission to create and manage files.
   *You should see:* The service account's address in the drive's member list.
3. Copy the shared drive's identifier (the string of letters at the end of its web address) onto the chapter information form.

**Done when:** The shared drive exists and the machine account is a member of it.

**How to check:** The service account appears in the drive's member list.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** An ordinary folder in somebody's personal drive instead of a shared drive. It works until that person leaves.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for the Google permissions (3-Methods-CRM-Google-Applications.md, version 0.5) with the step list's finishing tests. Numbered actions, a reason per step, and a check an app can run were added. |
