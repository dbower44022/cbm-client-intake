# Work Owed Before Any Chapter Can Follow the Guide

**Document:** Things the central support organization has to build, decide or write
before the New Chapter Deployment Guide can actually be followed
**Version:** 0.15
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-23-26 20:40

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

## Where each item stands for Boston (09-23-26)

Boston is the first real chapter, and it is being built now. So every open item
is one of three things: it needs an answer before Boston's build reaches it, Boston
builds around it with a known workaround, or it can wait until after the build.
Each line was checked against the code and the step files on 09-23-26.

**Needs an answer before Boston's build reaches it:**

1. ~~**Item 2 — which CRM version Boston installs.**~~ **Ruled 09-23-26 (Doug):**
   Boston runs the current release CRMBuilder installs, and Cleveland moves up to
   it later (`TASKS.md` C1). Nothing is left that needs an answer before the
   build.

**Boston builds around it, with a known workaround:**

2. **Item 15 — the CRM applier.** Boston is built the way the August trial was:
   configuration files copied off Cleveland's test system, then the trial script
   `apply_api_half.py`. The decision date (09-19-26, `TASKS.md` A1) has passed,
   and nothing in this repository records what happened on it.
3. **Item 16 — the settings generator.** The trial script `render_spec.py` now
   covers the Google and Zoom settings and reads the chapter information form,
   which is a web page since 09-23-26. Two gaps remain: it still asks for a
   development database, which step 11.4 converts by hand, and it reads secrets
   from a file rather than the vault.
4. **Item 1 — the central support organization's own vault.** Boston keeps its
   own secrets in its own vault (step 2.7). The central support organization's
   secrets are still on one laptop.
5. **Item 18 — five event email templates.** The conformance check at step 9.9
   will report these five as a difference for Boston, as it did for the trial
   chapter. The difference is known and accepted.

**Can wait until after Boston's build:**

6. ~~**Item 6 — the chapter training accounts.**~~ **Ruled 09-23-26 (Doug):** no
   new accounts; chapters use the existing generic training users, and their
   passwords are not changed after each chapter. Stage 16 is rewritten to match.
7. **Item 12 — loading existing records.** Needed only if Boston has records to
   bring in (step 15.4).
8. **Item 8 — ClickUp access for chapter people.** Needed before Boston's
   handover (step 18.1).
9. **Item 19 — CRM field labels say "CBM".** Boston's staff will see Cleveland's
   initials. On 09-23-26 Doug ruled that Boston launches with "CBM" in the
   application's own text, to be swept in a later release (`TASKS.md` G1 item
   11). That ruling does not cover the CRM labels, but the same answer is the
   likely one.
10. **Items 4 and 11 — colours and the logo.** The colour file is now written
    from four answers on the chapter information form (09-23-26). Still missing:
    the logo specification (item 4), and the public events page, which still
    shows Cleveland's navy and gold (item 11). Item 11 matters only if Boston
    sends its events address to that page.
11. **Item 3 — duplicate checking, saved views and automated rules.** Stage 9
    lists this as not possible yet, and Boston is built without it, as the trial
    chapter was.
12. **Item 17 — the time zone.** Boston is in Eastern time, so this does not
    affect Boston.
13. **Items 5, 7, 9, 10 and 13** — the emergency access procedure, the standard
    agreement, the leaving kit, the public mentor directory page and the plain
    list of personal information. None is reached during the build.

---

## Implementation first (09-18-26 ranking, kept for the record)

Doug, 09-18-26: the technical steps that build a chapter's system come first. The
legal and administrative items (7, 8, 9, 13 and 14) wait.

The technical holes, largest first. Items 15 to 19 were added on 09-18-26 from
the step methods and the chapter information form's gap list.

1. **Item 15 — the CRM configuration has no versioned source and no applier.**
   Building the CRM (stage 9) copies configuration files off Cleveland's test
   system by hand and replays a capture taken on 08-31 through a trial script.
2. **Item 1 — the secrets store.** Chosen 09-18-26: Proton Pass, chapter-owned.
   Still to do: the central support organization's own vault, and moving the
   existing secrets off one laptop.
3. **Item 16 — no settings generator.** Deploying the applications (stage 11)
   runs a trial script that reads a filled-in form nothing else reads.
4. **Item 2 — no published version standard**, including whether the two paid CRM
   add-on products are part of it.
5. **Item 17 — the time zone is written into the code.**
6. **Item 12 — no way to load a chapter's existing records.**
7. **Item 3 — duplicate checking, saved views and automated rules unexamined.**
8. **Items 10 and 11 — the public pages**: the mentor directory page is not built,
   and the events page shows Cleveland's colours.
9. **Item 18 — five event email templates are missing** from the standard.
10. **Item 19 — CRM field labels say "CBM".**
11. **Items 4, 5 and 6** — the colour file template, the emergency access
    procedure, and the chapter training accounts.

---

## 1. A place to keep secrets

**Ruled 09-18-26 (Doug).** Each chapter owns a Proton Pass business organization,
with at least two chapter owners. Named people from the central support
organization are members of its shared Operations vault. Named sign-ins are used
wherever a system allows; the vault holds break-glass sign-ins, recovery codes and
machine secrets. Written into the guide as step 2.7.

**What is still missing.** The central support organization's own vault, for its own
secrets: the release tooling, Cleveland's deployments and the shared training
system. And moving Cleveland's and the trial chapter's secrets off the one laptop
into vaults.

**What was missing before the ruling.** There is no shared store for the six passwords and keys each
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

**Update 09-23-26.** The add-on half is ruled: both paid add-on products are in
the standard (R7, 08-31-26). The version half is still open, and Boston's build
reaches it at step 9.4. Steps 2.2 and 9.5 still call the add-ons undecided
(`TASKS.md` G1 item 6).

**Ruled 09-23-26 (Doug).** A new chapter installs the current EspoCRM release
that CRMBuilder's deploy installs, and Cleveland moves up to it later
(`TASKS.md` C1). Still missing: a published statement naming the versions, for
step 9.1.

**What is missing.** No document says which CRM version a new chapter installs,
which versions of the two paid add-on products, or which release of the standard
configuration is current.

**What it blocks.** Obtaining the standard's version numbers (step 9.1), and
therefore recording the CRM's version (step 9.4), installing the add-on
products (step 9.5), and the final check that the CRM matches the standard
(step 9.9).

**Size.** Small to write, but it needs a decision first. The August practice build
found that the deployment tool installs whatever version is current, which would
start a new chapter a major version ahead of Cleveland. Somebody has to decide
whether chapters are pinned to Cleveland's version, or Cleveland moves up.

---

## 3. A decision on duplicate checking, saved views and automated rules

**What is missing.** Nobody has ever examined these settings on either existing
system. The August practice build recorded them as "not examined" and said so
plainly.

**What it blocks.** Applying them on a new chapter's CRM (listed in stage 9 as not possible yet).

**Size.** An investigation, then a decision. It may be larger than it looks:
duplicate checking is not only a convenience for staff, it is something the intake
software's behaviour depends on, and that dependency has never been verified in
either direction.

---

## 4. A starter colour file and a logo specification

**Update 09-23-26.** The colour half is done another way: the chapter information
form asks for four colours, and `scripts/chapter_form/to_values.py` writes the
colour file from them. The logo specification is still missing.

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

**Changed 09-23-26 (Doug).** The 09-18-26 ruling below is reversed: adding a set of
training accounts for every chapter is too much work. Chapters sign in as the six
generic training users Cleveland's own trainers use, and the passwords are not
changed after each chapter. Nothing is built. What
remains is the note to trainees and the decision about when this machine stops
being the answer, both below.

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

## 7. A standard agreement

**Where it stands (Doug, 09-18-26).** A draft of the standard agreement exists and is
in review. It is not held in this repository.

**What is still missing.** The finished agreement. Two unruled questions may still
change its cost: whether the fee covers labour only (`DECISIONS.md` proposal 5), and
whether the two paid CRM add-on products are part of the standard (item 2). Once it
is final, stage 2's steps should be checked against it, clause by clause.

**What it blocks.** Signing it (step 2.6), and so every stage after stage 2.

**Size.** Finishing the review. Then one pass over stage 2 to match the
agreement's wording.

---

## 8. A support route and a change-request forum

**Where it stands (Doug, 09-18-26).** New feature requests, defect reports and
support requests all go into one ClickUp system, managed by the entire support
team. That settles the shared place to raise a request, and that no one person owns
it.

**Also ruled (Doug, 09-18-26).** The central committee meets every two weeks to
review and schedule features and defects. There is no committed response time.

**And (Doug, 09-18-26):** nothing is treated as urgent. Everyday requests — adding
a person, changing someone's team, resetting a password — are handled by the support
team as they arrive, not held for the committee.

**What is still missing.** One small thing: how a chapter's people get access to the
ClickUp system to raise and follow their requests.

**What it blocks.** Nothing in the writing: steps 18.1 and 18.2 are fully answered.
The ClickUp access has to exist before the first chapter's handover.

**Size.** Decisions first, then a small amount of setup. This is the item the rule
that every chapter runs the same software depends on: a slow route is how chapters
end up asking for administrator accounts of their own.

---

## 9. A leaving kit, rehearsed once

**What is missing.** `governance-and-exit.md` defines what a leaving chapter
receives: its CRM, an export of the application's own database, its shared drive
documents, and a licence to the last version. Nothing produces the kit, and the
leaving procedure has never been rehearsed.

**What it blocks.** Confirming the leaving terms in practice (step 18.6).

**Size.** A script for the database export, a written procedure, and one rehearsal on
the shared training system.

---

## 10. The public mentor directory page

**What is missing.** The page is not built (`prds/public-mentor-pages-plan.md`), and
it is not decided whether a chapter's website embeds it or redirects to it, as it
now does for events.

**What it blocks.** Displaying the mentor directory (step 13.1), links to a single
mentor (step 13.4), and whether step 13.3 applies at all.

**Size.** A build, and a decision first.

---

## 11. Chapter colours on the public events page

**What is missing.** The public events page uses a word-for-word copy of Cleveland's
website stylesheet, which sets Cleveland's navy and gold itself and never reads the
chapter's colour file. Every chapter's events page would look like Cleveland's.

**What it blocks.** Nothing outright, but step 13.2 gives a chapter a page in
another city's colours.

**Size.** Small: make the stylesheet's colours come from the chapter's colour
settings. Sits beside item 4.

---

## 12. A way to load a chapter's existing records

**What is missing.** No tool loads a chapter's old records into its CRM. The two
candidates are the CRM's own import screen and a script that uses the same
find-or-create rules as the public intake forms. Neither has been tried, and whether
the import screen can link each record to the one it belongs to is unchecked.

**What it blocks.** The trial load and the real load (steps 15.4 and 15.6).

**Size.** An investigation, then probably a script.

---

## 13. A plain list of the personal information the software collects

**What is missing.** Nothing lists, in plain words, what personal information the
forms and the software collect and where it is kept. A chapter's legal adviser needs
that list to write the privacy policy.

**What it blocks.** Writing the privacy policy (step 7.4).

**Size.** Small. The field mapping record (`field-mapping-completion-plan.md`) holds
the facts; they need rewriting for a lawyer.

---

## 14. ~~Steps for the provided Google Workspace branch~~ — closed 09-18-26

**Closed.** Doug ruled on 09-18-26 that every chapter hosts its own email on its own
Google Workspace. There is no provided branch, so there are no steps to write.

**What is missing.** Stage 4 is written for a chapter that brings its own Google
Workspace. The other branch, where the central support organization provides the
Workspace, has no written steps. `DECISIONS.md` proposal 4 would make bringing your
own the default, and it is not ruled.

**What it blocks.** Stage 4 for any chapter choosing the provided branch.

**Size.** A writing job, after the proposal is ruled.

---

## 15. A versioned CRM standard and an applier

**Update 09-23-26.** The 09-19-26 decision date has passed. Nothing in this
repository records whether the CRMBuilder requirements session was held, so it is
not known whether the applier is being built in CRMBuilder or here. Boston is
built with the trial method.

**What is missing.** Nothing holds the standard CRM configuration as a versioned
artifact, and nothing applies it. The August build copied two folders of
configuration files off Cleveland's test system by hand, then ran a trial script
(`scripts/rehearsal/apply_api_half.py`) that replays the teams, roles, email
templates and instance settings captured from that system on 08-31. Cleveland's
test system changes under the application, so "copy it off the test system" is a
different standard every week. Phase 1's plan has the conformance check built and
the applier not started.

**What it blocks.** Doing stage 9 (building the CRM system) repeatably, and the
final check that the CRM matches the standard (step 9.9).

**Size.** The largest item here. Ruled 08-31-26: the applier lives inside
CRMBuilder, which is a separate repository with its own requirement-first process.
Phase 1's decision trigger is 09-19-26: if CRMBuilder's requirements session has
not settled the headless requirement by then, the applier is built in this
repository instead (`phase-1-crm-config.md`).

---

## 16. A settings generator

**Update 09-23-26.** Mostly overtaken. `scripts/rehearsal/render_spec.py` now
writes the Google, mail, Drive, website and Zoom settings, and the chapter
information form is a web page that writes its values file. Two gaps remain: the
database it asks for is still a development database, and it reads secrets from
a file, not the vault.

**What is missing.** Nothing turns a filled-in chapter information form into the
application's deployment settings. The August build used a trial script
(`scripts/rehearsal/render_spec.py`). It asks for a development database, which
takes no backups, and it knows nothing about the Google or Zoom values. This is
Phase 3 of the chapter-network plan, not started.

**What it blocks.** Generating the deployment settings (step 11.2) and loading the
secrets (step 11.3) by anyone but the person holding the files.

**Size.** Moderate, and it pairs with item 1: the generator reads secrets from the
store.

---

## 17. The time zone is written into the code

**What is missing.** The Eastern time zone is written into four source files:
birthday greetings, the assignment date stamp, the public events page and a Zoom
default (`chapter-values.md` § C). A chapter elsewhere gets wrong dates, and
nothing reports an error.

**What it blocks.** Any chapter outside the Eastern United States.

**Size.** Small: one setting, defaulting to Eastern, read in four places.

---

## 18. Five event email templates missing from the standard

**What is missing.** The event follow-up emails need five CRM email templates:
`EventReminder`, `EventRecordingAvailable`, `EventNoShow`, `EventMentorCTA` and
`EventSurvey`. None exists on Cleveland's test system, so none reached the trial
chapter, and the conformance check fails on both for this reason alone.

**What it blocks.** A clean result from the conformance check (step 9.9), and
event follow-up emails on any system.

**Size.** Small: write the five templates once, on the test system.

---

## 19. CRM field labels say "CBM"

**What is missing.** Ten field labels in the CRM's configuration say "CBM", for
example "CBM Email". Every chapter's staff would see Cleveland's initials on their
own records (finding F7 of the August build).

**What it blocks.** Nothing breaks. Every chapter sees another city's initials.

**Size.** Small: relabel the ten fields with a neutral word, once, for everyone.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.15 | 09-23-26 20:40 | Step references follow stage 9's renumbering from twenty steps to nine: 9.3 → 9.4, 9.7 → 9.5, 9.20 → 9.9, and 9.16 is now listed in stage 9 as not possible yet. |
| 0.14 | 09-23-26 13:33 | Item 6 changed: chapters use the existing generic training users, reversing the 09-18-26 ruling for separate chapter accounts (Doug, 09-23-26). The passwords stay unchanged after each chapter, and stage 16 is rewritten to match. Nothing is built. |
| 0.13 | 09-23-26 13:23 | Item 2 ruled: Boston runs the current EspoCRM release, and Cleveland moves up to it later (Doug, 09-23-26). Nothing now needs an answer before Boston's build. |
| 0.12 | 09-23-26 13:21 | Brought up to date the day Boston is built. A new list at the top sorts every open item by what Boston needs: one needs an answer before the build (item 2, the CRM version), four have workarounds (items 15, 16, 1, 18), and the rest wait. Items 2, 4, 15 and 16 carry an update: the add-ons are ruled in, the colour file comes from the form, the applier's decision date passed with no recorded outcome, and the settings generator is mostly built. The 09-18-26 ranking is kept below the new list. |
| 0.11 | 09-19-26 00:10 | Item 14 closed: every chapter hosts its own Google Workspace, so there is no provided branch (Doug, 09-18-26). |
| 0.10 | 09-18-26 14:30 | Item 1 ruled: a chapter-owned Proton Pass business organization with central support members (Doug, 09-18-26). What remains is the central support organization's own vault and moving existing secrets off one laptop. |
| 0.9 | 09-18-26 14:00 | Implementation put first (Doug, 09-18-26): a ranked list of the technical holes added at the top, and five technical items added — a versioned CRM standard and applier, a settings generator, the time zone written into the code, five missing event email templates, and CRM field labels that say "CBM". |
| 0.8 | 09-18-26 13:50 | Item 8: nothing is urgent, and everyday requests are handled as they arrive (Doug, 09-18-26). Only chapter access to the ClickUp system remains. |
| 0.7 | 09-18-26 13:45 | Item 8 narrowed: the central committee reviews and schedules features and defects every two weeks, and there is no committed response time (Doug, 09-18-26). What remains is what counts as urgent, and chapter access to the ClickUp system. |
| 0.6 | 09-18-26 13:40 | Items 7 and 8 updated from Doug's answers on 09-18-26: a draft of the standard agreement exists and is in review; feature requests, defect reports and support requests go into one ClickUp system managed by the entire support team. Each item now lists only what is still missing. |
| 0.5 | 09-18-26 02:05 | Eight items added (7 to 14), found while writing the methods for the remaining stages: a standard agreement, a support route and change-request forum, a leaving kit, the public mentor directory page, chapter colours on the public events page, a way to load existing records, a plain list of personal information collected, and steps for the provided Google Workspace branch. |
| 0.4 | 09-18-26 01:55 | Item 6 rewritten after Doug ruled on 09-18-26 that chapter staff train with shared training accounts set up specifically for chapter training. Building those accounts is now the item's one piece of real work, and it blocks steps 16.1 and 16.6. |
| 0.3 | 09-15-26 00:22 | No items changed. Noted here for the record: the trial chapter stays running with testing the setup steps as its reason (Doug, 09-15-26), which gives four of the five remaining items somewhere to be tried before a real chapter meets them. |
| 0.2 | 09-14-26 18:09 | Item 6 rewritten after Doug ruled that chapters train on the existing test system. It is no longer a build — what remains is an account rule, a note for trainees, and a decision about when that machine stops being the answer. Five items now block work; this one blocks nothing. |
| 0.1 | 09-14-26 17:51 | First draft. Six items, found by reviewing the fourteen steps added after the completeness checks were run against the step list. |
