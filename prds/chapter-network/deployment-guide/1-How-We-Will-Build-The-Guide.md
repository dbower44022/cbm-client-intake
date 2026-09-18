# New Chapter Deployment Guide — How We Will Build It

**Document:** The plan for writing the New Chapter Deployment Guide
**Version:** 1.1
**Status:** Draft for review
**Owner:** Doug Bower
**Last Updated:** 09-18-26 02:05

---

## 1. What this document is

This is not the guide. This is the plan for writing the guide. We agree the plan
first, so that the writing itself is straightforward.

The guide takes a new mentoring chapter from nothing — no legal organization, no
email address, no website — to a chapter that is fully up and running. Its job is
to leave nothing out. It also suggests what order to do things in and what to
start early, but the promise it makes is coverage: every step is written down.

---

## 2. Who reads the guide

Two people read it, and it has to work for both.

The first is someone at the new chapter. They may not work in technology at all.
They need to know what to do, what order to do it in, and how to tell when a step
is finished.

The second is the person from the central support organization who does the
technical work inside the chapter's accounts.

The first reader is the harder one to write for, so the guide is written for
them. The second reader loses nothing by that.

---

## 3. Language rules

Settled 09-14-26. These apply to every line of the guide, and to every
conversation about it.

**Short sentences.** One idea each. If a sentence has to be read twice, it gets
rewritten shorter, not longer.

**Common words.** If a plain word will do the job, use the plain word.

**Name the thing, every time.** Never write "step 9" or "the earlier stage" on its
own. Write "the step that sets up the Google permissions (step 10)". The number is
a pointer. It is never the name.

**Define every term the first time it appears**, in one sentence, in plain words.
If a term needs a paragraph to explain, it does not belong in that sentence.

**No shorthand and no insider language.** No abbreviations unless the
abbreviation is the actual published name of the thing.

**No pronoun where a name belongs.** "It", "this" and "that" do not stand in for a
defined term. Repeat the term.

---

## 4. The names we use

One name per thing, used everywhere. Two systems in this project are easy to
confuse, and confusing them has already happened once.

**The shared training system.** Cleveland's existing test system. It clears itself
out every night. Chapter staff train on it (ruled 09-14-26).

**The trial chapter.** A complete chapter built from nothing on 31 August 2026 for
an organization that does not exist, to prove the build could be done. Its own CRM
system on its own server, with its own copy of the applications. It has no Google
account and is not going to get one. It stays running so that setup steps can be
tried on it before a real chapter meets them (ruled 09-15-26).

**The central support organization.** The organization that develops and supports
the software for every chapter.

**The chapter information form.** The list of roughly thirty-five values that
differ from one chapter to the next.

---

## 5. What the guide covers

Everything. Setting up the legal organization, nonprofit status, the agreement with
the central support organization, registering domain names, email, Google
Workspace, hosting accounts, the CRM system, the applications, the website, the
people, the records, staff training, backups, and the handover into normal
day-to-day support.

The guide does not stop at the edge of what the central support organization is
good at. Some steps are outside its expertise — setting up a nonprofit corporation
in a particular state, for example. Those steps are still written down: what the
step has to produce, when it has to start, and what cannot happen until it is done.
The guide says plainly that the chapter gets that particular advice elsewhere.

A step nobody here performs is still a step. An undocumented step is how a chapter
gets stuck.

---

## 6. The shape of the guide

The guide is a numbered list of steps in the order they have to happen.

Each step says **what must be true when the step is finished**. It does not
describe an activity. "The domain name is registered and the chapter controls the
account that holds it" is a step. "Register a domain name" is not, because nobody
can check it.

Each step then gives the method in two parts:

**How to do it today** — what a person can actually do right now, by hand or with
the scripts that already exist.

**How it will be done later** — a marked, usually empty, space naming the
automation that will one day replace the manual method.

The order of the steps is the stable part. Methods change as automation arrives;
the steps themselves do not. That is what keeps each future rewrite inside a
single step instead of spreading through the whole document.

Every step also carries one of two labels. **Done for real** means someone has
actually performed this step on a real system and there is a written record of it.
**Not yet tried** means the step is written from the design and has never been
walked through. No step is quietly presented as tested when it is not.

---

## 7. The eighteen stages

A stage is a group of steps that share a starting condition and a finishing test.
The stages run in this order because each one needs something an earlier one
produces.

**1. Set up the chapter as a legal organization.** The chapter exists in law, with
a board, someone who can sign for it, a chosen name, and either its own nonprofit
status or an arrangement with a sponsoring nonprofit. The chapter's name is chosen
here, because the legal filing needs it. That name then appears throughout the
software, so it is chosen once and not revisited. The central support organization
does not do this work. It is in the guide because it controls both the cost and the
waiting time of two later stages, and because the sponsoring-nonprofit case changes
who is allowed to own the accounts.

**2. Sign the agreement with the central support organization.** What each side
does, what it costs, how long notice has to be given, and exactly what the chapter
takes away with it if it ever leaves. This comes second because everything after it
involves one organization spending money and holding administrative access inside
another organization's accounts.

**3. Register the chapter's domain names.** A founder's existing email address is
used to register the domain name or names at an ordinary domain registrar, and to
create the account that holds them. Whether a chapter needs one domain name or two
is an open question — see section 10.

**4. Set up Google Workspace and the chapter's email.** The Google Workspace
account is created on the chapter's domain, the domain is verified, email starts
flowing, the shared mailboxes and the members group are created, control of the
domain registrar account moves from the founder's personal email to a chapter
mailbox, and the nonprofit discount is applied for. This stage also holds one
choice: the chapter brings its own Google Workspace, or the central support
organization provides one on its behalf. The consequences of the second choice —
specifically what happens if the chapter later leaves — are explained before the
choice is made, not after.

**5. Open the hosting and video meeting accounts.** The chapter's own server
hosting account, its hosting credits, a video meeting account if it runs public
webinars, and the administrative access that lets the central support organization
operate each of them on the chapter's behalf.

**6. Build the chapter's public website.** The chapter's own marketing website
exists and works at its own domain name. A chapter that already has a website has
already finished this stage. It comes this early because the two stages after it
depend on it.

**7. Write and publish the policy documents.** Four documents — the client code of
conduct, the mentor code of ethics, the terms, and the privacy policy — written for
this chapter and published at this chapter's own web addresses. This is its own
stage because the public application form has a consent box that links to all four.
Showing one city's applicants another city's privacy policy is a legal problem, not
a branding one.

**8. Fill in the chapter information form.** Roughly thirty-five pieces of
information that differ from one chapter to the next — names, web addresses, email
addresses, time zone, and six passwords or keys. This is the dividing line between
setting the chapter up and installing the technology. Nothing after this stage can
start until the form is complete, and everything after it becomes routine once it
is.

**9. Build the CRM system.** Create the CRM system, install the two add-on products
it depends on, copy in the standard configuration, create the teams and permission
roles and email templates, apply the instance settings, create the two system
accounts the applications log in with, and run the checking tool until it reports
no differences from the standard.

**10. Set up the Google permissions the software needs.** Create the machine
account the applications will use, and enter the permission grant in the chapter's
own Google admin console with the exact list of permissions. This happens before
the applications are deployed, because the applications need the resulting key at
the moment they start.

**11. Deploy the chapter's applications.** Build the deployment settings from the
chapter information form, load the passwords and keys including the Google key from
the stage before, create the application components, run the database setup, deploy
the released version, set the update policy, and turn off automatic deployment at
the moment the application is created rather than going back for it later. Then work
up the ladder of Google checks: mail arrives, mail sends, the calendar works, and a
newly approved mentor gets a real working mailbox.

**12. Set up backups and monitoring.** The CRM system and the application database
are backed up on a schedule, someone can restore from a backup, and somebody is
told when the system stops working. This happens before any real records are
loaded, not after.

**13. Put the chapter's pages on its website.** Install the pages the software
publishes — the mentor directory and the events programme — into the chapter's own
website, pointed at that chapter's own application, and allow that one website to
display them.

**14. Create the staff accounts.** Only an administrator can create staff
accounts, so this is central support organization work. Mentors are not created
here.

**15. Bring in the chapter's records and create the mentor accounts.** Whatever
client, mentor and company records the chapter already holds, loaded into the CRM
system. Then every mentor gets an account, created from their mentor record in
Mentor Administration. The mentor accounts come last because an account made any
other way turns into a duplicate (ruled 09-18-26). A chapter starting from nothing
skips the load, but still enters its mentors and creates their accounts.

**16. Train the chapter's staff.** The people who will use the system every day are
shown how, using the training material and a practice area rather than live
records.

**17. Check everything works before going live.** An ordinary, non-administrator
user from each team walks the whole client intake path from the public form through
to a closed submission, and the published pages are checked on the chapter's own
website. Administrator accounts skip all permission checks, so testing as an
administrator proves nothing.

**18. Hand over and start normal support.** Who to call, how to request a change and
how long an answer takes, what the weekly software release schedule means for the
chapter day to day, and how the chapter's leaving terms work in practice.

---

## 8. What every step contains

Every step is written to the same eight headings, in the same order.

1. **Step number and name.**
2. **What must be true when this is done.** Written so someone else could check it.
3. **Who does it.** The chapter, the central support organization, or both.
4. **What has to be finished first.** The earlier steps, named and numbered.
5. **How to do it today.**
6. **How it will be done later.** The automation that will replace the manual
   method, or "not yet".
7. **How you know it worked.** The check to run, and the result to expect.
8. **What goes wrong.** The known failure and how to recognise it, where one is
   known.

Heading 7 is required and cannot be left blank. A step whose completion cannot be
checked is a step that gets skipped.

---

## 9. How we prove nothing is missing

The guide's promise is that every step is written down. That promise needs a test.
An opinion that the guide looks complete is not a test. Three checks run against
the finished draft, and each one can find a missing step on its own.

**The information check.** Every piece of information on the chapter information
form must be created by exactly one step and used by at least one step. A piece of
information that no step creates means a step is missing. A piece that no step uses
means either the information does not really belong on the form, or a later step is
missing. This check is mechanical, and it is the strongest of the three.

**The configuration check.** When a practice chapter was built in August, a record
was kept of every category of CRM configuration, how each one was carried across,
and whether it worked. Every category in that record must appear in a step. A
category with no step is a gap that has already been shown to cause trouble.

**The access check.** Every account, password, key and permission grant the running
system needs must be created by a named step, held by a named party, and reachable
without depending on one particular person's laptop. This is the check that catches
ownership problems — a domain name sitting in a volunteer's personal account, or a
password only one person has.

There is a fourth check, and it is not a review at all. It is doing the work. A
step labelled **done for real** has been performed on a real system with a record
kept. The steps still labelled **not yet tried** are the guide's honest to-do list.

---

## 10. How steps get tested

**The trial chapter stays up, and its job is now testing the setup steps**
(ruled 09-15-26). It was kept alive after the August build to rehearse the Google
connection. That rehearsal is not happening, so it has a new and better reason:
it is the only chapter system in existence that is not Cleveland's, which makes it
the one place a setup step can be tried before a real chapter meets it. Fifteen
stages are about to be written from the design, and several of them can be tested
against it rather than guessed at.

Cost: roughly twenty-five dollars a month in Doug's own accounts. Review at the
end of October — keep it only if the writing has actually been tested against it
by then.

**The Google connection will not be rehearsed.** Those steps are written from the
design, marked as never performed, and the first real chapter is the rehearsal —
with someone from the central support organization present while it happens, and
the steps corrected the same day.

### What has actually been done for real

More of the guide is tested than the first accounting said. The August build
covered, in whole or in part, five stages rather than two.

**Filling in the chapter information form.** The form was filled in for the trial
chapter and the filled-in copy survives. The part that was not done is putting the
secrets somewhere safe, because there is nowhere to put them.

**Building the CRM system.** Done in full, apart from installing the two paid
add-on products, which is how that failure was found.

**Deploying the applications.** Done in full apart from every Google step, which
was switched off on purpose.

**Creating the staff accounts.** Seven ordinary users were created, one
for each team, each with the right single team and no extra permissions.

**Checking everything works before going live.** Those seven users were tested
against twelve restricted pages each — allowed on their own, refused everywhere
else — and then a person walked the whole client intake path by hand, from the
public form through assignment to a closed submission.

### What has never been tested at all

The first seven stages, from setting up the chapter as a legal organization
through publishing the policy documents. They are about an organization rather
than a computer, so no practice system can test them. They get tested by the first
real chapter. Until then they stay marked "not yet tried", and someone who has
personally done each of those things at least once reads them over.

**What this means for the guide's honesty.** A good part of it will be marked never
performed when it is finished. That is the true state, and marking it is better
than not marking it. The label is what tells a reader which parts to trust and
which to watch.

---

## 11. Open questions

These do not block writing the list of steps. They do have to be answered before
the stages they touch can be written out in detail.

**One domain name or two?** Cleveland uses two: one for the public website, and a
second, shorter one for email addresses, mentor logins and the address the CRM
system sends from. A new chapter could copy that, or use a single domain name for
everything. Two is more to explain and more to pay for. One is simpler but ties the
email addresses to the marketing name for good. This affects the stage that
registers domain names (stage 3), the stage that sets up Google Workspace
(stage 4), and about eight entries on the chapter information form.

**What happens when the chapter has a sponsoring nonprofit instead of its own
nonprofit status?** The nonprofit discounts for Google Workspace and for server
hosting are claimed against a nonprofit's own status. A chapter operating under a
sponsor does not have its own, so the accounts would have to sit under the sponsor
— which cuts against the rule that the chapter owns its own accounts and can
withdraw access at any time. Nothing written today covers this case.

**Does each chapter publish its own help documentation, or share one site?** The
software links staff to a documentation site, and the CRM system carries a
navigation tab pointing at it. Cleveland publishes its own. A new chapter either
does the same, which is another site to build and maintain, or points at a shared
one, which then has to be written so it suits every chapter. Nothing written today
says which.

**Which time zone rule applies to a chapter outside the Eastern United States?**
The software currently has the Eastern time zone written into four places in its
code. A chapter in Denver or Phoenix would see wrong calendar dates on birthday
messages, assignment dates and the public events programme. Nothing breaks and
nothing reports an error, which is what makes it dangerous. The guide cannot
document a step for this until the software is changed.

---

## 12. Document rules

**Naming products is allowed in this guide.** The standing rule that keeps vendor
names out of requirements documents applies to documents that describe what a
system must do. This guide tells a person which screen to open, so naming the
product is the entire point. Recorded here so the question does not come up again
during writing.

**Version number and change log** on the guide and on this plan, with the date and
time stamp in MM-DD-YY HH:MM form.

**One document to start.** The guide begins as a single document with a list of its
stages at the top. Any stage that grows beyond roughly fifteen steps moves into its
own file, with the main document keeping the numbered list and the finishing tests.
Decided rather than asked, because it follows from length, and the length is not
known yet.

---

## 13. The order we build it in

1. ~~Agree this plan.~~ Done 09-14-26.
2. ~~Write the bare list: all eighteen stages broken into numbered steps, each
   with only its name and what must be true when it is done.~~ Done 09-14-26 —
   one hundred and fifty steps.
3. ~~Run the three checks in section 9 against that bare list.~~ Done 09-14-26 —
   fourteen gaps found and closed.
4. ~~Write the methods for the stages that have been done for real.~~ Done
   09-14-26 — building the CRM system and deploying the applications.
5. ~~Write the methods for the remaining stages.~~ Done 09-18-26 — every stage now
   has written methods, in documents 3 and 5 to 11. The Google permissions stage is
   done, written from the design. Filling in the chapter information form,
   creating the staff accounts, and checking everything works before
   going live are done, written from the August build (09-18-26). Setting up
   backups and monitoring is done, written from Cleveland's live hosting account
   (09-18-26). Training the chapter's staff is done, written from Cleveland's own
   training material (09-18-26). The last ten stages were written the same day from
   the design and the network's rulings, and are labelled as never performed. The
   work list grew to fourteen items.
6. Take the first real chapter through the guide. Someone from the central support
   organization is present for the Google steps, and corrects them the same day.

Doing the checks in step 3 before writing any methods in step 4 is deliberate.
Filling polished text into a list that is missing steps produces a document that
reads well and still has holes, and once the writing is good the holes stop being
visible.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 1.1 | 09-18-26 02:05 | Build order step 5 done: methods written for the last ten stages — setting up the legal organization through publishing the policy documents (documents 8 and 9), putting the chapter's pages on its website and loading existing records (document 10), and the handover (document 11). Every stage now has written methods. Next is step 6, taking the first real chapter through the guide. |
| 1.0 | 09-18-26 01:55 | Build order step 5 updated: methods written for training the chapter's staff (`7-Methods-Training.md`). Ten stages remain. |
| 0.9 | 09-18-26 01:18 | Build order step 5 updated: methods written for setting up backups and monitoring (`6-Methods-Backups-Monitoring.md`). Eleven stages remain. |
| 0.8 | 09-18-26 00:50 | Stages 14 and 15 renamed and their boundary moved: mentor accounts are now created at the end of the records stage, from each mentor's record (Doug, 09-18-26). |
| 0.7 | 09-18-26 00:45 | Build order step 5 updated: methods written for three more stages, all tested in the August build (`5-Methods-Form-Accounts-Checks.md`). Twelve stages remain. |
| 0.6 | 09-15-26 00:22 | The trial chapter stays up, with testing the setup steps as its stated reason (Doug, 09-15-26), reviewed at the end of October. Section 10 also corrected: five stages were covered in whole or in part by the August build, not two. Filling in the chapter information form, creating the staff and mentor accounts, and checking everything works before going live all have real evidence behind them and were wrongly counted as untested. |
| 0.5 | 09-15-26 00:19 | A list of the names we use added as section 4, after two systems were confused in conversation — the shared training system and the trial chapter are different machines. Later sections renumbered. Section 10 rewritten after Doug ruled the Google connection will not be rehearsed: those steps are written from the design and the first real chapter is the rehearsal. |
| 0.4 | 09-14-26 17:41 | Fourth open question added: whether each chapter publishes its own help documentation or shares one site. Found by running the completeness checks against the step list. |
| 0.3 | 09-14-26 17:11 | Stage names and boundaries reviewed and corrected. Thirteen stages became eighteen. Two ordering errors fixed: the chapter's name moved into the legal setup stage, and the Google permission work split so the part that must precede deployment is separate from the checks that must follow it. Five stages added: signing the agreement with the central support organization, setting up backups and monitoring, putting the chapter's pages on its website, training the chapter's staff, and bringing in existing records as a stage of its own. Section 10 added, recording three open questions. |
| 0.2 | 09-14-26 17:06 | Rewritten at a plainer language level on Doug's instruction. Added the language rules (section 3) and the description of who reads the guide (section 2). All stages given plain-English names instead of being referred to by number alone. No decisions changed. |
| 0.1 | 09-14-26 14:32 | Initial draft. Shape of the guide settled as one ordered list of steps with a method for today and a space for later automation; coverage settled as nothing left out, from legal formation onward; thirteen stages, the eight headings every step carries, three completeness checks, and the build order. |
