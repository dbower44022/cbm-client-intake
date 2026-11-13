# Kickoff prompt — Business Evaluation, phase 1: the foundation

Last Updated: 11-13-26 00:42 · Revision 0.1 — see change log at the end.

Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`. The plan's rulings were approved on
11-13-26.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

Read, in full, before any code:

- `prompts/business-evaluation-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session.
- `prds/business-evaluation-plan.md`: the plan. **Its approved rulings are
  settled; do not re-open them.** This phase builds § 5 (the CRM data model),
  § 3 step 3 (the client answering), and rulings BE8, BE9, BE11, BE12 and BE13.
- The client intake form, as the model for a public page that writes to the
  CRM: `forms/client_intake/` (`schemas.py`, `orchestrator.py`, `router.py`,
  `frontend/`), `core/app.py`, `frontend/shared/wizard.css` and `wizard.js`.
- The campaign links, as the model for a token link held in the application
  database: `campaigns/public.py` and `alembic/versions/0031_campaign_links.py`.
- `core/store.py`, `core/settings_registry.py`, and `comms/summarize.py` for how
  a feature switch gates an optional layer.
- `crm-plans/` (both files), `scripts/apply_crm_plan.py` and
  `tests/test_apply_crm_plan.py`, for how a CRM change is planned and applied.
- `tests/test_client_intake.py`, for how a public form is tested.

## Scope of this phase

Build the foundation, dark behind `BUSINESS_EVALUATION`:

1. **The switch.** A bool setting `business_evaluation` in the Features group,
   default false, read per request. Off: no new route answers, and no existing
   page changes. A test proves both.
2. **The CRM plan.** `crm-plans/business-evaluation.json`: the
   `CBusinessEvaluation` entity with the fields, links and status values in plan
   § 5 and ruling BE14, collaborators enabled; the two client profile fields
   (`evaluationProfile`, `evaluationProfileAt`); the reverse links on
   `CEngagement` and `CClientProfile`. Do not apply it yet.
3. **The survey definition format.** A new package, `evaluation/`. Survey
   definitions live in `evaluation/surveys/<key>.v<n>.yaml`. Each one has a key,
   a version, a title, an introduction, and sections of questions. Each question
   has an id, a label, optional help text, a type (short text, long text, single
   choice, multiple choice, number, currency, a 1-to-5 scale, yes or no),
   options where needed, and whether it is required. A loader validates every
   definition at start-up, and a test fails on an invalid one.
4. **Three survey drafts.** `business-profile.v1.yaml`, `finance.v1.yaml` and
   `marketing.v1.yaml`. Write them for the owner of a small or new business with
   no specialist training: plain words, 12 to 18 questions each, under 15
   minutes each, no question that asks for a figure the owner is unlikely to
   know without looking it up, unless it says "an estimate is fine". Each
   question exists because the analysis will need its answer; add a one-line
   comment saying what for.

**Stopping point (a).** Stop here. Report the CRM plan and the three survey
drafts for Doug's review. Doug may change the questions. Do not apply the CRM
plan to crm-test until Doug approves it.

After Doug's go-ahead:

5. **Apply the CRM plan to crm-test** with `scripts/apply_crm_plan.py` and read
   it back. Write `business-evaluation-crm-handoff.md` for production, in the
   form of `enrichment-finding-crm-handoff.md`. Production is not touched.
6. **The link store.** An Alembic migration and a store on the shared engine:
   one table for evaluation links (random token, engagement id, client profile
   id, round, the area keys, who created it, created, expires, replaced) and one
   for saved answers (link, survey key, survey version, answers, updated,
   submitted, the CRM record id). The token is never a CRM id (ruling BE12). The
   expiry comes from a new setting `evaluation_link_days`, default 30.
7. **A script to make a link for testing**, `scripts/evaluation_make_link.py`:
   given an engagement id and area keys, it creates the Business Evaluation
   records (status Sent) and a link, and prints the address. Phase 2 replaces
   it with the Send Evaluation button.
8. **The public survey page**, `/evaluation/{token}`, plain HTML, CSS and
   JavaScript, built on the shared wizard styles:
   - An expired, replaced or unknown token shows one polite page saying the link
     is no longer valid and to contact the mentor. It reveals nothing else and
     never calls the CRM.
   - The first screen shows the organization, the company name, and the consent
     checkbox (ruling BE11). Nothing can be submitted without consent.
   - Then the business profile survey, unless this engagement already has one,
     then each area survey. A list shows each survey's state: not started, in
     progress, submitted.
   - Answers save as the client goes (ruling BE13): on leaving each section, and
     on a timer. The client can close the page and return to where they were.
   - Submitting a survey checks required answers, then writes to the CRM under
     the org-wide key: the answers as JSON, the readable question-and-answer
     text, the survey version, `consentAt`, `submittedAt`, status Submitted. The
     business profile goes to the client profile. A CRM failure keeps the
     answers saved, tells the client that the answers are safe, and retries from
     the worker. A submitted survey can be viewed but not changed.
   - Honeypot and submission-token idempotency as on the public forms. No CRM
     id appears in the page or its requests.
9. **Tests**: the loader, the link states, saving, submit with the CRM in dry
   run, the CRM-failure path, the switch off, and the branding guard for the new
   page.
10. **`OPEN-ITEMS.md`**: a new item, the next free number, for the Business
    Evaluation build: what is built, what is owed (the production CRM change,
    the live check on crm-test).

**Stopping point (b).** Stop here, before closing the phase. Run the
application locally against crm-test with the switch on, make a link with the
script for a test engagement, and give Doug runbook steps to fill in and submit
the Finance survey himself. Close the phase only after Doug's report.

## Not in this phase

The Send Evaluation button and email (phase 2), anything that calls the Claude
API (phase 3), any reviewer screen (phase 4).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 00:42 | Claude (Cowork) | Created with the orchestrator, from plan revision 0.1. |
