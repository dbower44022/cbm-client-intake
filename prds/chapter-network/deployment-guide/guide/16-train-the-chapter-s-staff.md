# Stage 16 — Train the chapter's staff

**Version:** 0.3  
**Last Updated:** 09-23-26 13:35  
**Generated from** `steps/stage-16.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

Staff learn the system on invented records before they touch real ones. Training happens on Cleveland's shared training system, which clears itself every night, signed in as the six generic training users Cleveland's own trainers use (ruled 09-14-26 and 09-23-26).

**Who:** The chapter's trainer runs the sessions; the central support organization hands over the training users' sign-in details and the guides.  
**Time:** One session per role. The mentor session is the longest, at 30 to 40 minutes.  
**When this stage is done:** The final checks before going live (stage 17), with staff who know what they are checking.

**Before you start:**

- The staff accounts (stage 14)
- The six training users on the shared training system, which already exist

**Steps in this stage:**

- 16.1 Get the chapter's staff onto the shared practice system
- 16.2 Explain how the practice system behaves
- 16.3 Train each role
- 16.4 Hand over the written guides
- 16.5 Name the chapter's own first point of contact
- 16.6 Record that training has ended

---

## 16.1 Get the chapter's staff onto the shared practice system

**Why:** Trainees need working sign-ins to a system that holds only invented records.

**Who:** The central support organization

**Finish first:**

- step 14.2 Create the staff accounts

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Know the addresses first. The shared training system is Cleveland's test system:
   - The CRM: https://crm-test.clevelandbusinessmentors.org
   - The applications: https://cbm-client-intake-svxs3.ondigitalocean.app/
2. Know the six training users. They are the ones Cleveland's own trainers use, one per role:
   - Mentors: Joe Mentor
   - Client administrators: Kitty Cat
   - Mentor administrators: Mentor Admin
   - Partner managers: Partner Manager
   - Funder managers: Sally Sponsor
   - The person handling submissions: Mark Marketing
3. Get the six training users' sign-in names and passwords from the person who holds them for Cleveland's trainers.
4. Give the chapter's trainer the six sign-in names and passwords by a private route, such as a shared entry in a vault or a one-to-one message. Never send them in an email to a group, and never put them on a public page.
5. Have one person from the chapter open https://cbm-client-intake-svxs3.ondigitalocean.app/ and sign in as one of the six training users.
   *You should see:* The portal, with "(Test)" after the version number in the footer.

**Done when all of these are true:**

- The chapter's trainer holds the sign-in details for the six training users.
- One person from the chapter has signed in once.

**Note:** Ruled 09-14-26: chapters train on the existing test system rather than on their own live system or on a practice system built for them. Ruled 09-23-26: they sign in as the six generic training users Cleveland's own trainers use, never with accounts of their own, and the passwords are not changed for each chapter.

**How to check:** Someone from the chapter signs in as a training user, and the footer reads "(Test)".

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A trainee signs in with their own chapter account instead of a training user. Their own account's email address is real, so a practice email could reach a real person.

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
2. Check every trainee is signed in as one of the six training users, never with their own chapter account. Only the training users' addresses lead nowhere.
   *You should see:* Every trainee's portal showing a training user's name.
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

1. Before any session, sign in at https://cbm-client-intake-svxs3.ondigitalocean.app/ as the training user Joe Mentor and open Client Management.
   *You should see:* Seven invented clients. If the list is empty or short, stop and ask the central support organization.
2. Mentors, 30 to 40 minutes, signed in as the training user Joe Mentor:
   - Open Client Management (the address ending /mentorsessions/) and show the status filter and the search box.
   - Open the first client in the list and land on its Overview tab.
   - Open the Sessions tab, open a completed session, and have each trainee read its notes and next steps.
   - Open the Communications tab and show that the email history lives on the record.
   - Open My Mentor Profile (the address ending /mentorprofile/) and show the live preview.
3. Client administrators, signed in as the training user Kitty Cat:
   - Open Client Administration (the address ending /assignments/).
   - Filter the status to Submitted.
   - Have each trainee assign one engagement to a mentor.
   - When the email to the mentor opens, show it and close it without sending.
4. Mentor administrators, signed in as the training user Mentor Admin:
   - Open Mentor Administration (the address ending /mentoradmin/).
   - Open one mentor marked Complete and one marked Incomplete, and read the reasons.
   - Have each trainee run Update Mentor Status.
5. Partner managers, signed in as the training user Partner Manager:
   - Open Partner Management (the address ending /partnersessions/).
   - Open a partner record and have each trainee open its Sessions tab and its Communications tab.
6. Funder managers, signed in as the training user Sally Sponsor:
   - Open Funder Management (the address ending /sponsorsessions/).
   - Open a funder record and have each trainee open its Contributions tab, its Sessions tab and its Communications tab.
7. The person handling submissions, signed in as the training user Mark Marketing:
   - Open Submission Admin (the address ending /ops/).
   - Have the trainee open one submission and read its two status columns.
   *You should see:* Submissions in the queue. The queue is empty unless the central support organization filled it before the session; ask for that at least a day ahead.
8. Analytics: skip it. None of the six training users is in the Analytics Admin Team, so none can open the Analytics page.

**Done when:** Every person has been shown the parts of the system their own team uses, and has done each main task once themselves.

**How to check:** Each trainee has done their main task once, and says so.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Two gaps in the walkthroughs. The Submission Admin queue is empty unless filled beforehand. And there is no analytics training, because no training user can open the Analytics page.

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

## 16.6 Record that training has ended

**Why:** The training users' passwords stay unchanged after a chapter trains, so a written record of who holds them is the only account of it.

**Who:** The central support organization

**Finish first:**

- step 16.3 Train each role

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. When training ends, add two things to the chapter's entry in the list of watched systems (step 12.5):
   - The date training ended
   - That the chapter's staff hold the six training users' passwords
   *You should see:* Both lines in the chapter's entry.

**Done when:** The date training ended, and that the chapter holds the training passwords, are written in the chapter's entry.

**Note:** Ruled 09-23-26: the training users' passwords are not changed after each chapter. The shared training system holds only invented records and sends no real email, so a former trainee keeping access exposes nothing real.

**How to check:** The chapter's entry in the list of watched systems shows the date.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.3 | 09-23-26 13:35 | Chapters train as the six generic training users Cleveland's trainers use, and the passwords are not changed for each chapter (Doug, 09-23-26), reversing the 09-18-26 ruling for separate chapter training accounts. Step 16.1 now hands over the six existing sign-ins; step 16.6 records that training ended instead of changing passwords; the walkthroughs name the training users; analytics is skipped, because no training user can open it. |
| 0.2 | 09-19-26 00:04 | Actions made precise (Doug, 09-19-26): the shared training system's exact addresses, the exact commands to refresh the training data, re-capture and check the fixed copy, and to pause and resume the reset; the words to say to the room; a page and task per role; the file name of each written guide. The training account user names are not known until work list item 6 builds them, and step 16.1 says so. |
| 0.1 | 09-18-26 17:30 | First version as data, converted from the methods for training the chapter's staff (7-Methods-Training.md, version 0.1) with the step list's finishing tests. |
