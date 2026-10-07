# CRM build handoff — `Held-Company` intake status

Last Updated: 10-07-26 01:20 · Revision 1.0

**One enum option to add, on both CRMs.** It belongs to the CRM because the
CRM is the source of truth for the intake-receipt vocabulary (the 2026-07-27
redesign, `cintake-submission-redesign.md`). Same shape as the `Held-Duplicate`
handoff (`cintake-submission-duplicate-status.md`), and the two can be built in
one sitting.

The app already ships the behaviour and **feature-detects this option**, so
nothing breaks if the build is delayed — see "Until it exists" below.

## Why

A public submission (client intake, partner, sponsor) that names a company
already in the CRM **at a different web address** is now held for staff
instead of being delivered (Doug's ruling 2026-10-07, plan
`prds/company-website-hold-plan.md`). Two businesses can share a name, and the
exact-name match would attach the second to the first's records — for a client,
to another business's client profile and engagement. A held row needs a word in
the receipt vocabulary.

## The change

**Entity Manager → `CIntakeSubmission` → Fields → `intakeStatus` (enum) →
add one option:**

```
Held-Company
```

Exact spelling, capital H and C, one hyphen, no spaces — the app compares the
string literally.

Place it with the other held values so the picklist reads in lifecycle order:

```
Received
Completed
Held-Spam
Held-Email
Held-Duplicate
Held-Company       <-- new
Error
Discarded
```

Do this on **crm-test first, then production**.

Nothing else changes: no new field, no new link, no workflow, no role grant.
`intakeMessage` carries the explanation and the reviewer's two choices, and
the disposition fields already exist.

## Until it exists

`core/receipts.py:_gate_status` reads the live enum options once per process
and downgrades a value the CRM does not offer to `Received` — truthful, since
the submission is in hand and undelivered — with the full explanation still in
`intakeMessage`. Once the option is built the next receipt touch writes
`Held-Company` with no deploy.

## Verify

Submit the partner form on crm-test naming a company that exists there with a
different website. In Submission Admin the row reads **Held-Company**; in the
CRM the Intake Submission receipt reads `Held-Company` (or `Received` with the
explanation, before the option is built).

## Change log

| Rev | Date | Author | Change |
|---|---|---|---|
| 1.0 | 10-07-26 01:20 | Claude (Claude Code) | First version, with v0.238.0. |
