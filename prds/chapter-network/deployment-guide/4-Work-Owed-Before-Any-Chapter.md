# Work Owed Before Any Chapter Can Follow the Guide

**Document:** Things the central support organization has to build, decide or write
before the New Chapter Deployment Guide can actually be followed
**Version:** 0.4
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-18-26 01:55

---

## Why this document exists

Reviewing the fourteen steps added after the completeness checks turned up
something worth separating out. Some of those steps are ordinary work a chapter
does. Others quietly depend on something that does not exist yet, and no amount of
good writing in the guide will make them possible.

Those dependencies are listed here rather than left inside the step they block,
because they are not writing tasks. Somebody has to build or decide each one, and
none of them can be done by a chapter.

Each item says what is missing, which step cannot be completed without it, and how
big the work looks.

---

## 1. A place to keep secrets

**What is missing.** There is no shared store for the six passwords and keys each
chapter's system needs. Today they live in files on one person's computer, and
regenerating one of those files scrambles the passwords inside it into something
unreadable.

**What it blocks.** Putting the chapter's secrets into the store (step 8.8).
Recording who holds the server command line key (step 9.4). Loading the secrets at
deployment (step 11.3). In practice it blocks the whole of stages 9, 10 and 11
being done by anyone other than the one person holding the files.

**Size.** Real work, and already named in the existing planning documents as the
single largest reason one of the later phases exists. It is also the support
organization's own single point of failure, so it is worth doing whether or not a
second chapter ever appears.

---

## 2. A published statement of what the standard is

**What is missing.** No document says which CRM version a new chapter installs,
which versions of the two paid add-on products, or which release of the standard
configuration is current.

**What it blocks.** Obtaining the standard's version numbers (step 9.1), and
therefore installing the CRM at the right version (step 9.3), installing the add-on
products (step 9.7), and the final check that the CRM matches the standard
(step 9.20).

**Size.** Small to write, but it needs a decision first. The August practice build
found that the deployment tool installs whatever version is current, which would
start a new chapter a major version ahead of Cleveland. Somebody has to decide
whether chapters are pinned to Cleveland's version, or Cleveland moves up.

---

## 3. A decision on duplicate checking, saved views and automated rules

**What is missing.** Nobody has ever examined these settings on either existing
system. The August practice build recorded them as "not examined" and said so
plainly.

**What it blocks.** Applying them on a new chapter's CRM (step 9.16).

**Size.** An investigation, then a decision. It may be larger than it looks:
duplicate checking is not only a convenience for staff, it is something the intake
software's behaviour depends on, and that dependency has never been verified in
either direction.

---

## 4. A starter colour file and a logo specification

**What is missing.** Colours are the only visual difference between chapters, and
they are supplied as a small stylesheet the software loads. There is no template
for a chapter to start from, and no written specification for the logo image the
CRM displays — what file type, what size, where it goes.

**What it blocks.** Choosing the chapter's colours and publishing the colour file
(step 6.5) and producing the logo image (step 6.6).

**Size.** Half a day. The colour names already exist in the software; the template
is a file listing them with Cleveland's values commented out.

---

## 5. A written emergency access procedure

**What is missing.** The architecture says neither side can lock the other out, and
that a chapter can always get in through the server it owns. No procedure describes
how.

**What it blocks.** Proving the chapter can reach its own accounts unaided
(step 18.5), which is the step that turns that promise into something demonstrated
rather than stated.

**Size.** Small to write, but it has to be walked once to be worth anything — the
same objection the existing documents already make about the leaving procedure.

---

## 6. Access to the shared practice system

**Ruled 09-14-26: chapters train on the existing test system.** Not on their own
live system, and not on a practice system built for each of them. That closes most
of this item — the machine already exists, it already clears itself out nightly,
and it already holds example records to practise on.

**What is still missing.** Three things.

A set of shared chapter training accounts (ruled 09-18-26), separate from the six
Cleveland's own trainers use. This is the one piece of real work: one account per
team, each with an `@sandbox.cbmentors.org` address that leads nowhere; added to the
training data script so they are rebuilt with everything else; a mentor profile for
the mentor account with its own invented clients; then one re-capture of the
training system's fixed copy. Personal accounts were ruled out because the system
restores its user accounts every night, and because a personal account puts a real
mailbox behind the Send button.

A note to trainees explaining two things they will otherwise find confusing: the
system clears itself out every night, so nothing they create survives to the next
morning; and it carries Cleveland's name and Cleveland's example records, so it
will not look like their own chapter.

A decision about when this stops being the answer. The existing test system already
does three jobs — it is the review gate before anything reaches production, the
training sandbox, and the system a release is tested on. Training chapters makes it
a fourth, and it makes one chapter's machine serve the whole network, which is the
shape the architecture's first ruling exists to avoid. The existing planning
documents already reached the same conclusion about using that machine to test
releases, and recommended moving to a machine the central support organization owns
once a second chapter is in sight. The same answer applies here: use it now, move
it later, and decide at the same moment.

**What it blocks.** Getting chapter staff onto the practice system (step 16.1) and
changing the passwords afterwards (step 16.6). Both are written; neither can be done
until the chapter training accounts exist.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.4 | 09-18-26 01:55 | Item 6 rewritten after Doug ruled on 09-18-26 that chapter staff train with shared training accounts set up specifically for chapter training. Building those accounts is now the item's one piece of real work, and it blocks steps 16.1 and 16.6. |
| 0.3 | 09-15-26 00:22 | No items changed. Noted here for the record: the trial chapter stays running with testing the setup steps as its reason (Doug, 09-15-26), which gives four of the five remaining items somewhere to be tried before a real chapter meets them. |
| 0.2 | 09-14-26 18:09 | Item 6 rewritten after Doug ruled that chapters train on the existing test system. It is no longer a build — what remains is an account rule, a note for trainees, and a decision about when that machine stops being the answer. Five items now block work; this one blocks nothing. |
| 0.1 | 09-14-26 17:51 | First draft. Six items, found by reviewing the fourteen steps added after the completeness checks were run against the step list. |
