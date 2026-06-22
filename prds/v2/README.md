# Cleveland Business Mentors — Intake Platform, Version 2

## Why there is a Version 2

Version 1 delivered the working front door. Five public web forms — mentor
request, volunteer, information request, partner, and sponsor — take what a
visitor enters on the website and create the matching records in our CRM. It is
live, and it works.

Version 1 proved the idea. Version 2 makes it dependable.

The forms today succeed only if the CRM is healthy and responsive at the exact
second a visitor clicks "submit." The application takes the person's information
and immediately tries to build several linked records in the CRM while the
visitor waits. If the CRM is down for maintenance on a Saturday evening, or
simply slow, or rejects one piece of the data, two bad things can happen: the
visitor sees an error instead of a thank-you, and their information can be lost,
because we never kept our own copy. The only trace is a temporary technical log
that is erased every time the application is updated.

For an organization whose pipeline of future clients, mentors, and partners
comes through these forms, that is too fragile. Version 2 fixes it.

## The goal, in one sentence

Every submission is captured and saved the instant it arrives, the forms keep
working even when the CRM does not, every submission eventually lands correctly
in the CRM, and staff are warned the moment anything needs attention.

## The six requirements

1. **Every submission is saved the moment it arrives** — a permanent copy in our
   own storage, before any CRM work, so nothing is ever lost.
2. **The forms keep working when the CRM does not** — the visitor always gets a
   fast confirmation; CRM work happens afterward, in the background.
3. **Reliable, automatic delivery into the CRM** — failed transfers retry
   themselves until they succeed, and staff can see and re-drive anything stuck.
4. **No duplicates and no half-finished records** — one submission always
   produces exactly one complete, correctly connected set of records.
5. **Early warning when something needs attention** — staff are alerted to
   failures and backlogs instead of hearing about them from an unhappy visitor.
6. **Protection from changes to the CRM** — when the CRM's fields or options
   change, we detect the mismatch and warn staff before real submissions fail.

The full definition of each is in
[CBM_Intake_V2_Requirements.md](CBM_Intake_V2_Requirements.md).

## Suggested order of delivery

Requirements 1, 2, and 4 are the foundation and belong together: save every
submission, confirm to the visitor immediately, and never create duplicates or
orphans. Requirement 3 is the engine that delivers the saved submissions into
the CRM and retries failures. Requirements 5 and 6 are the operational safety
net that tells staff when to step in. We recommend building them in that order.

## What is deliberately not part of Version 2

- New forms, or new questions on the existing forms.
- Any change to how the CRM itself is structured.
- Spam and abuse controls beyond the current hidden-field check (worth doing,
  tracked on its own).
- Replacing or moving off the current hosting.

These are out of scope so that Version 2 stays focused on one outcome:
submissions that can be trusted never to be lost and always to arrive.
