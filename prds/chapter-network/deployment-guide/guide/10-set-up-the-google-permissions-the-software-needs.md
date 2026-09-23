# Stage 10 — Set up the Google permissions the software needs

**Version:** 0.3  
**Last Updated:** 09-23-26 14:27  
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

1. In a browser, go to console.cloud.google.com and sign in as the chapter's Google administrator (the account from step 4.5). Labels below are Google Cloud's wording as of 2026, not checked on screen for this guide; if one differs, use the search box at the top of the console.
2. Open the project picker at the top of the page and choose New project. Enter:
   - Project name: SHORT-LABEL-apps
   - Organization: the chapter's own domain
   *You should see:* The new project selected in the project picker.
3. Open APIs and services, then Library. Search for each of these and choose Enable on each:
   - Admin SDK API
   - Gmail API
   - Google Calendar API
   - Google Drive API
   - Google Meet REST API (only if meeting transcripts will be switched on)
   *You should see:* Each API shown as enabled under APIs and services, then Enabled APIs and services.
4. Open IAM and admin, then Service accounts, and choose Create service account. Enter:
   - Service account name: SHORT-LABEL-apps
   - Service account ID: SHORT-LABEL-apps (filled in for you)
   - Roles: none. Skip the optional steps and choose Done.
   *You should see:* The service account listed, with an email address ending @SHORT-LABEL-apps.iam.gserviceaccount.com.
5. Open the service account. Copy its Unique ID, a number of about twenty digits, into the chapter's Operations vault as a note named Google machine account client ID. Step 10.3 needs it.
   *You should see:* The Unique ID on the service account's details page.

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

1. In the same service account, open the Keys tab, choose Add key, then Create new key. Choose:
   - Key type: JSON
   *You should see:* One file ending .json downloaded to the computer.
2. If Google refuses to create the key, the organization has the policy that blocks service account keys switched on. That is the default for Google Cloud organizations created since 2024. The chapter's Google administrator must allow keys for this one project: open IAM and admin, then Organization policies, find Disable service account key creation, and override it for project SHORT-LABEL-apps only. Then create the key again.
3. In Proton Pass, open the chapter's Operations vault and add a new item named Google machine account key. Attach the downloaded .json file to it.
   *You should see:* The item in the Operations vault with the file attached, and a second named person able to open it.
4. Delete the downloaded .json file from the computer, and empty the computer's bin.
   *You should see:* A search of the downloads folder for .json finds nothing.

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

1. The chapter's Google administrator signs in at admin.google.com. Nobody else can do this step.
2. Open Security, then Access and data control, then API controls, then Manage domain-wide delegation, and choose Add new. The menu names are Google's wording as of 2026, not checked on screen for this guide; if they differ, search the admin console for domain-wide delegation.
3. In Client ID, paste the Unique ID from step 10.1 (it is in the Operations vault).
4. In OAuth scopes, paste these scopes, separated by commas with no spaces. They are exactly the scopes the software requests, read from its code (core/gmail.py, core/gcalendar.py, core/gdrive.py, core/google_directory.py, core/gmeet.py):
   - https://www.googleapis.com/auth/gmail.readonly
   - https://www.googleapis.com/auth/gmail.send
   - https://www.googleapis.com/auth/calendar.events
   - https://www.googleapis.com/auth/drive
   - https://www.googleapis.com/auth/admin.directory.user.readonly
   - https://www.googleapis.com/auth/admin.directory.user
   - https://www.googleapis.com/auth/admin.directory.group
   - https://www.googleapis.com/auth/meetings.space.created (only if meeting transcripts will be switched on)
5. The same list as one line, ready to paste (leave off the last scope if meeting transcripts will not be switched on):
   - https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/calendar.events,https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/admin.directory.user,https://www.googleapis.com/auth/admin.directory.group,https://www.googleapis.com/auth/meetings.space.created
6. Read each scope back against the list above, one at a time, aloud, before saving. Look for a space after a comma, a trailing full stop, or http instead of https; each silently breaks one scope.
   *You should see:* Every scope on the list, spelled exactly, and nothing missing.
7. Choose Authorize.
   *You should see:* The client ID listed on the domain-wide delegation page, with the scopes beside it.

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

1. At admin.google.com, open Directory, then Users, and search for the shared operations mailbox address (for example info@CHAPTER-DOMAIN).
   *You should see:* The address listed as a user, with a Google Workspace licence shown against it. If it is not in the users list at all, it is a group or an alias, and cannot be used.
2. Write the address on the chapter information form as the shared operations mailbox.

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

1. Sign in at drive.google.com as the chapter's Google administrator. Open Shared drives and choose New. Enter:
   - Name: CHAPTER-NAME Documents
   *You should see:* The new shared drive open, and empty.
2. Open the shared drive's menu, choose Manage members, and add the service account's email address from step 10.1 (ending @SHORT-LABEL-apps.iam.gserviceaccount.com). Choose:
   - Access: Manager (Cleveland's service account is a Manager of its shared drive, because it grants people access to folders)
   - Notify people: off (the service account has no mailbox)
   *You should see:* The service account in the member list as Manager.
3. Copy the shared drive's identifier from the browser's address bar: the characters after /drive/folders/ . Write it on the chapter information form as the shared drive.
   *You should see:* A string of about nineteen letters and numbers, often starting 0A.

**Done when:** The shared drive exists and the machine account is a member of it.

**How to check:** The service account appears in the drive's member list.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** An ordinary folder in somebody's personal drive instead of a shared drive. It works until that person leaves.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.3 | 09-23-26 14:27 | The placeholder CHAPTER-SLUG is now SHORT-LABEL, the form's own name for it (Doug, 09-23-26: slug is a terrible name for a user). The guide's index lists every shared placeholder. |
| 0.2 | 09-19-26 00:07 | Every action made exact (Doug, 09-19-26: sweep every step): the Google Cloud project, the five APIs, the service account, the JSON key (including the organization policy that blocks keys by default), the domain-wide delegation entry with the exact scope list read from the software's code, one per line and as one pasteable line, and the shared drive with the Manager role Cleveland's own service account holds. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for the Google permissions (3-Methods-CRM-Google-Applications.md, version 0.5) with the step list's finishing tests. Numbered actions, a reason per step, and a check an app can run were added. |
