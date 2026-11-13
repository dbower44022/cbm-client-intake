# evaluation/ — Business Evaluation

Last Updated: 11-13-26 10:40 · Revision 1.0

Detail for the Business Evaluation offering: the survey definitions, the
evaluation links, and the client's public survey page at `/evaluation/{token}`.
Claude Code loads this file only when a session works in this folder. The plan
is `prds/business-evaluation-plan.md` (rulings BE1–BE22, all approved
11-13-26, settled); the build runs phase by phase from
`prompts/business-evaluation-build-orchestrator-v0.1.md`; what is owed is
`OPEN-ITEMS.md` #83.

## What phase 1 built (v0.324.0)

- **Dark behind `BUSINESS_EVALUATION`**, read per request: `core/app.py`'s
  `_dark_evaluation` middleware answers 404 on `/evaluation/…`,
  `/evaluation-assets/…` and `/api/evaluation/…` while it is off.
- **Survey definitions are versioned files** (ruling BE9):
  `surveys/<key>.v<n>.yaml`, validated by `surveys.py` (`load_all`), loaded
  once at start-up by `router.load_surveys`. An invalid file is logged as an
  ERROR and the pages answer "no longer valid"; `tests/test_evaluation_surveys.py`
  is what stops one shipping. **Every question carries a `# For:` comment**
  saying what the analysis needs it for; the test fails without it. **Quote
  `"Yes"` and `"No"` options**: bare, YAML reads them as booleans (the loader
  refuses them). A question the pilot clients have answered is never edited:
  a change is a new version file. (Version 1 of Finance was edited 11-13-26,
  before any real client, to add the subscription option; Doug's request.)
- **The business profile** (`business-profile`) is answered once per
  engagement (BE8) and is written to `CClientProfile.evaluationProfile`
  (JSON) and `evaluationProfileAt`; an area survey goes to its own
  `CBusinessEvaluation` record.
- **The link is a random token in the application database, never a CRM id**
  (BE12): `store.py`, migration 0044 (`evaluation_link`,
  `evaluation_answer`), the shared pool, reset nightly on the sandbox. The
  link snapshots the company name so an open never calls the CRM. A link that
  is malformed, unknown, expired (`EVALUATION_LINK_DAYS`) or replaced gets one
  polite page and one 404 wording, and that check never calls the CRM.
- **Consent first** (BE11): nothing saves or submits without it; its time is
  written to every submitted record as `consentAt`.
- **Answers save as the client goes** (BE13): `PUT …/answers/{key}` on each
  section change, every 20 seconds and on page hide; saves are not counted
  against the intake rate limit and are capped in the router (256 KB). The
  first save of an area moves its record to In Progress (best-effort).
- **Submit** checks types and required answers (server and page), locks the
  survey, and writes the CRM under the org-wide key. A refusal keeps the
  answers, tells the client they are safe, and the worker retries
  (`service.run_retry_cycle`, every `EVALUATION_RETRY_SECONDS`, backoff 1m to
  6h). The worker leaves a fresh submission to its own request for two
  minutes (`store.WEB_GRACE`). A submitted survey can be viewed, never changed.
  Honeypot `company_url` and the submission token as on the public forms.
- **After a refused submit, Submit shows on every section** (Doug's choice B,
  11-13-26): every missing answer is marked, the message names how many and in
  which sections, and the first pass stays Next, Next, Submit.
- **Business Evaluation records carry the engagement's `assignedUsers`**, set
  at creation and kept by the nightly reconciliation
  (`assignments/stamps.related_records(…, with_evaluations=True)`, read once
  per pass from the CRM's links).
- **Test links**: `scripts/evaluation_make_link.py <engagement id> finance
  marketing` until phase 2's Send Evaluation button.

## The CRM

`crm-plans/business-evaluation.json` (fingerprint `89d89d28b53b` on crm-test)
and `scripts/migrate_evaluation_roles.py`; handoff
`business-evaluation-crm-handoff.md`. **No field is Read-only**, the draft
report included (ruling 40); `engagement` and `clientProfile` are required by
the application, not the CRM. Multiple Assigned Users and Collaborators are
switched on through the plan's `entityParams` (an entity update, never a
create).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-13-26 10:40 | Claude (Claude Code) | Created at the close of phase 1 (v0.324.0). |
