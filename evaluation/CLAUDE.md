# evaluation/ — Business Evaluation

Last Updated: 11-15-26 23:20 · Revision 1.5

Detail for the Business Evaluation offering. Claude Code loads this file only
when a session works in this folder. The plan is
`prds/business-evaluation-plan.md` (rulings BE1–BE23, all approved 11-13-26,
settled); the build runs phase by phase from
`prompts/business-evaluation-build-orchestrator-v0.1.md`; what is owed is
`OPEN-ITEMS.md` #83.

## Since phase 2b: a survey purpose on the survey engine (ruling BE23)

The definition format and loader, the link store and saved answers, the
submit retry and the client's public page moved to the survey engine,
`surveys/` (see `surveys/CLAUDE.md`). **Business Evaluation is its first
survey purpose**, registered in `purpose.py` (key `business-evaluation`,
switch `BUSINESS_EVALUATION`, settings `EVALUATION_LINK_DAYS` and
`EVALUATION_RETRY_SECONDS`, which kept their names). What stays here:

- `purpose.py`: the registration, the page's words (phase 1's, unchanged),
  and `surveys()` / `load_surveys()` for this purpose's definitions.
- `surveys.py` and `surveys/*.yaml`: the definitions, with the `area` key,
  the six areas and the required business profile as loader rules.
- `service.py`: the surveys a link opens, the CRM write on submit
  (`deliver`), the In Progress step on a first save.
- `sending.py` and `email.py`: phase 2's mentor side. Links are made with
  the engine's store: `entity_type` `CEngagement`, `record_id` the
  engagement, `display_name` the company, and `data` holding
  `client_profile_id`, `round`, `area_keys` and `profile_needed`.
- `router.py`: **the old address**. `/evaluation/{token}` answers 301 to
  `/survey/{token}`, so a link emailed before phase 2b still opens; 404
  while the switch is off. The old `/api/evaluation/…` and
  `/evaluation-assets/…` addresses are gone.
- `scripts/evaluation_make_link.py`.

The phase 1 and 2 notes below are as built; where they name `store.py`,
`router.load_surveys`, the `_dark_evaluation` middleware, migration 0044's
table names or the `/evaluation/{token}` page, read the engine's equivalent.

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
  marketing`, which since phase 2 runs the same `sending.send` as the button.

## What phase 2 built (v0.328.0)

- **The mentor side is Client Management's Evaluations tab**
  (`DomainConfig.evaluations_tab`, mentor domain only; the routes live in
  `sessions/router.py` and answer 404 while the switch is off). The logic is
  `sending.py`: the tab's rows, the answers view, Send, Resend, Expire and
  Record a decline. **Reads run as the user**; the Mentor Role holds create,
  read own, edit own and stream own on `CBusinessEvaluation`.
- **Records are created as the mentor**, stamped with the engagement's
  `assignedUsers`. The Mentor Role's Assignment Permission is `team`, so a
  stamp naming someone outside the mentor's teams is refused: only that 403
  is retried under the org-wide key.
- **The link leaves the server only inside the email** (BE12): Send and Resend
  return the composer's subject and body (`email.py`, `invitation.v1`, wording
  approved by Doug 11-13-26), never the link on its own. A wording change is a
  new `VERSION` and a release; the wording lives here, not in a CRM template
  (Doug's choice). The mentor edits the email in the shared composer
  (`pre.bodyHtml`) and nothing is sent until they press Send.
- **Resend carries the client's saved answers and consent to the new link**
  (Doug's choice 11-13-26; `store.replace_link`, one transaction) and ends the
  old one; Expired areas reopen, In Progress where the client had begun.
  **Expire** ends the link and sets Sent and In Progress records to Expired.
  **Record a decline** sets Declined on everything not submitted and ends the
  link. A wrong recipient is handled by Expire and a new Send, never Resend.
- **Every action goes to `core/action_log.py`** with old and new values in
  `details["fields"]`, under the existing Record Edit and Status Change
  categories: `CActionLog.category` is a CRM enum, and a new value would be
  refused.
- Tests: `tests/test_evaluation_mentor.py`; the in-memory store is
  `tests/survey_fakes.MemoryStore` (since phase 2b).

## What phase 3 built (v0.332.0)

- **The analysis prompts and rubrics are versioned files** (BE9), beside the
  surveys: `prompts/<key>.v<n>.yaml` (the system text, `{{org}}` filled in,
  naming its rubric) and `rubrics/<key>.v<n>.yaml` (dimensions, each with
  levels 1 to 5 and the questions it rests on). `analysis.load_all` checks
  them; tests check every rubric's `informed_by` names a real question, and
  that the Finance and Marketing prompts share their rules word for word
  except the area's own words. **A prompt or rubric a real client's report
  was written from is never edited**: a change is a new version. Doug
  11-14-26: they stay files through the pilot and become editable in System
  Settings later (plan § 7 question 6).
- **The voice is Doug's, 11-14-26**: questionnaire answers are impressions,
  so a report names areas worth looking at, quotes what points to each and
  asks what would settle it; it never states a cause or figure the survey
  cannot show. Round 1 of the samples was rejected as too authoritative.
- **The report** (`report.py`, BE16): `Report` is the structured output,
  `render` the `draftReport` HTML. "Points to check" sits in
  `<div data-internal="true">`, which the CRM keeps (read back on crm-test),
  for phase 5's client version to drop. The missing-information section is
  headed "Questions to explore".
- **The worker pass** (`analysis.run_analysis_cycle`, in `worker.py` beside
  the engine's retry): Submitted records, ten a pass, one
  `client.beta.messages.parse` call per area (`EVALUATION_MODEL`, adaptive
  thinking, effort high, `fallbacks: "default"`). **The CRM status is the
  queue**: Draft Ready on success, Analysis Failed with `analysisError` on
  failure, Retry sets Submitted. A CRM error leaves the record Submitted for
  the next pass, which then pays for the call again — hence the pass's
  60-second CRM timeout. On only when `enabled()`: the switch,
  `EVALUATION_ANALYSIS_SECONDS` above 0, the Anthropic integration in use, a
  key, not a dry run.
- **No contact details reach the Claude API**: `analysis.scrub` removes email
  addresses, phone numbers and street addresses from every answer; a test
  reads the request sent. The company name and business profile are sent.
- **An area submitted before the business profile waits** up to 24 hours
  (`PROFILE_WAIT`), then is analyzed without it, flagged in Points to check.
- **The mentor's email** (`make_notifier`, Doug's choice A): from
  `OPS_MAILBOX` to the engagement mentor's `cbmEmail`, linking
  `?tab=evaluations`. No shared mailbox, no email. Never fails the analysis.
- **The draft never reaches the client** (BE17): a test fails if any module
  besides `analysis.py`, `report.py` and `sending.py` names `draftReport`.
- **An Anthropic key must be scoped to a workspace**: an unscoped key is
  refused ("must include the anthropic-workspace-id header"), found 11-14-26.
- **Samples**: `scripts/evaluation_sample_reports.py <engagement id>` sends,
  submits made-up bakery answers and analyzes, on crm-test only; about $0.12
  per area.
- Tests: `tests/test_evaluation_analysis.py`.

## What phase 4 built (v0.336.0)

- **Review and approval are `review.py`** (BE17, BE18), behind the
  Evaluations routes in `sessions/router.py`: `PUT …/evaluations/{id}/report`,
  `POST …/{id}/approve`, `GET`/`POST …/rounds/{n}/review-session`; 404 while
  the switch is off.
- **Every reviewer edits `reviewedReport` as themself**: the CRM decides,
  through the engagement's `assignedUsers` stamp and the Mentor Role's
  edit own. `review.py` never names `draftReport`; the draft reaches the
  page only through `sending.answers_view`, shown read-only beside the
  editor.
- **A save carries the text the reviewer opened** (`base`); a different
  stored text is someone else's newer save and answers 409, naming them.
  The response returns the text as stored, which is the next save's `base`.
- **A saved change to an Approved report withdraws the approval** (Doug,
  11-14-26): Draft Ready, `approvedAt` and `approvedBy` cleared. Message
  wording approved by Doug 11-15-26.
- **Only the engagement's mentor approves**: the login on the engagement's
  mentor profile (read under the org-wide key, which a co-mentor may need).
  Administrators get no exemption. `approvedBy` and `reviewSession` writes
  refused as the user retry under the org-wide key, on a 403 only.
- **A save that drops the `data-internal` marker but keeps the Points to
  check heading is warned**; deleting the whole section is not. The marker
  survives the editor and the CRM (checked 11-15-26).
- **No images in the report** (Doug, 11-14-26): the editor has no upload
  hook, so a pasted image is removed with a notice.
- **The review session**: a round is ready when no record is Submitted,
  Analysis Failed or Draft Ready and one is Approved. The dialog offers the
  engagement's upcoming Scheduled sessions or a new one; a new one is
  linked after its save (`evlReviewRound` in `app.js`), a failed link a
  warning on a saved session. The session goes on every record of the round.
- Tests: `tests/test_evaluation_review.py`.

## What phase 5 built (v0.338.0)

- **Release is `release.py`** (BE19, BE20), behind `GET`/`POST
  …/evaluations/{id}/release`, `GET …/actionitems` and `PUT
  …/actionitems/{id}` in `sessions/router.py`; 404 while the switch is off.
  Doug's choices 11-15-26, all as recommended.
- **Only the engagement's mentor releases, only an Approved report whose
  round has its review session.** A released report (Reviewed with Client)
  is final: `review.save_report` refuses it and the review screen shows it
  read-only.
- **The client version is made from `reviewedReport`, never the draft**:
  `client_body` drops every element carrying `data-internal` (any tag) and
  the report's own `<h2>`; `client_document` adds the header, *Action items
  we agreed* and the closing note. `release.py` must not name the draft
  field (the BE17 guard test).
- **A PDF made by Google Docs**: `DriveClient.html_to_pdf` uploads the HTML
  as a temporary Google Doc in the engagement's folder, exports it, deletes
  it; `docs.service.file_generated_pdf` files it as *Evaluation report*
  (accepted, never offered in the upload picker) and returns a same-named
  document instead of filing a second. Release needs `GDRIVE_DOCS`.
- **Order, for a safe retry**: the items (one with the same title already on
  the evaluation is skipped), then the document, then the status.
- **Action items are `CActionItem`** (`crm-plans/action-item.json`): owner is
  a Contact, chosen from the engagement's client contacts and its mentor's
  and co-mentors' Contacts (`owner_choices`); due dates default from the
  item's "When" after the review session. Written as the user, a 403
  retried under the org-wide key; stamped with the engagement's
  `assignedUsers`; in the nightly reconciliation
  (`stamps.related_records(…, with_action_items=True)`). Feature-detected.
- **The email** (`email.release`, `release.v1`, wording approved 11-15-26)
  opens in the composer with the PDF attached through the composer's new
  `pre.documents`.
- **Tests on the Business Mentors Association's system** (Doug, 11-15-26):
  `scripts/evaluation_bma.sh` (check, apply, samples).
- Tests: `tests/test_evaluation_release.py`.

## The CRM

`crm-plans/business-evaluation.json` (fingerprint `89d89d28b53b` on crm-test)
and `scripts/migrate_evaluation_roles.py`; handoff
`business-evaluation-crm-handoff.md`. Phase 5: `crm-plans/action-item.json`
(fingerprint `5bf3e2de43a8`), the same role script, handoff
`action-item-crm-handoff.md`. **No field is Read-only**, the draft
report included (ruling 40); `engagement` and `clientProfile` are required by
the application, not the CRM. Multiple Assigned Users and Collaborators are
switched on through the plan's `entityParams` (an entity update, never a
create).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-13-26 10:40 | Claude (Claude Code) | Created at the close of phase 1 (v0.324.0). |
| 1.1 | 11-13-26 13:55 | Claude (Claude Code) | Phase 2, the mentor side (v0.328.0). |
| 1.2 | 11-13-26 14:53 | Claude (Claude Code) | Phase 2b: the survey engine moved out to `surveys/` (ruling BE23). |
| 1.3 | 11-14-26 13:35 | Claude (Claude Code) | Phase 3, the analysis (v0.332.0). |
| 1.4 | 11-15-26 12:20 | Claude (Claude Code) | Phase 4, review and approval (v0.336.0). |
| 1.5 | 11-15-26 23:20 | Claude (Claude Code) | Phase 5, release and action items (v0.338.0). |
