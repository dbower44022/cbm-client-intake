# Company website hold — plan

Last Updated: 10-07-26 01:05 · Revision 1.0

The public intake forms hold a submission for staff review when the company
it names already exists under a different web address. Doug's ruling
2026-10-07, following v0.237.0 (the same check on the staff quick-add, which
refuses instead).

## The decision and why

**Hold, never refuse, never merge.** A public submitter is an anonymous
visitor who cannot fix CRM data, and a message naming the existing company and
its website hands our records to anyone who types a name. The platform's first
rule is never lose a submission. So the submission is captured as always, the
visitor sees "received", and the conflict is decided by staff.

**Client intake included.** For a partner or funder a wrong company match is
cheap to undo on the Details tab. For a client it is not: the client profile
is found by company, so a wrong match attaches the new client to another
business's profile and engagement — the July 2026 production incident class.

## Mechanism

1. **Where.** The check runs where the company match runs — in the three
   orchestrators that use a website (client intake, partner, sponsor), through
   `core.crm_upsert.conflicting_website`. Same comparison as quick-add
   (`website_key`): scheme, `www.`, case, trailing slash never differ; the
   path does. No website entered, or none stored ⇒ no conflict; none stored ⇒
   the website is null-filled.
2. **What.** The orchestrator raises `CompanyConflict` before any record is
   written. The worker (and the synchronous path) catch it and put the row in
   the new status **`held_company`**, with the explanation on the row. The
   CRM receipt reads `Held-Company` once the enum option exists on that CRM,
   `Received` until then (`_GATED_STATUSES`, the Held-Duplicate precedent).
3. **Who.** Submission Admin lists it as a new item (`OPEN_REVIEW_STATUSES`),
   with two actions instead of Approve:
   - **Same company** — the submitted website is dropped from the delivery
     (a `delivery_overrides` entry), so the name match reuses the company and
     its stored website stands.
   - **Different company** — staff supply a qualified name; it replaces the
     submitted company name for delivery, so a new company is created.
   Both then redrive. Discard stays available.
4. **How the override reaches delivery.** A new `delivery_overrides` JSONB
   column (migration 0029). The worker merges it over the captured payload
   before validation. The captured payload is never rewritten — it is the
   audit record of what the visitor sent; the activity feed records the
   decision and the name used.

## Not in scope

- The information request form collects no website.
- The event registration and volunteer forms create no company.
- Fuzzy name matching. Matching stays exact-name, as everywhere else.

## Change log

| Rev | Date | Author | Change |
|---|---|---|---|
| 1.0 | 10-07-26 01:05 | Claude (Claude Code) | First version, written as the build started. |
