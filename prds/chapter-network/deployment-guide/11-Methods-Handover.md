# New Chapter Deployment Guide — Methods for the Handover

**Document:** The written-out steps for one stage — handing over and starting normal
support (stage 18)
**Version:** 0.1
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-18-26 01:50

---

## What this is

The last stage. It moves the chapter from being set up to being supported, and it
proves the chapter can reach everything it owns without help.

It is written from the network's settled rulings (`DECISIONS.md`), the governance
and leaving design (`governance-and-exit.md`), and the release train
(`phase-2-release-train.md`). Most of what this stage hands over does not exist yet:
there is no support contact, no change-request route, no emergency access procedure
and no leaving kit. Each step says so plainly rather than describing a process that
is not there.

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
chapter, and four of its seven steps depend on things not yet built or decided.

---

### 18.1 Publish how to get help

**Done when:** the chapter has in writing how to contact the central support
organization, what counts as urgent, and how quickly to expect an answer.

**Who:** central support organization.

**First:** the agreement is signed (step 2.6), and the chapter's first point of
contact is named (step 16.5).

**How to do it today:** there is no support address, no definition of urgent and no
published response time. Until there is, write down for this chapter: one email
address to use, the name of the person who answers it, and the promise made in the
agreement. Separate the two kinds of request from the start:

- **Everyday requests**: add a person, change someone's team, reset a password.
  These need an administrator and must be answered quickly. Several are already
  self-service. Mentor Administration creates mentor logins itself, and "Forgot
  your password?" on the sign-in page resets a password without anyone's help.
- **Change requests**: anything that would change the software. These go through
  step 18.2.

**How it will be done later:** one shared place to raise a request, visible to every
member chapter, as `governance-and-exit.md` proposes.

**How you know it worked:** the chapter's first point of contact sends a test
request and gets an answer within the time promised.

**What goes wrong:** everyday requests queued behind change requests. A new
volunteer who waits a week for an account is how a chapter starts asking for an
administrator account of its own.

**Status:** not yet tried. The support route does not exist.

---

### 18.2 Explain how to ask for a change

**Done when:** the chapter knows where to send a request that would change the
software for everyone, who decides, and how often those decisions are made.

**Who:** central support organization.

**First:** step 18.1.

**How to do it today:** explain the rule first: every chapter runs the same software.
A requested change is made for every chapter, or it is not made. There is no third
answer. Then give the chapter the place to send a change request, and say who
decides and when.

None of those three exists yet. `governance-and-exit.md` proposes one shared place
for requests and a decision forum of the funding member chapters. `DECISIONS.md`
proposal 3 suggests the forum meets monthly. Neither is ruled. Until they are, say
so, and record the request with the central support organization directly.

**How it will be done later:** the shared request place and the decision forum,
once ruled.

**How you know it worked:** the chapter can say, without looking it up, that a change
is for everyone or not at all.

**What goes wrong:** a request that is "only for us". The answer is always the same:
it becomes a change for everyone, or it does not happen. Granting one exception is
how the rule ends.

**Status:** not yet tried. The request route and the forum are proposals, not
rulings.

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
Passwords live in the secrets store (step 8.8).

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

**How you know it worked:** the chapter can list the four parts, and knows which of
them depend on its choice of Google Workspace branch.

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

**1. Four steps depend on things that do not exist.** Step 18.1 needs a support
route and a promised response time. Step 18.2 needs a place to send change requests
and a decision forum, both only proposed. Step 18.5 needs the emergency access
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
| 0.1 | 09-18-26 01:50 | First draft of the methods for handing over and starting normal support. Written from the network's rulings, the governance and leaving design, and the release train. Two findings: four steps depend on things that do not exist, and the leaving kit has no owner on the work list. |
