# Kickoff — the lead model's code rework (build plan § 7a.5 step 2)

Revision 1.0 · Last Updated: 10-19-26 11:03 · Prepared by Claude (Claude Code) for D. Bower

| Rev | Date (MM-DD-YY HH:MM) | Change |
|---|---|---|
| 1.0 | 10-19-26 11:03 | First version, written when the CRM half was applied on crm-test (rulings 49, 50). |

Operating mode: DETAIL.

## What this session does

Reworks the application to the lead model, in one release behind the existing
campaign switches. The CRM already has the new fields and options on crm-test
(`coutreach-lead-model-crm-handoff.md` § 2a). Commit in this clone. Doug reviews
and pushes.

## Read first, in this order

1. The repository's root `CLAUDE.md`. Note that its five-forms section defines
   **door** "(Doug, 10-18-26)". Ruling 41 retires that word, and this session
   rewrites the definition. Put the new wording to Doug before committing it,
   because the "door" definition is his.
2. `prds/prospect-marketing/README.md`, *Rules for working in this directory*.
   Check `git log -3 -- prds/prospect-marketing` first.
3. `prds/prospect-marketing/rulings.md`, rulings 41–50 in full.
4. `prds/prospect-marketing/build-plan.md` § 7a. The table in § 7a.3 is the
   module-by-module work list.
5. `coutreach-lead-model-crm-handoff.md`, especially § 1 (what waits for this
   release), § 5 (the value move) and § 7 (the layouts).

## Put to Doug before building, one at a time

- **The draft "a scan alone does not convert"** (build plan § 7a.2), left open
  by ruling 50. Today a scan moves the record to Lead (ruling 16).
- Anything the § 7a.3 table leaves open once the code is read. Two examples: what
  the postcard and call selection rules store for an Unqualified lead, and how
  the call screen asks for an email or website (ruling 47).

## The work, by module (build plan § 7a.3)

- **Configuration:** `campaigns/config.py`, the new status, stage, reason and
  Lead Source constants.
- **Import:** `imports.py`. Every row enters Unqualified, and no Company or
  Contact is created.
- **Review:** `review.py`. Qualify only with a website or email; Disqualify
  takes a note.
- **Landing and response:** `landing.py` and `forms/prospect_response/`. A
  response with a website or email converts the lead.
- **Calls:** `calls.py`. Interested converts only with an email or website
  (ruling 47).
- **Postcards:** `postcard.py`. It selects Unqualified and Qualified leads
  (ruling 44).
- **Attribution:** `attribution.py`. It writes Engaged, and every public form
  creates a lead, Converted at once, with Lead Source set to the form (ruling 48).
- **Stale sweep:** `stale.py`.
- **Email and SMS selection:** `email.py` and `sms.py`.
- **Reporting:** `reporting.py` and `analytics/campaigns.py`. Three counts:
  Responded, Converted, and Became a client, partner or funder (ruling 46).
- **Screens and documents:** the words lead, Lead Source, public form,
  conversion and stage throughout.
- **At the release:** the lead's layouts (handoff § 7) and the value move on
  crm-test (handoff § 5).

Then the live pass on crm-test re-runs the stage steps of the Phase 1–4 passes
(§ 7a.5 step 3). Write it as a runbook page under the Step-by-Step Instructions
standard.
