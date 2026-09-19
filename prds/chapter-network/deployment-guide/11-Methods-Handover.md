# New Chapter Deployment Guide — Methods for the Handover

**Document:** The written-out steps for one stage — handing over and starting normal
support (stage 18)
**Version:** 0.5
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-18-26 14:30

---

## What this is

The last stage. It moves the chapter from being set up to being supported, and it
proves the chapter can reach everything it owns without help.

It is written from the network's settled rulings (`DECISIONS.md`), the governance
and leaving design (`governance-and-exit.md`), and the release train
(`phase-2-release-train.md`). Some of what this stage hands over does not exist yet:
no emergency access procedure and no leaving kit. Requests
have a home in the ClickUp system the support team manages, and the central
committee reviews them every two weeks (09-18-26). Each step says plainly what is missing
rather than describing a process that is not there.

Each step carries the same eight headings as the other methods documents.

**Why this stage matters more than its length suggests.** The central support
organization holds the only administrator accounts on every chapter's CRM (ruling 6).
That is what keeps every chapter's software identical (ruling 4). The cost is that
every change lands on the central support organization's desk. If asking for help
or for a change is slow, chapters will ask for an administrator account of their own.
The first one granted ends the rule that every chapter runs the same software.
Steps 18.1 and 18.2 are where that is won or lost.

---

# Stage 18 — Hand over and start normal support

**Stage status: not yet tried.** Nothing in this stage has been done for any
chapter, and two of its seven steps depend on things not yet built: the emergency access
procedure and the leaving kit.

---

### 18.1 Publish how to get help

**Done when:** the chapter has in writing how to raise a request, that no request is
treated as urgent, that everyday requests are handled as they arrive, and that no
response time is committed (ruled 09-18-26).

**Who:** central support organization.

**First:** the agreement is signed (step 2.6), and the chapter's first point of
contact is named (step 16.5).

**How to do it today:** every request goes into the ClickUp system the support team
uses for new feature requests, defect reports and support requests (Doug,
09-18-26). The whole support team manages it, so a request never waits on one
person. Give the chapter's first point of contact access to it, and show them how to
raise each of the three kinds and how to follow one to its answer.

Tell the chapter plainly that there is no committed response time (ruled 09-18-26).
Feature requests and defects are reviewed and scheduled by the central committee,
which meets every two weeks. No request is treated as urgent (ruled 09-18-26).
Separate the kinds of request from the start:

- **Everyday requests**: add a person, change someone's team, reset a password.
  These need an administrator, and the support team handles them as they arrive
  rather than holding them for the committee (ruled 09-18-26). Several are already
  self-service. Mentor Administration creates mentor logins itself, and "Forgot
  your password?" on the sign-in page resets a password without anyone's help.
- **Defect reports**: something that worked and has stopped, or does the wrong
  thing. Include the version number from the page footer.
- **New feature requests**: anything that would change the software. These go
  through step 18.2.

**How it will be done later:** unchanged. The ClickUp system is the method.

**How you know it worked:** the chapter's first point of contact raises a test
request in the ClickUp system and sees it acknowledged.

**What goes wrong:** everyday requests queued behind feature requests and defects. A
new volunteer who waits for the next committee meeting to get an account is how a
chapter starts asking for an administrator account of its own. That is why
everyday requests are handled as they arrive (confirmed by Doug, 09-18-26).

**Status:** not yet tried. Every part of this step is now ruled. Chapter access to
the ClickUp system still has to be set up (work list item 8).

---

### 18.2 Explain how to ask for a change

**Done when:** the chapter knows where to send a request that would change the
software for everyone, who decides, and how often those decisions are made. The
central committee decides, every two weeks (ruled 09-18-26).

**Who:** central support organization.

**First:** step 18.1.

**How to do it today:** explain the rule first: every chapter runs the same software.
A requested change is made for every chapter, or it is not made. There is no third
answer. Then show the chapter how to raise a new feature request in the ClickUp
system (step 18.1), where the support team manages it.

The central committee reviews and schedules feature requests and defects every two
weeks (ruled 09-18-26). Tell the chapter that, and that a feature request is
answered "for every chapter" or "no". A request accepted is scheduled into a weekly
release (step 18.3).

**How it will be done later:** unchanged.

**How you know it worked:** the chapter can say, without looking it up, that a change
is for everyone or not at all.

**What goes wrong:** a request that is "only for us". The answer is always the same:
it becomes a change for everyone, or it does not happen. Granting one exception is
how the rule ends.

**Status:** not yet tried. The route and the decision rule are both settled.

---

### 18.3 Explain the release schedule

**Done when:** the chapter knows software updates arrive automatically on a weekly
schedule, roughly when, and what to do if something looks wrong afterwards.

**Who:** central support organization.

**First:** the application's update policy is set to Latest Stable (step 11.8).

**How to do it today:** tell the chapter three things.

1. **When.** A new release is named each week, at the Sunday 17:00 UTC slot (ruled
   2026-08-26). The chapter's application takes each named release by itself. That
   is what Latest Stable means.
2. **What changes.** Every chapter moves to the same release at the same time. A
   chapter never runs a different version from the others.
3. **What to do if something looks wrong on Monday.** First refresh the page
   properly, because a browser can keep the old version of a page after an update.
   Then report it through step 18.1. The page footer shows the version number;
   include it.

A fix for a security problem can arrive outside the weekly slot. It still passes
through the central support organization's own test system first.

**How it will be done later:** the fleet console shows each chapter its current
release and the date of the next one.

**How you know it worked:** the chapter's first point of contact can find the version
number in the footer.

**What goes wrong:** the weekly slot being missed. It has happened: the 09-06-26
slot was missed and the 09-13-26 release ran late. A late release is harmless to a
chapter. A chapter told "every Sunday" that sees nothing change should be told why.

**Status:** not yet tried with a chapter. The trial chapter follows Latest Stable
and has updated itself on a release.

---

### 18.4 Hand over the account and access list

**Done when:** the chapter holds the list of every account, who has the top-level
sign-in, and who else has access — and a named chapter officer can reach every one
of them.

**Who:** central support organization prepares it; the chapter keeps it.

**First:** the list of accounts written in step 5.7, and every stage that created an
account since.

**How to do it today:** bring the list from step 5.7 up to date. It covers the domain
registrar account, the Google Workspace account, the hosting account, the video
meeting account if there is one, the CRM's administrator accounts, and the
documentation site if the chapter has its own. For each account, write who holds the
top-level sign-in and who else has access. Never write a password on the list.
Passwords and recovery codes live in the chapter's Proton Pass Operations vault
(step 2.7).

**How it will be done later:** the fleet console produces the list from what it
created.

**How you know it worked:** the named chapter officer reads the list and confirms
every account on it is one they recognise.

**What goes wrong:** an account whose top-level sign-in is a volunteer's personal
email address. When that volunteer leaves, the chapter loses the account. Step 4.14
moves the domain registrar account for this reason. Check every other account the
same way.

**Status:** not yet tried.

---

### 18.5 Confirm the chapter can get in without the central support organization

**Done when:** a named chapter officer has demonstrated, not merely been told, that
they can reach the server, the hosting account, the Google Workspace account and the
domain registrar account on their own. The agreement says neither side can lock the
other out; this is the step that makes that true rather than stated.

**Who:** the chapter officer does it; the central support organization watches.

**First:** step 18.4, and a written emergency access procedure, which does not exist
(work list item 5).

**How to do it today:** the three accounts are straightforward. The officer signs in
to the hosting account, the Google Workspace admin console and the domain registrar
account, each with their own sign-in, while someone watches.

The server is the hard one. The chapter's route into its own CRM, if the central
support organization ever stopped working, is through the server it owns. No
procedure describes how. Until one is written, this step cannot be completed.

**How it will be done later:** unchanged. A person has to do it once, by hand, with
someone watching.

**How you know it worked:** the officer has signed in to all four, and the date is
recorded on the chapter's entry in the list of watched systems (step 12.5).

**What goes wrong:** being told instead of shown. An access route nobody has used is a
promise, not a capability.

**Status:** not yet tried. Blocked on the emergency access procedure.

---

### 18.6 Confirm the leaving terms in practice

**Done when:** the chapter has been shown exactly what it would receive if it left,
and who produces each part.

**Who:** central support organization.

**First:** the leaving terms are agreed (step 2.5).

**How to do it today:** walk the chapter through the leaving kit that
`governance-and-exit.md` defines, part by part.

- **The CRM.** The chapter already owns the server, so the CRM stays with the
  chapter.
- **An export of the application's own database.** This matters more than it
  sounds. Some of the chapter's records live only there and were never written to
  the CRM. They include the discussion notes on partner and funder records, the
  history of every public form submission and the replies to it, and the chapter's
  own analytics pages. Keeping the CRM is not keeping all the data.
- **The documents on the shared drive.** A chapter that brought its own Google
  Workspace keeps them. A chapter whose Google Workspace was provided by the central
  support organization has its mail, documents and calendars in someone else's
  account. It can get them back, but only by a transfer.
- **A licence to keep using the last version it received.**

Nobody has produced a leaving kit yet. `governance-and-exit.md` says the leaving
procedure must be rehearsed once before it can be relied on, and it has not been.

**How it will be done later:** the leaving kit is produced by a script, and rehearsed
once on the shared training system.

**How you know it worked:** the chapter can list the four parts. (Before 09-18-26 a
chapter could have had a centrally provided Google Workspace; that option is gone.)

**What goes wrong:** a chapter that chose a Google Workspace provided by the central
support organization, finding out only now what leaving costs. That choice is
explained before it is made (step 4.1). This step only confirms it.

**Status:** not yet tried. The leaving kit does not exist.

---

### 18.7 Set the first review date

**Done when:** a date is booked to review how the first months have gone.

**Who:** the chapter and the central support organization together.

**First:** steps 18.1 to 18.6.

**How to do it today:** book a meeting about three months out. Put it in both
organizations' calendars. At it, go through the support requests raised, any
change requests and their answers, whether a restore test has been run since
go-live, and whether the account list from step 18.4 is still right.

**How it will be done later:** unchanged.

**How you know it worked:** the meeting is in both calendars.

**What goes wrong:** nothing known yet.

**Status:** not yet tried.

---

## What writing this stage found

**1. Four steps depend on things that do not exist.** Step 18.1 needs a promised
response time and a definition of urgent. Since ruled on 09-18-26: requests go into
the ClickUp system, the central committee decides feature requests and defects every
two weeks, no response time is committed, and nothing is treated as urgent. Only
chapter access to the ClickUp system is left to set up. Step 18.5 needs the emergency access
procedure (work list item 5). Step 18.6 needs a leaving kit, never produced or
rehearsed. The first three are organizational decisions rather than builds. They
should be added to the work list as items of their own.

**2. The leaving kit belongs on the work list.** `governance-and-exit.md` defines
the kit and requires one rehearsal, but no work list item owns it. It includes an
export of the application's own database. That export is the part most easily
forgotten, because the CRM looks like the whole system and is not.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.5 | 09-18-26 14:30 | Step 18.4 points to the chapter's Proton Pass vault (Doug, 09-18-26). |
| 0.4 | 09-18-26 13:50 | Step 18.1 finished: nothing is treated as urgent, and everyday requests are handled as they arrive (Doug, 09-18-26). Stage status updated: two steps, not four, now wait on something unbuilt. |
| 0.3 | 09-18-26 13:45 | Steps 18.1 and 18.2 updated: the central committee reviews and schedules features and defects every two weeks, and there is no committed response time (Doug, 09-18-26). Step 18.1 now warns that everyday requests must not wait for the committee. |
| 0.2 | 09-18-26 13:40 | Steps 18.1 and 18.2 rewritten around the ClickUp system that takes new feature requests, defect reports and support requests, managed by the entire support team (Doug, 09-18-26). Defect reports added as a third kind of request. Still open: the response time, what counts as urgent, and who decides feature requests. |
| 0.1 | 09-18-26 01:50 | First draft of the methods for handing over and starting normal support. Written from the network's rulings, the governance and leaving design, and the release train. Two findings: four steps depend on things that do not exist, and the leaving kit has no owner on the work list. |
