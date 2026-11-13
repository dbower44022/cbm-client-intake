# Stage 10 — Set up the Google permissions the software needs

**Version:** 0.9  
**Last Updated:** 11-13-26 10:30  
**Generated from** `steps/stage-10.yaml` — do not edit this page; edit the YAML and re-render.

---

## Summary

In this stage we give the applications a way to act inside the chapter's Google account. We create one account made for a program rather than a person, store its key in the chapter's vault, and have the chapter's own Google administrator grant that account an exact list of permissions. We also confirm the mailbox the applications will act as, and create the shared drive where every record's documents will be filed. The applications read and send the chapter's email, keep calendars in step, file documents and create mentor mailboxes, and every one of those goes through this single account. It comes before stage 11 because the applications need the key and the shared drive the moment they are deployed.

**Who:** The Association, inside the chapter's Google account, with the chapter's own Google administrator at the keyboard for the permission grant.  
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
- 10.6 Create the YouTube key and list the playlists, or record that they are not needed

---

## 10.1 Create the machine account

**Summary:** We create a Google Cloud project for the chapter and, inside it, a service account: an account made for a program rather than a person. The applications sign in to Google as this account, so nobody's personal sign-in is ever involved and nothing stops working when a person leaves. In the same project we switch on the five Google services the applications call, because Google refuses a call to a service that has not been switched on for the project. The account's Unique ID is the number the chapter's Google administrator will grant permission to in step 10.3.

**Who:** The Association inside the chapter's Google account

**Finish first:**

- step 4.5 Create the chapter's own administrator account

**Do this:**

1. In a browser, go to console.cloud.google.com and sign in as a Google administrator of the chapter's domain (stage 4). Screens below were checked on the Association's own account on 11-08-26. The first sign-in creates the domain's Google Cloud organization by itself, and the console then offers a free-trial banner across the top: dismiss it, the stage costs nothing.
2. Open the project picker at the top of the page and choose New project. Enter:
   - Project name: SHORT-LABEL-apps
   - Organization: the chapter's own domain

   *You should see:* The new project selected in the project picker. Google adds a number to the project's ID, for example bma-apps-514121; write the full project ID down, because every address below uses it. Below it is written PROJECT-ID.
3. Switch on each service by opening its page below and clicking the blue Enable button under its name. The console is slow: wait until the button is drawn before clicking, and wait about ten seconds after. A click that took moves the page to the service's details page, whose address ends /metrics. If it stays on the page with the Enable button, click again.
   - https://console.cloud.google.com/apis/library/admin.googleapis.com?project=PROJECT-ID
   - https://console.cloud.google.com/apis/library/gmail.googleapis.com?project=PROJECT-ID
   - https://console.cloud.google.com/apis/library/calendar-json.googleapis.com?project=PROJECT-ID
   - https://console.cloud.google.com/apis/library/drive.googleapis.com?project=PROJECT-ID
   - https://console.cloud.google.com/apis/library/meet.googleapis.com?project=PROJECT-ID (only if meeting transcripts will be switched on)

   *You should see:* At https://console.cloud.google.com/apis/dashboard?project=PROJECT-ID, the list headed Enabled APIs and services includes Admin SDK API, Gmail API, Google Calendar API and Google Drive API, among about twenty services Google switches on for every project.
4. Go to https://console.cloud.google.com/iam-admin/serviceaccounts/create?project=PROJECT-ID . The page is headed Create service account. Fill in the two fields below; Service account ID fills itself in from the name. Leave Permissions (optional) and Principals with access (optional) closed, and click Create and close.
   - Service account name: SHORT-LABEL-apps
   - Service account description: Machine account for the chapter applications: sends mail, books calendars, files documents

   *You should see:* The Service accounts list, with one account whose email is SHORT-LABEL-apps@PROJECT-ID.iam.gserviceaccount.com, status Enabled, and a number of about twenty digits in the column headed OAuth 2 Client ID.
5. Copy that OAuth 2 Client ID number into the chapter's Operations vault as a note named Google machine account client ID. It is the same number the account's Details tab calls Unique ID. Step 10.3 needs it.
   *You should see:* The note in the vault, holding the same digits as the list.

**Done when:** The account the software will use exists in the chapter's Google account.

**How to check:**

- At console.cloud.google.com, with SHORT-LABEL-apps showing in the project picker at the top of the page, open IAM and admin, then Service accounts. The list shows one account named SHORT-LABEL-apps, with an email address ending @PROJECT-ID.iam.gserviceaccount.com and a status of Enabled.
- Open that account. Its details page shows a Unique ID of about twenty digits. Open the note named Google machine account client ID in the chapter's Operations vault beside it and compare the two numbers digit by digit. They must be the same number: a wrong digit here means step 10.3 grants permission to an account that does not exist.
- Open APIs and services, then Enabled APIs and services. The list includes Admin SDK API, Gmail API, Google Calendar API and Google Drive API, and Google Meet REST API if meeting transcripts will be switched on. A service missing here is refused later with a message saying the API has not been used in this project or is disabled.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** The project is created under the wrong organization, or under no organization at all, because the person signed in with a personal Google account rather than the chapter's administrator account. The project picker names the organization beside each project; if it does not name the chapter's domain, sign out, sign in as the administrator from step 4.5 and start again.

---

## 10.2 Download and store its key

**Summary:** We create a key for the service account and put the key file in the chapter's vault. The key is how the applications prove to Google that they are this account. It is the whole of the chapter's Google access in one file, and anyone who holds the file can use it, so it goes into the vault and nowhere else, and the copy the browser downloaded is deleted straight afterwards. Stage 11 takes the key from the vault when the applications are deployed.

**Who:** The Association

**Finish first:**

- step 10.1 Create the machine account
- step 2.7 Set up the chapter's password vault

**Do this:**

1. Go to https://console.cloud.google.com/iam-admin/serviceaccounts?project=PROJECT-ID , click the account's email, and open the Keys tab. Under a yellow warning about key risks, click Add key, then Create new key. Choose:
   - Key type: JSON

   *You should see:* One file ending .json downloaded to the computer.
2. If Google says An Organization Policy that blocks service accounts key creation has been enforced on your organization, the block is on. Google switches it on for every organization created since 2024, and the Association's, created 11-08-26, had it. Being a Super Admin is not enough to lift it: first give yourself the role that can. Go to https://console.cloud.google.com/cloud-resource-manager and note the number beside the domain's name (the organization ID). Then go to https://console.cloud.google.com/iam-admin/iam?organizationId=ORGANIZATION-ID , click the pencil beside your own address, click Add another role, type the role below into the search box, choose it, and click Save.
   - Organization Policy Administrator

   *You should see:* Your row lists Organization Administrator and Organization Policy Administrator.
3. Go to https://console.cloud.google.com/iam-admin/orgpolicies/iam-managed-disableServiceAccountKeyCreation/edit?project=PROJECT-ID . Check that Applies to reads Project SHORT-LABEL-apps, not the organization. Choose Override parent's policy, click Add a rule, leave Enforcement on Off, click Done, then Set policy. Google asks Save and set policy changes without testing?: click Set policy.
   *You should see:* The policy page shows Policy source Override parent's policy and Status Not enforced. The older rule, at https://console.cloud.google.com/iam-admin/orgpolicies/iam-disableServiceAccountKeyCreation?project=PROJECT-ID , must also read Not enforced; it did on the Association's.
4. Take the role back off: at the same organization access page, click the pencil beside your address, click the bin beside Organization Policy Administrator only, and click Save. Then create the key again. A change can take a few minutes to reach the key page.
   *You should see:* Your row lists Organization Administrator alone.
5. In Proton Pass, open the chapter's Operations vault and add a new item named Google machine account key. Attach the downloaded .json file to it.
   *You should see:* The item in the Operations vault with the file attached, and a second named person able to open it.
6. Delete the downloaded .json file from the computer, and empty the computer's bin.
   *You should see:* A search of the downloads folder for .json finds nothing.

**Done when:** The key file is stored as a secret and is not left on anyone's laptop or in email.

**How to check:**

- In Proton Pass, open the chapter's Operations vault. An item named Google machine account key is there with one attachment, a file ending .json. Open the attachment. It is plain text that starts with a curly bracket and contains a line beginning "client_email" whose value ends @PROJECT-ID.iam.gserviceaccount.com, and a line beginning "client_id" whose value is the Unique ID from step 10.1. A file naming a different account is the key to the wrong project.
- A second named person at the Association opens the same item and sees the attachment. One person holding the only copy is the failure this vault exists to prevent.
- On the computer that did the download, search the Downloads folder for .json. It finds nothing. Then open the bin: it is empty. Also check the browser's own downloads list, which keeps a link to the file until it is cleared.
- At console.cloud.google.com, open the service account's Keys tab. Exactly one key is listed, dated today. If two are listed, the download was run twice: keep the one whose Key ID matches the "private_key_id" line in the file in the vault, and delete the other, so no key exists that the vault does not hold.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** The file stays in a downloads folder. It is not password-protected, and it gives whoever holds it the chapter's Google access.

---

## 10.3 Enter the permission grant

**Summary:** The chapter's Google administrator tells Google that the service account may act on behalf of the chapter's users, for an exact list of permissions (Google calls the mechanism domain-wide delegation). Without this grant the account exists but can do nothing. The list has to be exact, because a permission missed here does not fail here: it fails weeks later, in a message that does not say which permission is missing. Only the chapter's own administrator can enter the grant, which is why this step is booked in advance and why the Association reads the list aloud while the administrator types.

**Who:** The chapter and the Association — the chapter's Google administrator types; the Association reads out the list

**Finish first:**

- step 10.1 Create the machine account

**Do this:**

1. The chapter's Google administrator signs in at admin.google.com. Nobody else can do this step.
2. Go to https://admin.google.com/ac/owl/domainwidedelegation . The page is headed by the trail Security, API Controls, Domain-wide Delegation, with a list headed API clients. Click Add new beside that heading.
   *You should see:* A box headed Add a new client ID, with a Client ID field, a tick box Overwrite existing client ID, and a field OAuth scopes (comma-delimited).
3. In Client ID, paste the OAuth 2 Client ID from step 10.1 (it is in the Operations vault). Leave Overwrite existing client ID unticked.
4. In OAuth scopes (comma-delimited), paste these scopes, separated by commas with no spaces. They are exactly the scopes the software requests, read from its code (core/gmail.py, core/gcalendar.py, core/gdrive.py, core/google_directory.py, core/gmeet.py):
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
7. Click AUTHORIZE.
   *You should see:* A row in API clients: the Name is the service account's email address, the Client ID is the number, and Scopes shows the first two scopes then +5 More (or +6 More with the meeting scope).

**Done when:** The grant is entered in the chapter's own Google admin console with the exact list of permissions, and the list has been checked item by item against the standard. A missing permission fails later with a message that names nothing useful.

**How to check:**

- At https://admin.google.com/ac/owl/domainwidedelegation , signed in as the chapter's Google administrator, one row shows the Client ID from step 10.1. Open the note named Google machine account client ID in the chapter's Operations vault beside it and compare digit by digit. A row for a different number is a grant to an account that does not exist.
- Beside the Client ID, the row lists its scopes. Count them: seven, or eight if meeting transcripts will be switched on. Then read each one against the list in action 4 of this step, aloud, one at a time. Look for a space after a comma, a trailing full stop, or http instead of https; each one silently breaks that scope and nothing else.
- Check there is only one row for this Client ID. Google keeps all of an account's scopes in a single row, and a second row for the same number does not add to the first; it conflicts with it. If there are two, edit the first to hold the full list and delete the second.
- The real test is in stage 11, where steps 11.14 to 11.18 try each Google connection in turn. A grant takes a few minutes to take effect, and Google says it can take up to a day. A failure straight after authorizing that reads unauthorized_client is usually the wait, not a mistake: wait and try again before changing anything.

**If it didn't work:** If a Google check in stage 11 fails later, come back to this list first, before looking anywhere else.

**What usually goes wrong:** A permission missed. It does not fail here. It fails later, and the error does not say which permission is missing. Directory access needs two permissions, reading and changing; a grant with only the reading one fails at the very last check (step 11.18). The other known failure is a second row added for the same Client ID instead of editing the first: the two rows conflict rather than combine.

---

## 10.4 Name the mailbox the software acts as

**Summary:** We confirm that the shared operations mailbox from stage 4 is a real mailbox with its own licence, and write its address on the chapter information form. The applications read and send the chapter's shared mail as this mailbox, and Google lets the service account act only as a real licensed user. A group address or a forwarding alias looks the same in an address book, but Google refuses it, with a message that names nothing useful. This check has cost the project time before, so it is done here rather than discovered in stage 11.

**Who:** The chapter and the Association

**Finish first:**

- step 4.7 Create the shared operations mailbox

**Do this:**

1. Go to https://admin.google.com/ac/users , the list headed Users, and search for the shared operations mailbox address (for example info@CHAPTER-DOMAIN).
   *You should see:* The address listed as a user with Status Active and an Email usage figure. The list does not show licences: click the name to see the licence on the user's own page. If it is not in the users list at all, it is a group or an alias, and cannot be used.
2. Write the address on the chapter information form as the shared operations mailbox.

**Done when:** The mailbox is named, and it is a real licensed mailbox rather than a group or an alias. A group or alias is refused.

**How to check:**

- At admin.google.com, open Directory, then Users, and search for the address. It appears as a user with a person's or a team's name beside it. Open the user: the page names a Google Workspace licence against it. A user with no licence has no mailbox, and the applications cannot act as it.
- On that user's page, find the primary email address. The address written on the chapter information form must be that primary address, character for character. An address listed further down the page as an email alias is not a mailbox of its own, and must not be the one on the form.
- Open Directory, then Groups, and search for the same address. It must not appear there. An address that is a group appears here and not under Users.
- Signing in at mail.google.com as the address, with its own password from step 4.7, opens an inbox. A group or an alias has no password and no inbox to open.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A group address or a forwarding alias. Both look like email addresses and neither works, and the refusal names nothing useful. If the address has no licence, it is not a mailbox.

---

## 10.5 Create the shared drive and add the machine account

**Summary:** We create the shared drive that will hold every record's documents, and add the service account to it as a Manager. The applications file documents there as the service account, and give each person access to the folders for their own records, which is what the Manager role allows. A shared drive belongs to the chapter rather than to a person, so it survives staff changes; a folder in someone's own drive goes with them when they leave. Its identifier goes on the chapter information form, and stage 11 gives it to the applications.

**Who:** The Association inside the chapter's Google account

**Finish first:**

- step 10.1 Create the machine account

**Do this:**

1. Signed in as the chapter's Google administrator, go to https://drive.google.com/drive/shared-drives . On a domain with none yet, the page shows A place for teamwork and a blue button Create a shared drive; otherwise click New at top left. Either opens a box headed New shared drive. Replace the name in it with the one below and click Create.
   - CHAPTER-NAME Documents

   *You should see:* The new shared drive open and empty, its name at the top with 1 person under it.
2. Click Manage members at the top right of the drive. In Add people and groups, type the service account's email address from step 10.1 and press Enter, which turns it into a chip. Then set:
   - Role menu beside the address (it starts at Content manager): Manager. Cleveland's service account is a Manager of its shared drive, because it grants people access to folders.
   - Notify people: untick it. The service account has no mailbox. The blue button then reads Share instead of Send.
3. Click Share. Google then shows a box headed Share? saying the address is external to the organization. That is expected: every service account is outside the domain. Click Share anyway.
   *You should see:* The drive's heading now says 2 people.
4. Copy the shared drive's identifier from the browser's address bar: the characters after /folders/ (the address reads /drive/u/0/folders/ or similar). Write it on the chapter information form as the shared drive.
   *You should see:* A string of about nineteen letters and numbers, often starting 0A.

**Done when:** The shared drive exists and the machine account is a member of it.

**How to check:**

- At drive.google.com, signed in as the chapter's Google administrator, open Shared drives in the left-hand list. CHAPTER-NAME Documents is listed there, under Shared drives and not under My Drive. A drive that appears under My Drive is an ordinary folder, and the check has failed.
- Open the drive, click its name at the top of the page and choose Manage members. The service account's address, ending @PROJECT-ID.iam.gserviceaccount.com, is in the list with the role Manager. Any other role lets the applications file documents but not give people access to their folders.
- The rest of the member list is the chapter's Google administrator who created the drive, and nobody else. People are given access to single folders later, by the applications, never to the whole drive.
- With the drive itself open (not a folder inside it), the browser's address bar ends /folders/ followed by the identifier. The value on the chapter information form matches it character for character. It is about nineteen characters and usually begins 0A; a much longer value was copied from inside a folder and points at that folder, not the drive.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** An ordinary folder in somebody's personal drive instead of a shared drive. It works until that person leaves.

---

## 10.6 Create the YouTube key and list the playlists, or record that they are not needed

**Summary:** The events library brings recorded webinars in from the chapter's YouTube playlists. Reading a playlist needs an API key from the chapter's Google Cloud project, the one step 10.1 created. This step makes the key, limits it to YouTube, and records the playlists. A chapter with no recorded webinars records that instead.

**Who:** The Association inside the chapter's Google account; the chapter names the playlists

**Finish first:**

- step 10.1 Create the machine account

> This step has not yet been done on a real chapter. Follow it, and tell the Association anything that differs.

**Do this:**

1. Decide whether the chapter has recorded webinars on YouTube to bring in. If not, write "No YouTube playlists" on the chapter's account list (step 5.7), mark YouTube not in use on the YouTube sub-tab of System Settings once the applications run, and stop here.
2. In the Google Cloud console, open the project step 10.1 created, then APIs and services, then Library. Find YouTube Data API v3 and click Enable.
3. Open APIs and services, then Credentials. Click Create credentials, then API key.
   *You should see:* A new key, shown in a dialog.
4. Edit the key, and under its API restrictions allow only YouTube Data API v3. Copy the key into the chapter's Operations vault, in an item titled YouTube, labelled API key.
5. For each playlist to bring in, open it on YouTube and copy the part of its web address after list=. Write the identifiers in the YouTube item in the vault, one per line.
6. Once the applications run (stage 11), open System Settings, then the YouTube sub-tab of the Integrations tab, and set two settings:
   - YouTube API key: the key.
   - YouTube playlists: the playlist identifiers, separated by commas.

   *You should see:* The YouTube sub-tab's integration test names each playlist with its number of videos.

**Done when:** Either the key is in the vault, limited to YouTube, and set in System Settings with every playlist the chapter wants brought in, or a note records that this chapter has none.

**How to check:** The YouTube sub-tab of System Settings shows both settings as set, and its Test Integration button passes, naming every playlist.

**If it didn't work:** Stop, and ask the Association before going on.

**What usually goes wrong:** A private playlist, or an identifier copied short. YouTube does not find it, and the integration test names it. Cleveland's own list had one such playlist on 11-13-26.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.9 | 11-13-26 10:30 | Step 10.6 added: the YouTube key in the chapter's Google Cloud project, and the playlists (mapping approved by Doug 11-13-26). No existing step number changed. Steps that belong to an integration carry the new keys integration and check.auto, read by the setup checklist on System Settings' Integrations tab (prds/integrations-tab-plan.md section 4, mapping approved by Doug 11-13-26). |
| 0.8 | 11-08-26 23:44 | Step 10.2 done on the Business Mentors Association: stage 10 complete. |
| 0.7 | 11-08-26 23:41 | Step 10.2: the Association's new organization did block keys after all. The fix written out from the real screens: grant Organization Policy Administrator, override the block on the project only, check the older rule, and take the role back off. |
| 0.6 | 11-08-26 21:43 | Steps 10.1 and 10.3 to 10.5 done on the Business Mentors Association and rewritten from the real screens: a direct address for every page, the project ID's added number (PROJECT-ID) and the service account's real address, the Enable click that needs a wait, the OAuth 2 Client ID column, the Add a new client ID box, the role menu that starts at Content manager, the Share anyway warning, and /folders/ in the drive's address. Step 10.2 notes that the Association's new organization did not block keys. |
| 0.5 | 11-07-26 15:21 | Corrected while the Business Mentors Association is set up as a chapter (plan association-setup-plan.md, approved by Doug 11-07-26): "the central support organization" is now "the Association", and "the central committee" is "the central technical committee". |
| 0.4 | 09-25-26 12:50 | Rewritten for the reader (Doug, 09-25-26): the stage and every step open with a Summary, what is done and why in a few plain sentences, in place of the one-line Why. Every How to check is now a list of concrete checks naming where to look and what must be seen: the Unique ID compared digit by digit, the key file's own contents and the Keys tab, the single delegation row and its scope count, the primary address against the alias list, and the shared drive's place in the left-hand list and the length of its identifier. Two more known failures added: a project made under a personal account (10.1) and a second delegation row for the same Client ID (10.3). |
| 0.3 | 09-23-26 14:27 | The placeholder CHAPTER-SLUG is now SHORT-LABEL, the form's own name for it (Doug, 09-23-26: slug is a terrible name for a user). The guide's index lists every shared placeholder. |
| 0.2 | 09-19-26 00:07 | Every action made exact (Doug, 09-19-26: sweep every step): the Google Cloud project, the five APIs, the service account, the JSON key (including the organization policy that blocks keys by default), the domain-wide delegation entry with the exact scope list read from the software's code, one per line and as one pasteable line, and the shared drive with the Manager role Cleveland's own service account holds. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for the Google permissions (3-Methods-CRM-Google-Applications.md, version 0.5) with the step list's finishing tests. Numbered actions, a reason per step, and a check an app can run were added. |
