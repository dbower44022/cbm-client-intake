# Phase 9, stopping point 3 — Google Workspace's wizard screens for review

Last Updated: 11-15-26 11:23 · Revision 0.3 — see change log at the end.

**Scope B and the screens approved by Doug 11-15-26; built as v0.334.0.** The wizard rulings are W1 to
W6 (`prds/integrations-tab-plan.md` § 10). Each screen sits in the guide step
named beside it, under that step's `wizard:` key; the rendered guide does not
change.

## 1. The scope decision

The guide tags 23 steps as Google Workspace's, with about 90 actions between
them. **Stage 4 (steps 4.2 to 4.6, 4.11, 4.12) builds the Workspace account
itself**: sign-up, the domain, mail delivery, administrators, staff mailboxes
and two-step sign-in. All of it happens weeks before the application exists,
and nothing in it is a setting the application reads or can check. Step 12.4
is DigitalOcean's alerts, not Google's.

**Recommended (B): the wizard covers what the application connects to.**
One opening question asks whether Workspace is already set up. If not, one
screen sends the person to stage 4 of the guide, which already walks it
through step by step. Everything the application reads or can check gets its
own screens: the mailboxes and groups it names (4.7 to 4.10), the machine
account and its grant (10.1 to 10.5) and each feature switch (11.14 to
11.18). **43 screens at most.** A chapter that answers No to the optional
parts sees 28.

The other way (A) gives stage 4 one screen per action too. That is about 35
more screens, none of them checkable, for work that is always done before the
application runs. **The cost of B:** a chapter repairing its mail delivery
(step 4.4) or its two-step sign-in (step 4.12) gets no wizard help with it.
The guide still covers both.

## 2. What the screens need that does not exist yet

**Decided unless Doug objects:**

1. **A new check in the Google test: `grant`**, "Delegation: the whole
   grant". It mints a delegated token for every scope of step 10.3's list,
   whatever is switched on. It acts as the delegated admin, or as the shared
   mailbox when no admin is set. The meeting scope is included only while
   meeting transcripts are on. Today's test checks only the scopes of
   switched-on features, so it cannot prove the grant before anything is
   switched on. Every call is a read; minting a token sends nothing.
2. **A skipped check counts as passing on a screen.** "Not checked —
   switched off" means there is nothing to prove. Without this, a "Turn …
   on?" screen answered *Not yet* could never be passed.
3. **A new screen kind, `runs:`, for a phase 7 coded action.** The screen
   shows the action's button (here, Create the shared drive). The engine
   runs the action through the existing coded-action path, then the screen's
   check. Only the shared drive uses it for Google; Twilio's sender number
   will use it in part two.
4. **No new "a directory user exists" check is needed.** The screens that
   name a mailbox are checked by the test lines that read that mailbox, once
   the key and the grant exist.

## 3. The screens, in order, as Doug will see them

Each screen gives its type and check in brackets, then its text. "Done"
means the person clicks Done. A check written `test:…/x` runs the Google
integration test and reads its line `x`.

### Step 4.2 — the opening

**1. Does this chapter use Google Workspace?** *(question; check: answered)*
- What: The chapter's Google account: its mailboxes, calendars and shared drive.
- Why: The applications send the chapter's email, book mentors' meetings, file client documents and create mentors' mailboxes through it. Without it, none of those features can be switched on.
- Yes sets Google Workspace in use. No sets it not in use, and the wizard ends.

**2. Is the chapter's Google Workspace already set up?** *(question)*
- What: The account, its verified domain, mail delivered to Google, and a Super Admin who can sign in at admin.google.com (guide steps 4.2 to 4.6).
- Why: Everything after this screen happens inside that account.
- Yes goes to the next screen. No goes to screen 3.

**3. Set up Google Workspace first** *(Done; only after No on screen 2)*
- What: Building the chapter's Google account.
- Why: It must exist, with mail flowing to it, before the application can use it.
- How: Follow stage 4 of the deployment guide, steps 4.2 to 4.6, then 4.11 and 4.12. Come back here when a Super Admin can sign in at admin.google.com and a test message reaches a chapter mailbox.
- See: The admin console's home page, signed in as a Super Admin.
- If not: Stop and ask the Association.

### Step 4.7 — the shared operations mailbox

**4. Create the shared operations mailbox** *(Done)*
- What: A licensed user named info@ on the chapter's email domain. It is a user, never a group.
- Why: The applications send their mail as this address, and read the chapter's incoming mail from it.
- How: At admin.google.com, open Directory, then Users, then Add new user. First name: the chapter's name. Last name: Info. Primary email: info@ followed by the chapter's email domain. Click Continue, and copy the password straight into the chapter's Operations vault before leaving the page.
- See: info@ listed under Directory, then Users, with a licence, and not under Groups.
- If not: A group or an alias cannot be used. Delete it and create a user.

**5. Name the shared operations mailbox** *(box: Shared mailbox; check: set)*
- What: The address the applications send as and read incoming mail from.
- Why: Saving it here also starts the background worker reading that mailbox. Only one deployment may read a given mailbox, or every message is captured twice.
- How: Type info@ followed by the chapter's email domain, and click Save.
- If not: Check the address is the user created on screen 4.

### Step 4.8 — the alert sending address

**6. Send the system's warning messages from the shared mailbox?** *(question)*
- What: The address the system's warning messages come from.
- Why: Cleveland sends them from its shared mailbox, which saves a licence.
- Yes goes on to screen 9 and leaves Alert sending address empty, which means the shared mailbox. "A separate address" goes to screen 7.

**7. Create the alert sending mailbox** *(Done; only after "A separate address")*
- How: As screen 4, with Last name Alerts and Primary email alerts@ followed by the chapter's email domain.
- See: alerts@ under Directory, then Users, with a licence, and not under Groups.

**8. Name the alert sending address** *(box: Alert sending address; check: set; only after "A separate address")*
- How: Type alerts@ followed by the chapter's email domain, and click Save.

### Step 4.9 — who receives the warnings

**9. Create the System Administrators group** *(Done)*
- What: A group named admin@ on the chapter's email domain.
- Why: The system's warning messages go to it, and so does the sign-in mail of every account the chapter opens, so no message depends on one person.
- How: At admin.google.com, open Directory, then Groups, then Create group. Name: System Administrators. Group email: admin@ followed by the chapter's email domain. Group owners: the chapter administrator's address. Click Next.
- See: The access settings page.
- If not: A user already holding admin@ blocks the group. Rename that user first.

**10. Let outside senders post to it** *(Done)*
- What: The group's access settings.
- Why: The hosting provider's alerts and every account's password resets come from outside the chapter. Without External they are refused.
- How: Under Access type choose Restricted, then in the row Who can post tick External. Under Who can join the group choose Only invited users. Click Create group.
- See: The group listed with access type Custom.

**11. Add the group's members** *(Done)*
- How: Add at least two named officers of the chapter. Add a named person from the Association, by their own address, only if the chapter's access schedule says so.
- See: The members listed. Write their names on the chapter's account list (step 5.7).

**12. Name the alert receiving address** *(box: Alert receiving address; check: set)*
- How: Type admin@ followed by the chapter's email domain, and click Save.

**13. Test the group** *(Done)*
- How: From a personal account outside the chapter, send a message to admin@.
- See: The message arrives with every member of the group.
- If not: Check the group's Who can post includes External (screen 10).

### Step 4.10 — the members group

**14. Should a new mentor be added to an All Members group?** *(question)*
- What: A Google group of every member, which the application adds each new mentor's mailbox to.
- Why: The chapter writes to its whole membership through one address. Without it, the group step is skipped.
- Yes goes to screen 15. No goes to screen 17.

**15. Create the All Members group** *(Done; only after Yes)*
- How: At admin.google.com, open Directory, then Groups, then Create group. Name: All Members. Group email: allmembers@ followed by the chapter's email domain, or another the chapter prefers. Set who can post; only the group's own members is the usual choice.
- See: The group listed under Groups.

**16. Name the members group** *(box: All Members group; check: set; only after Yes)*

### Step 10.1 — the machine account

**17. Create the Google Cloud project** *(Done)*
- What: A project holding the machine account the applications sign in to Google with.
- Why: Google gives an application its access through a machine account, called a service account, and that lives in a project.
- How: Go to console.cloud.google.com, signed in as a Google administrator of the chapter's domain. Dismiss the free-trial banner; this costs nothing. Open the project picker at the top, choose New project, name it after the chapter's short label followed by -apps, for example akron-apps, with the chapter's own domain as Organization.
- See: The new project selected in the project picker. Write down its full project ID, which Google numbers, for example bma-apps-514121.

**18. Switch on Google's services** *(Done; each address with a Copy button)*
- Why: Each service lets the applications use one Google product.
- How: Open each address below, with the project ID in place of PROJECT-ID. Click the blue Enable button, and wait until the page moves to the service's details. The last one is only needed if meeting transcripts will be switched on.
- Copy: the five console addresses of guide step 10.1 (Admin SDK, Gmail, Calendar, Drive, Meet).
- See: Admin SDK API, Gmail API, Google Calendar API and Google Drive API under Enabled APIs and services.

**19. Create the machine account** *(Done)*
- How: Go to the Create service account page of the project. Service account name: the short label followed by -apps. Description: Machine account for the chapter applications. Click Create and close.
- See: One account in the Service accounts list, status Enabled, with a number of about twenty digits under OAuth 2 Client ID.

**20. Keep the machine account's client ID** *(Done)*
- How: Copy the OAuth 2 Client ID number into the chapter's Operations vault, as a note named Google machine account client ID.
- Why: Screen 26 needs it.

### Step 10.2 — the key

**21. Download the machine account's key** *(Done)*
- How: Click the account's email, open the Keys tab, click Add key, then Create new key, choose JSON.
- See: One file ending .json downloaded.
- If not: If Google says an Organization Policy blocks key creation, follow guide step 10.2, actions 2 to 4. They lift the block for this project only, then take the extra role back off. Then try again.

**22. Paste the key** *(box, secret: Google service account key; check: `test:google_workspace/key`)*
- What: The file's whole contents.
- Why: Without it the applications cannot sign in to Google, so no Google feature can work.
- How: Open the downloaded file in a text editor, copy everything in it, paste it in the box, and click Save. The value is never shown again.
- If not: Google refused the key. It may have been deleted or disabled in the console; create a new one.

**23. Store the key in the vault** *(Done)*
- How: In the chapter's Operations vault, add an item named Google machine account key and attach the file.
- See: The item, with a second named person able to open it.

**24. Delete the downloaded key** *(Done)*
- How: Delete the .json file from the computer and empty its bin.
- See: A search of the downloads folder for .json finds nothing.

### Step 10.3 — the grant

**25. Name the Google administrator the software acts as** *(box: Delegated Workspace admin; check: set)*
- What: A Super Admin's own address, for example the chapter administrator's (step 4.5).
- Why: Creating mentors' mailboxes and adding them to groups is done as this administrator. It must be a real licensed user; a group or an alias is refused by Google.
- How: Type the address and click Save.

**26. Enter the permission grant** *(Done; the scope line with a Copy button, in two versions; check: `test:google_workspace/grant`, new)*
- What: The list of what the machine account may do in the chapter's domain.
- Why: Each scope lets the applications do one thing: read or send mail, book a calendar event, file a document, create a mailbox.
- How: The chapter's Google administrator goes to https://admin.google.com/ac/owl/domainwidedelegation and clicks Add new. In Client ID, paste the number kept on screen 20. In OAuth scopes, paste the line below: the first copy if meeting transcripts will be switched on, the second if not. Leave Overwrite existing client ID unticked and click Authorize.
- See: A row in API clients whose Client ID is that number.
- If not: The scopes named above are missing from the grant. Check for a space after a comma, a full stop at the end, or http instead of https. Edit the row and click Authorize again.

(Step 10.4 has no screen: the shared mailbox it names is screen 5, and the
page never asks to set a value it already shows.)

### Step 10.5 — the shared drive

**27. Will the chapter keep client documents in Google Drive?** *(question)*
- What: The Documents tabs, which file client documents in a shared drive with a folder per client.
- Yes sets Drive identity to service, then screen 28. No goes to screen 31.

**28. Create the shared drive** *(button Create the shared drive, the phase 7 coded action; check: Shared drive ID set; only after Yes)*
- What: A shared drive named after the chapter, with the machine account as a Manager.
- Why: The machine account files every document and grants each person access to their folders.
- How: Click Create the shared drive. The application creates it, or finds one of that name, adds the machine account, and saves its ID.
- If not: Create it by hand as guide step 10.5 describes, then paste its ID on the next screen.

**29. Confirm the shared drive's ID** *(box: Shared drive ID; check: set; only after Yes)*
- How: The ID is filled in when screen 28 worked. Otherwise copy it from the browser's address bar, the characters after /folders/, and click Save.

**30. Turn on documents?** *(question; check: `test:google_workspace/drive`; only after Yes)*
- Yes sets Documents on. Not yet leaves it off.
- Why: Until it is on, the Documents tabs do not use the drive.

### Step 11.14 — incoming mail

**31. Read the chapter's incoming mail?** *(question; check: `test:google_workspace/mailbox`)*
- What: The background worker reading the shared mailbox every few minutes, and putting each message in Submission Admin. It also syncs each mentor's mail with their clients' records.
- Why: Gmail sync is the whole Communications pipeline. **It takes effect when the background worker next starts.**
- Yes sets Gmail conversation sync on, then screen 32. Not yet goes to screen 34.

**32. Restart the background worker** *(Done; only after Yes)*
- How: In the hosting account, open Apps, then the chapter's application, then Actions, then Force rebuild and deploy, or ask the Association. The exact wording of the hosting console has not been checked for this guide.
- See: A new deployment reaching Active.

**33. Send the shared mailbox a message** *(Done; only after Yes)*
- How: From an outside address, send a message to info@.
- See: Within about five minutes, the message in Submission Admin as a new email submission.
- If not: Ask Claude on this screen. The worker's log names the mailbox it acts as.

### Step 11.15 — outgoing mail

**34. Send a test message** *(Done)*
- How: Open a record in the application and send a message from it to an outside address you can read.
- See: The message arriving, with the chapter's own name as the sender.

### Step 11.16 — the calendar

**35. Book mentors' meetings in Google Calendar?** *(question; check: `test:google_workspace/calendar`)*
- What: A session saved as Scheduled puts an event, with a Meet link, on the mentor's own calendar.
- Yes sets Google Calendar events on. Not yet leaves it off.

**36. Turn on meeting transcripts?** *(question; check: `test:google_workspace/meet`)*
- What: Meet transcripts filed on each session after the meeting.
- Why: It needs the meeting scope in the grant (screen 26's first line). Without it, mentors see a transcription failure on every Scheduled save.
- Yes sets Meet transcripts on. Not yet leaves it off.

**37. Try the calendar** *(Done; only after Yes on screen 35)*
- How: Signed in as a mentor with a client, create a session with Status Scheduled and a start time tomorrow.
- See: The meeting on the mentor's Google calendar, with the client's contacts invited and a Meet link.

### Step 11.17 — the shared drive in use

**38. Try the documents** *(Done; only after Yes on screen 30)*
- How: Open a client in Client Management, open its Documents tab, and upload a small test file.
- See: The file on the Documents tab, and a folder for that client on the shared drive holding it.

### Step 11.18 — mentors' mailboxes

**39. Create each new mentor's mailbox from their mentor record?** *(question)*
- What: When a mentor is accepted, the application creates their mailbox on the mentors' domain and adds them to the All Members group.
- Why: It saves the administrator doing it by hand. The temporary password is shown once, to a person, never sent by the system.
- Yes goes to screen 40. Not now goes to the end.

**40. Name the mentors' email domain** *(box: Mentor email domain; check: set; only after Yes)*

**41. Check new mentors' addresses against the directory?** *(question; check: `test:google_workspace/directory`; only after Yes)*
- Yes sets Directory check on.

**42. Turn on mailbox creation?** *(question; check: `test:google_workspace/directory`; only after Yes)*
- Yes sets Create mailboxes and Mentor provisioning on. Not yet leaves them off.

**43. Try it with a test mentor** *(Done; only after Yes on screen 42)*
- How: In Mentor Administration, create a test mentor with a name no real mentor has and set Mentor Status to Accepted-Provisional. Copy the temporary password into the Operations vault. Sign in at mail.google.com as the new address. Then delete the test mailbox at admin.google.com, and the test mentor and its contact in the CRM.
- See: The mailbox opens and asks for a new password.

### The end

**44. The whole Google test** *(Done; check: `test:google_workspace`)*
- What: Every check of the Google integration test, for what is switched on.
- If not: The failing line is shown. Ask Claude about this.

43 screens when Workspace is already set up, every answer is Yes and a separate alert address is chosen;
28 on the shortest path (Workspace already set up, alerts from the shared
mailbox, no members group, no drive, nothing switched on yet).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.3 | 11-15-26 11:23 | Claude (Claude Code) | Approved by Doug; built as v0.334.0. |
| 0.2 | 11-15-26 11:15 | Claude (Claude Code) | Scope B approved by Doug: the wizard starts from an existing Workspace account. |
| 0.1 | 11-15-26 11:01 | Claude (Claude Code) | Draft for phase 9 stopping point 3. |
