# CBM Intake Platform — Version 2 Requirements

**Theme: Reliability.** Make the intake forms trustworthy enough to be the
organization's front door — submissions are never lost, the forms keep working
when the CRM is unavailable, every submission eventually arrives in the CRM
exactly once, and staff are warned the moment anything needs attention.

Each requirement below states the business problem it solves, what the system
must do, how we will know it is finished, and how important it is. The
requirements are written to be understood by anyone, not just engineers.

---

## Requirement 1 — Every submission is saved the moment it arrives

**The problem today.** When a visitor submits a form, the application does not
keep its own copy. It immediately tries to build several connected records in
the CRM, and the visitor's information lives only inside that attempt. If the
CRM is unavailable, slow, or rejects part of the data, the submission can be
lost completely. The only record of what happened is a temporary technical log
that is wiped out every time the application is updated — and the application is
updated often.

**What the system must do.** The application must save a complete, permanent
copy of every submission to storage that we own and control, and it must do this
the instant the submission is received, before it attempts any work in the CRM.
The saved copy includes everything the person entered, the date and time it
arrived, which form it came from, and a unique reference number. This copy is
never erased by the application. It survives application updates, restarts, and
any CRM outage. It is the official record that the submission happened, separate
from whatever later happens in the CRM.

**How we will know it is done.**

- With the CRM completely turned off, a visitor can still submit a form, and
  afterward a permanent record of that submission exists in our own storage.
- If the application is restarted immediately after a submission, the saved
  record is still there.
- Any saved submission can be looked up by its reference number and sent to the
  CRM later.

**Importance: Highest.** This is the foundation of everything else. As long as a
submission can vanish, no other reliability work matters.

---

## Requirement 2 — The forms keep working when the CRM does not

**The problem today.** The visitor waits while the application talks to the CRM
several times in a row. Their experience is tied directly to the CRM's health.
If the CRM is down for routine maintenance over a weekend, or is simply slow at
a busy moment, the visitor sees an error page instead of a thank-you. A
prospective client, mentor, or partner who hits an error may never come back,
and we may never know they tried.

**What the system must do.** The visitor must receive a fast, successful
confirmation as soon as their submission has been safely saved (Requirement 1),
without waiting for the CRM at all. The work of creating the CRM records happens
separately, in the background, after the visitor has already been thanked. A CRM
that is slow, busy, or temporarily offline must never cause an error for the
person filling out the form.

**How we will know it is done.**

- With the CRM fully offline, a visitor can complete any form and receive the
  normal thank-you confirmation.
- The confirmation appears within a couple of seconds, no matter how slow the
  CRM happens to be.
- Submissions received while the CRM was offline are turned into CRM records
  automatically once the CRM is available again, with no staff action required.

**Importance: Highest.** Together with Requirement 1, this is the core promise of
Version 2: a visitor always succeeds, and their information is always kept.

---

## Requirement 3 — Reliable, automatic delivery into the CRM

**The problem today.** A single submission needs to become several connected
records in the CRM. Today the application tries to build them once. If that
attempt fails, it is not tried again on its own. A temporary problem therefore
becomes a permanent failure, and it stays failed until a person happens to
notice and redoes the work by hand.

**What the system must do.** A background process must take each saved submission
and create its CRM records, and it must keep trying until it succeeds. Temporary
failures are retried automatically on a sensible schedule — quickly at first,
then at longer intervals — so that short-lived problems heal themselves without
anyone involved. Every submission carries a clear, visible status: waiting to be
processed, in progress, completed, or needs attention. Staff can see this status
for any submission, and they can re-send anything that is stuck with a single
action. At no point does recovering a failed submission require anyone to re-type
the visitor's information.

**How we will know it is done.**

- A submission whose first attempt fails because of a temporary problem is
  retried automatically and completes on its own once the problem clears.
- Staff can view a list of all submissions together with the current status of
  each one.
- A submission that still cannot be completed after repeated attempts is clearly
  marked "needs attention" rather than quietly disappearing.
- Any stuck submission can be re-sent into the CRM with one action, using the
  saved copy, with no re-keying.

**Importance: High.** This is the engine that turns "saved" into "in the CRM."

---

## Requirement 4 — No duplicates and no half-finished records

**The problem today.** There are two related risks. First, if a visitor submits
twice, or the system retries an attempt, we could create duplicate people and
duplicate records. The only thing preventing this today is held in the
application's temporary memory, which is erased every time the application is
updated — so the protection disappears regularly. Second, each submission
creates a chain of linked records; if that chain breaks partway through, the CRM
is left with disconnected, half-built records that mislead staff and distort
reporting.

**What the system must do.** One submission must always produce exactly one set
of records, no matter how many times it is submitted, retried, or re-sent, and
this guarantee must survive application updates and restarts. When the system
recognizes a person who already exists — matched by their email address — it
must reuse that existing person rather than create a second copy. When a chain of
records fails partway through, retrying it must finish the missing pieces and
connect them correctly, rather than starting a second, parallel chain alongside
the first.

**How we will know it is done.**

- Submitting the same form twice within a short time creates only one set of
  records.
- A retry that happens after an application update does not create a duplicate.
- A submission that failed partway, once retried, ends as a single, complete set
  of correctly connected records, with no stray half-records left behind.

**Importance: High.** Duplicates and orphans erode staff trust in the CRM and
quietly corrupt every report built on top of it.

---

## Requirement 5 — Early warning when something needs attention

**The problem today.** If submissions begin to fail, no one finds out until a
prospective client telephones to ask why they never received a response. There
is no dashboard and there is no alert. We are relying on luck and on visitors
being patient enough to follow up.

**What the system must do.** The organization must be told promptly and
automatically whenever something is wrong: submissions are failing, a backlog is
building, or processing has stalled. Designated staff receive a notification —
for example, an email — when the rate of failures or the size of the backlog
passes a defined level. A simple status view shows, at a glance and for any
chosen period of time, how many submissions arrived, how many were completed
successfully, and how many need attention.

**How we will know it is done.**

- When several submissions fail within a short window, designated staff receive
  an alert without anyone having to watch the system.
- A status view shows submission counts and their outcomes for any period a
  staff member chooses.
- The alert describes the problem clearly enough that staff can tell whether it
  is something on our side or something with the CRM.

**Importance: Medium-high.** Reliability that no one is watching is only reliable
until the first quiet failure.

---

## Requirement 6 — Protection from changes to the CRM

**The problem today.** The CRM is maintained by a separate effort, and its fields
and dropdown choices change over time as that work continues. When a choice is
renamed or a field is removed, the forms can begin to fail silently, because they
are still sending the old value the CRM no longer recognizes. We have already
seen this kind of mismatch cause failures.

**What the system must do.** The system must detect when what the forms expect no
longer matches what the CRM actually offers — for example, a dropdown choice the
CRM no longer accepts — and warn staff before real submissions start failing
because of it. This comparison runs automatically on a regular schedule, and
after known CRM changes, checking the values the forms rely on against the CRM's
current definitions. It does not depend on anyone remembering to run it.

**How we will know it is done.**

- When a dropdown choice the forms use is renamed or removed in the CRM, staff
  are warned before a member of the public encounters the resulting error.
- The warning names exactly which form and which value no longer match.
- The check runs on its own schedule, with no manual step.

**Importance: Medium.** This turns a recurring class of surprise outages into an
advance warning we can act on calmly.

---

## Summary

| # | Requirement | Importance |
|---|---|---|
| 1 | Every submission is saved the moment it arrives | Highest |
| 2 | The forms keep working when the CRM does not | Highest |
| 3 | Reliable, automatic delivery into the CRM | High |
| 4 | No duplicates and no half-finished records | High |
| 5 | Early warning when something needs attention | Medium-high |
| 6 | Protection from changes to the CRM | Medium |

Delivered together, these six change the intake platform from "works when
everything else is healthy" to "can be trusted as the organization's front
door."
