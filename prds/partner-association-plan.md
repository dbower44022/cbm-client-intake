# Partner and funder associations — and the Lists columns that use them

Last Updated: 10-28-26 10:34 · Revision 1.3 — change log at the end.

Prepared by Claude (Claude Code), for D. Bower. Discussed with Doug in plan
mode 10-28-26 00:33–01:28 and approved; every decision below is his.

**Status: stops 1–5 built as v0.295.0 and live-passed on crm-test 10-28-26; v0.295.1 fixes the two faults the pass found.** Stop 1 (the CRM change): `partner-association-crm-handoff.md`,
`scripts/plans/cpartner-association.json` (fingerprint `8dd9d9264170`),
`scripts/migrate_partner_association_roles.py`. Made on the way: the plan file
run by the shared applier stands in for a migrate script (the
`espo-crm-changes` procedure); every association is written under the
org-wide key, a mentor's referral included, after the application's own check
— so the Mentor Role needs no grant.

## Context

Doug asked for partners, events and funders on the Lists grid and Preview.
Asked what job that serves, he described why a company or contact is tied to a
partner or funder: the partner referred them to CBM; they attended an event the
partner sponsored; a mentor referred them on to the partner. Today those ties
are recorded in three unconnected places, or not at all:

- a **lead** holds one `referredByPartner`, set by an import template — and
  **conversion drops it** (`campaigns/conversion.py` copies nothing about a
  partner to the Company or Contact it creates);
- a **client** holds `CEngagement.referringPartners` (ruling 30), only when
  they applied through the partner's intake link;
- **event attendance** links a Contact to an event (`CEventRegistration`) but
  never records the company, and nothing links a partner to the attendee;
- a **mentor's referral to a partner** is recorded nowhere.

So "everyone Lakewood Library is associated with" has no answer, the answer
breaks at each stage (lead → prospect → client), and history is lost when a
person leaves a company. The outcome: one permanent association between a
partner or funder and a company (or a person with no company yet), written by
every place a tie arises, and lists that select by it.

## Decisions (Doug, 10-28-26)

1. The relationship is with the **business**, recorded as a link to the
   company, at every stage — lead, prospect, client — consistently.
2. **The rule**, Doug's words: "Once a contact that is associated with a
   company is referred by a partner/funder, that partner will be associated
   with that company, and all of their related contacts forever. If a contact
   is referred by a partner/funder without a company being defined, we will
   track the relationship with the contact until a company is established.
   Then the relationship will transfer to the company and last forever. If a
   second partner/funder referrs a contact/company/both, we will add a second
   reference to the contact/company."
3. **Attendance is reported by company**, the attendee as optional detail;
   never report someone who did not attend; never lose the partner–company
   tie when a contact is removed.
4. **Attending a partner's or funder's event creates the same permanent
   association**, the reason recorded (option A).
5. **A mentor's referral to a partner creates the same association**, reason
   recorded, entered by a *Refer to a partner* action on the engagement in
   Client Management, logged on the engagement.
6. **The Lists columns show what the list is built to reach** — the partners,
   events and funders its own search names; Preview's *Used by* adds those on
   its campaigns ("go").

## The design (routine choices, announced)

**One CRM entity, `CPartnerAssociation`** (label *Partner or funder
association*), one record per tie — a link with a reason needs its own record:

- `partnerProfile` (CPartnerProfile) **or** `sponsorProfile` (CSponsorProfile);
- `company` (Account) — empty until the person has one;
- `contact` (Contact) — the person who carried it, kept as history;
- `lead` (CProspect) — while the tie is still on a lead;
- `reason` enum: *Referred to CBM*, *Attended an event*, *Referred by CBM*;
- `event` (CEvent), `engagement` (CEngagement) — where it came from;
- `associatedAt`; the creator is the record's own `createdBy`.

Never deleted by the application. One record per (partner or funder, holder,
reason, event), so a second referral by the same partner is not a duplicate,
and a second partner is a second record (decision 2).

**`CEventRegistration.registrationCompany`** (Account): the company the
person was with when they registered (decision 3), written at registration.

Both go in one handoff, `partner-association-crm-handoff.md`, applied by a
`scripts/migrate_partner_association_schema.py` in the house shape
(idempotent, dry-run default, reads every link back) — the
`espo-crm-changes` skill's procedure; crm-test first, production and Boston
at their slots. Every read and write feature-detects the entity, so the
application ships dark until the CRM has it.

**One module writes every association: `core/partner_links.py`**, called by:

- **conversion** (`campaigns/conversion.convert_lead`): the lead's
  `referredByPartner` and its lead-held associations move to the new
  Company (decision 2's transfer);
- **the import** (`campaigns/imports.py`): a template's referrer partner
  writes an association on the lead, *Referred to CBM* — and a second
  partner on a known lead adds a second one instead of being dropped;
- **client intake** (`forms/client_intake/orchestrator.py`): the partner
  link's partner(s) → an association on the company;
- **attendance** (`campaigns/attribution.opportunity_on_attendance`, already
  called by the manual mark, the check-in and the Zoom pull): an *Attended*
  registration at an event with partners or funders → an association per
  partner and funder, on the registration's company (else the contact);
- **the mentor's action** (decision 5): `POST` on the engagement in the
  sessions router, as the user, `record_action` on the engagement;
- **a nightly transfer** in the worker: associations on a contact that now
  has a company gain that company — catching every screen that attaches a
  company (merge-only, never removes).

**A one-time backfill**, an Operations job at `/setup` (dry run first, then
apply): leads' `referredByPartner`; engagements' `referringPartner(s)`;
past *Attended* registrations at partner or funder events (company = the
contact's current company, since no snapshot exists).

**Lists** (`campaigns/audience.py`, `listview.js`):

- two new Include / Leave out group kinds: **associated with** (partners or
  funders, optional reasons) and **attended** (events; attended or
  registered) — each reaching the person who carried the tie, or every
  contact at the company when *every contact* is ticked (the ruling-59
  pattern), and a lead's key while it is still a lead;
- the list view gains **Partners, Events, Funders** columns, read from the
  list's own groups (names stored in the group at save, so the index never
  calls the CRM); Preview shows them, plus a *Used by* line per campaign
  naming its partners, events and funders (`router._grid_relations`, for
  that list's campaigns only).

Not in this plan: the partner's attendance report itself (decision 3 is its
requirement; the data this plan stores is what it needs) — an
`OPEN-ITEMS.md` item. The grid rollout to Leads, Campaigns, Review, Calls and
Imports follows this plan, as Doug ordered.

## Stops

Work pauses after each for Doug's go-ahead.

1. **The CRM change** — handoff and migrate script; Doug runs it on crm-test
   (the classifier blocks schema writes from here). Rulings recorded in
   `prds/partner-association-plan.md` (this plan, kept in the repo).
2. **The writers** — `core/partner_links.py`, conversion, import, intake,
   attendance, the nightly transfer, the backfill job; tests with the fakes.
3. **Refer to a partner** in Client Management.
4. **Lists** — the two group kinds, the three columns, Preview.
5. **Documents and the live pass** on crm-test as Mark Marketing (lists) and
   a mentor (the referral action); results page; version and changelog.

## Verification

- Unit tests per writer: conversion moves the lead's ties; a second partner
  adds a second record; an attended registration writes one per partner and
  funder; a no-show writes none; the nightly transfer adds a company and
  never removes; the backfill's dry run plans what the apply writes.
- Lists: a list on "associated with Lakewood Library" reaches the carrier, or
  every contact when ticked; its row shows Lakewood Library under Partners.
- Live: on crm-test, convert a referred lead → the company carries the
  partner; mark an attendee at a partner's event → the company is associated;
  a mentor's *Refer to a partner* → associated and logged; a list built on it
  shows the right members and columns.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.3 | 10-28-26 10:34 | Claude (Claude Code) | Live-passed on crm-test; v0.295.1. |
| 1.2 | 10-28-26 02:32 | Claude (Claude Code) | Stops 2–5 built as v0.295.0. Made on the way: a lead's own *Referred by partner* stays its first tie until conversion (no per-row CRM call at import — the volume rule); a different partner on a known lead becomes a second association only on a row that also fills fields; a company-held tie with no person reaches every contact there; the *attended* group's *every contact* uses the company recorded at registration, so registrations made before v0.295.0 reach the person only. |
| 1.1 | 10-28-26 02:10 | Claude (Claude Code) | Copied into the repository; status of stop 1; two choices made on the way. |
| 1.0 | 10-28-26 01:30 | Claude (Claude Code) | Approved by Doug in plan mode. |
