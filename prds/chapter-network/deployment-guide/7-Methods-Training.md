# New Chapter Deployment Guide — Methods for Training the Chapter's Staff

**Document:** The written-out steps for one stage — training the chapter's staff
(stage 16)
**Version:** 0.1
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-18-26 01:55

---

## What this is

The stage that shows the chapter's staff how to use the system before they use it
on real records. It is written from Cleveland's own training material: the trainer's
guide (`training-guide.md`), the record-by-record reference behind it
(`demo-records.md`), and the runbook for the training system's nightly reset
(`SANDBOX-RESET.md`).

Two rulings shape it:

- **Chapters train on the shared training system** (ruled 09-14-26). The shared
  training system is Cleveland's existing test system. It clears itself out every
  night, and it holds invented records to practise on.
- **Chapter staff sign in with shared training accounts set up specifically for
  chapter training** (ruled 09-18-26). They never use their own accounts on the
  shared training system. These chapter training accounts are separate from the
  six accounts Cleveland's own trainers use. That means changing their passwords
  never disturbs Cleveland.

Each step carries the same eight headings as the other methods documents.

**Nothing in this stage has been done with a chapter.** The walkthroughs are
Cleveland's own. The chapter training accounts do not exist yet. That is set out
at the end, under "What writing this stage found".

---

# Stage 16 — Train the chapter's staff

**Stage status: not yet tried.**

**One fact about the shared training system governs every step below.** The nightly
reset restores user accounts and passwords along with the records. A training
account created during the day, or a password changed during the day, goes back to
its old state at midnight. The only way to make an account change stick is to
re-capture the fixed copy the system restores from. That is called a re-baseline,
and it is done by the central support organization on the server, as set out in
`SANDBOX-RESET.md` under "Re-baseline".

---

### 16.1 Get the chapter's staff onto the shared practice system

**Done when:** the chapter's trainer holds the sign-in details for the chapter
training accounts, the passwords were set fresh for this chapter, and one person
from the chapter has signed in once.

**Who:** central support organization.

**First:** the chapter training accounts exist on the shared training system. They
do not exist yet. See "What writing this stage found".

**How to do it today:**

1. Set a new password on each chapter training account.
2. Re-baseline the shared training system, so the new passwords survive the nightly
   reset. Run the training data script first, in the same sitting, as
   `SANDBOX-RESET.md` requires.
3. Give the passwords to the chapter's trainer by a private route, never in an
   email to a group.

There is one chapter training account for each team that opens a page in the
applications. Each carries an email address ending `@sandbox.cbmentors.org`, which
leads nowhere on purpose. So nothing a trainee sends can reach a real person.

**How it will be done later:** the fleet console sets and hands out the passwords
in one action.

**How you know it worked:** the next morning, after one nightly reset, someone from
the chapter signs in with the new password. The footer after the version number
reads `(Test)`.

**What goes wrong:** skipping the re-baseline. The new passwords work all afternoon
and stop working at midnight. The trainees then find the old passwords are in force,
which the previous chapter still holds.

**Status:** not yet tried.

---

### 16.2 Explain how the practice system behaves

**Done when:** everyone being trained has been told two things. The system clears
itself out every night, so anything created in a session is gone the next morning.
And it carries Cleveland's name and Cleveland's invented records, so what they see
will not say their own chapter's name.

**Who:** the chapter's trainer, or the central support organization's.

**First:** step 16.1.

**How to do it today:** at the start of the first session, say it out loud. Use the
three points in the "What to tell the room" section of `training-guide.md`. It is a
training system and every record is invented. Nobody is expected to save anything.
And if someone does save something, nothing can escape. Then add the chapter's
own point: the name on every page is Cleveland's, and their own system will show
their own name.

**How it will be done later:** unchanged.

**How you know it worked:** nobody in the room asks, later, where their saved work
went.

**What goes wrong:** a session spread over two days. Whatever the first day
created is gone on the second. Plan each walkthrough to finish inside one day, or
ask the central support organization to pause that night's reset.

**Status:** not yet tried with a chapter. The three points come from Cleveland's
own trainer's guide.

---

### 16.3 Train each role

**Done when:** every person has been shown the parts of the system their own team
uses, and has done each main task once themselves.

**Who:** the chapter's trainer, with the central support organization available.

**First:** step 16.2.

**How to do it today:** follow the walkthroughs in `training-guide.md`, one per
role. Each names the account to sign in as, the record to open and what to point
out. The mentor walkthrough is the longest, at 30 to 40 minutes. Use the chapter
training account for each role in place of Cleveland's own training account.

Each trainee does the main task for their role once, with their own hands.

- A client administrator assigns one engagement.
- A mentor opens a session and reads its notes.
- A mentor administrator runs the "Update Mentor Status" check.
- Partner and funder managers open a record's Sessions and Communications tabs.
- The person handling submissions opens Submission Admin.

**How it will be done later:** unchanged.

**How you know it worked:** each trainee has done their main task once, and says
so.

**What goes wrong:** two known gaps in the walkthroughs.

The first: the Submission Admin queue on the shared training system is empty. That
walkthrough shows the screen, not the work. Ask for the queue to be filled before
the session. The training data script can seed it.

The second: there is no walkthrough for the Analytics Admin Team.

**Status:** not yet tried with a chapter.

---

### 16.4 Hand over the written guides

**Done when:** the chapter holds the written guides for each role and knows where
they live.

**Who:** central support organization.

**First:** the chapter's help documentation decision (step 6.7).

**How to do it today:** the written guides are in the software's code repository,
and several are published on Cleveland's documentation site. Give the chapter the
link to the documentation site, and name the guide for each role:

- Mentor Administration: `mentor-administration.md`
- the mentor directory: `mentor-directory.md`
- Submission Admin: `submission-admin.md`
- email: `email-management.md`
- events: `event-administration.md`
- analytics: `analytics-guide.md`

**How it will be done later:** depends on the open question about whether each
chapter publishes its own help documentation or shares one site.

**How you know it worked:** the chapter's first point of contact (step 16.5) opens
the guide for one role without help.

**What goes wrong:** the guides say Cleveland throughout. They were written for
Cleveland's staff. Until the documentation question is settled, tell the chapter so
when handing them over.

**Status:** not yet tried.

---

### 16.5 Name the chapter's own first point of contact

**Done when:** one person at the chapter is named as the person colleagues ask
first, before contacting the central support organization.

**Who:** the chapter.

**First:** step 16.3.

**How to do it today:** the chapter names the person in writing. The central
support organization records the name on the chapter's entry in the list of watched
systems (step 12.5).

**How it will be done later:** unchanged.

**How you know it worked:** the name is on the list.

**What goes wrong:** naming someone who was not in the training.

**Status:** not yet tried.

---

### 16.6 Remove the training accounts

**Done when:** the chapter training account passwords are changed once training
ends, the change has survived a nightly reset, and it is written down when this was
done.

**Who:** central support organization.

**First:** training ends.

**How to do it today:** the accounts are not removed, because the next chapter uses
the same ones. Set a new password on each chapter training account, then re-baseline
the shared training system, exactly as in step 16.1. Record the date on the
chapter's entry in the list of watched systems.

**How it will be done later:** the fleet console changes the passwords at the end of
training in one action.

**How you know it worked:** the next morning, the old password is refused.

**What goes wrong:** the same as step 16.1. Without the re-baseline, the old
password comes back at midnight, and the chapter keeps its access indefinitely.

**Status:** not yet tried.

---

## What writing this stage found

**1. User accounts on the shared training system reset every night.** The step list
assumed a chapter's staff would each get an account and have it removed afterwards.
On a system that restores its user accounts every night, both halves need a
re-baseline, and a personal account also carries a real mailbox behind the Send
button. Ruled 09-18-26: shared chapter training accounts instead. Steps 16.1 and
16.6 are rewritten to match, in this document and in the step list.

**2. The chapter training accounts do not exist.** Building them is work on the
shared training system, and it belongs on the work list (item 6):

- one account per team, each with an `@sandbox.cbmentors.org` address;
- added to the training data script so they are rebuilt with everything else;
- a mentor profile for the mentor account, with its own invented clients, because a
  mentor with no clients has nothing to train on;
- then one re-baseline.

**3. Two gaps in Cleveland's walkthroughs.** The Submission Admin queue is empty, and
there is no Analytics walkthrough. Both matter for Cleveland's own training as well.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 09-18-26 01:55 | First draft of the methods for training the chapter's staff. Written from Cleveland's trainer's guide, the demo records reference and the training system's reset runbook. Written for shared chapter training accounts, set up specifically for chapter training and separate from Cleveland's own (Doug, 09-18-26). Three findings: user accounts on the shared training system reset every night, the chapter training accounts do not exist yet, and Cleveland's walkthroughs have two gaps. |
