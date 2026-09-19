# Stage 16 — Train the chapter's staff

**Version:** 0.2  
**Last Updated:** 09-19-26 00:04  
**Generated from** `steps/stage-16.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

Staff learn the system on invented records before they touch real ones. Training happens on Cleveland's shared training system, which clears itself every night, using shared training accounts set up specifically for chapter training (ruled 09-14-26 and 09-18-26).

**Who:** The chapter's trainer runs the sessions; the central support organization sets up the training accounts and hands over the guides.  
**Time:** One session per role. The mentor session is the longest, at 30 to 40 minutes.  
**When this stage is done:** The final checks before going live (stage 17), with staff who know what they are checking.

**Before you start:**

- The staff accounts (stage 14)
- The chapter training accounts on the shared training system (work list item 6 — they do not exist yet)

**Steps in this stage:**

- 16.1 Get the chapter's staff onto the shared practice system
- 16.2 Explain how the practice system behaves
- 16.3 Train each role
- 16.4 Hand over the written guides
- 16.5 Name the chapter's own first point of contact
- 16.6 Change the training account passwords

---

## 16.1 Get the chapter's staff onto the shared practice system

**Why:** Trainees need working sign-ins, and fresh passwords stop the previous chapter keeping access.

**Who:** The central support organization

**Finish first:**

- step 14.2 Create the staff accounts

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Know the addresses first. The shared training system is Cleveland's test system:
   - The CRM: https://crm-test.clevelandbusinessmentors.org
   - The applications: https://cbm-client-intake-svxs3.ondigitalocean.app/
   - The server that holds its nightly reset: root@104.131.45.208
2. Know which accounts to change. There is one chapter training account per team that opens a page in the applications. Their user names are not known yet: they are chosen when the accounts are built (work list item 6). Until then, this step cannot be completed. The seven teams are:
   - Client Administration Team
   - Mentor Administration Team
   - Mentor Team
   - Partner Management Team
   - Sponsor Management Team
   - Marketing Admin Team
   - Analytics Admin Team
3. For each chapter training account, make a new password of 20 letters and digits only, with no punctuation. Store it straight away in the central support organization's own vault, in an entry named TRAINING-ACCOUNT-USER-NAME training password. That vault is not set up yet (work list item 1).
4. Sign in to https://crm-test.clevelandbusinessmentors.org as an administrator. Open Administration, then Users, then the chapter training account, and set its password to the new one. The exact label of the password action on the user screen is not verified; look for the action that changes the user's password.
   *You should see:* The password saved with no error, for each of the seven accounts.
5. In a terminal, go to the software's code folder:
   - cd ~/Dropbox/Projects/cbm-client-intake
6. Refresh the training data, so its dates are current before they are frozen:
   - uv run python scripts/sandbox/seed_training_data.py --apply
   *You should see:* The script finishing without an error. On a second run the same day it reports everything current and writes nothing.
7. Re-capture the shared training system's fixed copy, so the new passwords survive the nightly reset:
   - ssh root@104.131.45.208 'python3 /usr/local/sbin/reset_crm_sandbox.py baseline --apply'
   *You should see:* The script finishing without an error. Without this, the new passwords undo themselves at midnight.
8. Confirm the fixed copy was taken:
   - ssh root@104.131.45.208 'python3 /usr/local/sbin/reset_crm_sandbox.py status'
   *You should see:* The status reporting a baseline captured today.
9. Give the chapter's trainer the seven user names and passwords by a private route, such as a shared entry in a vault or a one-to-one message. Never send them in an email to a group.
10. The next morning, have one person from the chapter open https://cbm-client-intake-svxs3.ondigitalocean.app/ and sign in with one of the new passwords.
   *You should see:* The portal, with "(Test)" after the version number in the footer.

**Done when all of these are true:**

- The chapter's trainer holds the sign-in details for the chapter training accounts.
- The passwords were set fresh for this chapter.
- One person from the chapter has signed in once.

**Note:** Ruled 09-14-26: chapters train on the existing test system rather than on their own live system or on a practice system built for them. Ruled 09-18-26: they sign in with shared training accounts set up specifically for chapter training, never with accounts of their own.

**How to check:** The morning after, someone from the chapter signs in with a new password, and the footer reads "(Test)".

**If it didn't work:** If a new password fails the next morning, the re-capture was skipped or failed. Run the status command above, set the passwords again, and re-capture again.

**What usually goes wrong:** Skipping the re-capture. The new passwords work all afternoon and stop at midnight, and the old ones, which the previous chapter holds, come back.

---

## 16.2 Explain how the practice system behaves

**Why:** Trainees who do not know the system resets, or that it shows Cleveland's name, lose work and lose trust in what they see.

**Who:** The chapter and the central support organization — the chapter's trainer, or the central support organization's

**Finish first:**

- step 16.1 Get the chapter's staff onto the shared practice system

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. At the start of the first session, say these four things, in these words or close to them:
   - "This is a training system. Every business, person and email address in it is invented."
   - "You are not expected to save anything. If you do, it is fine: no email is sent, no calendar invitation goes out, and nothing reaches a real mailbox."
   - "Everything you create or change today is gone tomorrow morning, because the system resets itself every night. We finish each walkthrough today."
   - "Every page says Cleveland, because this is Cleveland's training system. Our own system will show our own name."
2. Check every trainee is signed in with a chapter training account, never with their own chapter account. Only the training accounts' addresses lead nowhere.
   *You should see:* Every trainee's portal showing a chapter training account's name.
3. If a session must run over two days, ask the central support organization, before the first evening, to pause that night's reset. They run:
   - ssh root@104.131.45.208 'touch /var/www/espocrm/.sandbox-hold'
   - and the next day, to resume: ssh root@104.131.45.208 'rm /var/www/espocrm/.sandbox-hold'

**Done when:** Everyone being trained has been told two things. The system clears itself out every night, so anything they create during a session is gone the next morning — a session cannot be spread across two days using the same records. And the practice system carries Cleveland's name and Cleveland's example records, so what they see on screen will not say their own chapter's name.

**How to check:** Nobody in the room asks, later, where their saved work went.

**If it didn't work:** If saved work is missing the next morning, the reset ran as designed. Repeat the walkthrough inside one day, or pause the reset as above.

**What usually goes wrong:** A session spread over two days, whose first day's work is gone on the second. Pausing the reset holds the CRM only; the applications' own queue still clears.

---

## 16.3 Train each role

**Why:** Each person should have done their own main task once before doing it for real.

**Who:** The chapter — the trainer, with the central support organization available

**Finish first:**

- step 16.2 Explain how the practice system behaves

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Before any session, sign in at https://cbm-client-intake-svxs3.ondigitalocean.app/ as the Mentor Team chapter training account and open Client Management.
   *You should see:* The account's list of invented clients. If it is empty, the chapter training mentor has not yet been given clients of its own (work list item 6); stop and ask the central support organization.
2. Mentors, 30 to 40 minutes, signed in as the Mentor Team chapter training account:
   - Open Client Management (the address ending /mentorsessions/) and show the status filter and the search box.
   - Open the first client in the list and land on its Overview tab.
   - Open the Sessions tab, open a completed session, and have each trainee read its notes and next steps.
   - Open the Communications tab and show that the email history lives on the record.
   - Open My Mentor Profile (the address ending /mentorprofile/) and show the live preview.
3. Client administrators, signed in as the Client Administration Team chapter training account:
   - Open Client Administration (the address ending /assignments/).
   - Filter the status to Submitted.
   - Have each trainee assign one engagement to a mentor.
   - When the email to the mentor opens, show it and close it without sending.
4. Mentor administrators, signed in as the Mentor Administration Team chapter training account:
   - Open Mentor Administration (the address ending /mentoradmin/).
   - Open one mentor marked Complete and one marked Incomplete, and read the reasons.
   - Have each trainee run Update Mentor Status.
5. Partner managers, signed in as the Partner Management Team chapter training account:
   - Open Partner Management (the address ending /partnersessions/).
   - Open a partner record and have each trainee open its Sessions tab and its Communications tab.
6. Funder managers, signed in as the Sponsor Management Team chapter training account:
   - Open Funder Management (the address ending /sponsorsessions/).
   - Open a funder record and have each trainee open its Contributions tab, its Sessions tab and its Communications tab.
7. The person handling submissions, signed in as the Marketing Admin Team chapter training account:
   - Open Submission Admin (the address ending /ops/).
   - Have the trainee open one submission and read its two status columns.
   *You should see:* Submissions in the queue. The queue is empty unless the central support organization filled it before the session; ask for that at least a day ahead.
8. Analytics: there is no walkthrough for the Analytics Admin Team yet. Show the Analytics page (the address ending /analytics/) and say so.

**Done when:** Every person has been shown the parts of the system their own team uses, and has done each main task once themselves.

**How to check:** Each trainee has done their main task once, and says so.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Two gaps in the walkthroughs. The Submission Admin queue is empty unless filled beforehand. And there is no walkthrough for the Analytics Admin Team. The record names in Cleveland's trainer's guide belong to Cleveland's own training accounts, so the chapter training accounts may show different records.

---

## 16.4 Hand over the written guides

**Why:** After training, people need something to look things up in.

**Who:** The central support organization

**Finish first:**

- step 6.7 Decide where the chapter's help documentation lives

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Send the chapter's first point of contact the address of the chapter's help documentation, from the chapter information form.
2. Send the guide for each role. Each is a file in the software's code repository, with this name:
   - Mentor Administration: mentor-administration.md
   - The mentor directory: mentor-directory.md
   - Submission Admin: submission-admin.md
   - Email: email-management.md
   - Events: event-administration.md
   - Analytics: analytics-guide.md
3. Tell the chapter the guides say Cleveland throughout, because they were written for Cleveland's staff.

**Done when:** The chapter holds the written guides for each role and knows where they live.

**How to check:** The chapter's first point of contact opens the guide for one role without help.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The guides name Cleveland throughout, until the help documentation question is settled. Which of the six are also on a documentation site the chapter can reach is not settled either.

---

## 16.5 Name the chapter's own first point of contact

**Why:** Colleagues need one person to ask first, before raising a request with the central support organization.

**Who:** The chapter

**Finish first:**

- step 16.3 Train each role

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. The chapter emails the central support organization one line: FIRST-POINT-OF-CONTACT-NAME, FIRST-POINT-OF-CONTACT-CHAPTER-EMAIL, is our first point of contact. Choose someone who was in the training.
2. The central support organization adds the name and address to the chapter's entry in the list of watched systems (step 12.5).
   *You should see:* The chapter's entry showing the name and chapter email address.

**Done when:** One person at the chapter is named as the person colleagues ask first, before contacting the central support organization.

**How to check:** The name is on the list of watched systems.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Naming someone who was not in the training.

---

## 16.6 Change the training account passwords

**Why:** People from one chapter must not keep standing access to a system another chapter also uses.

**Who:** The central support organization

**Finish first:**

- step 16.3 Train each role

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. When training ends, repeat the password actions of step 16.1 for all seven chapter training accounts:
   - Make a new password of 20 letters and digits for each account, and store it in the central support organization's vault.
   - Set it on the account at https://crm-test.clevelandbusinessmentors.org, under Administration, then Users.
   - cd ~/Dropbox/Projects/cbm-client-intake
   - uv run python scripts/sandbox/seed_training_data.py --apply
   - ssh root@104.131.45.208 'python3 /usr/local/sbin/reset_crm_sandbox.py baseline --apply'
2. Do not give the new passwords to the chapter.
3. The next morning, open https://cbm-client-intake-svxs3.ondigitalocean.app/ and try one old password.
   *You should see:* The sign-in refused.
4. Add the date the passwords were changed to the chapter's entry in the list of watched systems (step 12.5).

**Done when all of these are true:**

- The chapter training account passwords are changed once training ends.
- The change has survived a nightly reset.
- It is written down when this was done.

**Note:** People from one chapter do not keep standing access to a system another chapter also uses.

**How to check:** The morning after, the old password is refused.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Skipping the re-capture. The old password comes back at midnight, and the chapter keeps its access indefinitely.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.2 | 09-19-26 00:04 | Actions made precise (Doug, 09-19-26): the shared training system's exact addresses, the exact commands to refresh the training data, re-capture and check the fixed copy, and to pause and resume the reset; the words to say to the room; a page and task per role; the file name of each written guide. The training account user names are not known until work list item 6 builds them, and step 16.1 says so. |
| 0.1 | 09-18-26 17:30 | First version as data, converted from the methods for training the chapter's staff (7-Methods-Training.md, version 0.1) with the step list's finishing tests. |
