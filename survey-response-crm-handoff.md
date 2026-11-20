# CRM handoff — feedback surveys (Business Evaluation phases 8 and 9): `CSurveyResponse`

Last Updated: 11-20-26 02:20 · Revision 0.1 — see change log at the end.

One new record type: one Survey Response record per submitted feedback
survey. Each response is linked to what it is about, which is one of:

- the engagement and its mentor at the time;
- the event;
- the released Business Evaluation.

Each is also linked to the contact who answered. The change adds role grants
for four roles. Design: `prds/business-evaluation-plan.md` § 5 *Added
11-16-26* and rulings BE31 and BE32. Decision 1 of phases 8 and 9 was approved
by Doug on 11-20-26, with option A. Build prompt:
`prompts/business-evaluation-phase8-9-feedback-prompt-v0.1.md`.

**Additive.** The change adds one entity, 12 fields and 5 links, switches on
Multiple Assigned Users and Collaborators, and makes 4 role grants. Nothing is
removed, renamed or narrowed. It is safe to apply ahead of the code: the
application feature-detects the entity (`feedback/service.entity_available`)
and stays dark behind `FEEDBACK_SURVEYS`. **This needs
`business-evaluation-crm-handoff.md` first**, because one link points at
`CBusinessEvaluation`.

## 0. Current state

| CRM | State | Evidence |
|---|---|---|
| The Business Mentors Association (the test system) | **Not applied.** Dry run 11-20-26 01:50, fingerprint `b3aff8f4964e`. It is applied by `./scripts/evaluation_bma.sh feedback-apply` in the combined check. | The applier's dry-run output. |
| crm-test | **Not applied.** Testing is on the Association. | — |
| Production | **Not applied.** It goes at a Sunday 17:00 UTC slot, after the Association's check. | — |
| Boston | **Owed** with its release. | — |

Decided here, and said so:

- **No field is Read-only** (ruling 40). The application writes them all,
  including `needsFollowUp`.
- **`moment`** has the options Engagement Closed, Session Milestone, Event,
  Evaluation Released and On Demand, plus an empty value. "Session
  Milestone" replaces plan § 5's "Third Session", because the number of
  sessions is a setting (decision 6). The application writes a moment only
  after checking that the live list has it.
- **`recommendScore`** is a whole number from 0 to 10. It is empty when the
  question was not answered.
- **`needsFollowUp`** and **`followUpDone`** are audited, and the stream is on.
- **The grants (decision 1, A):**
  - `CustomAppAPIRole`: create, read all, edit all.
  - **Mentor Role**: read own only. "Own" reaches every response that
    carries the mentor in `assignedUsers`. The application stamps a response
    about an engagement with the engagement's assigned users, so the mentor
    and the co-mentors read it. Event feedback carries no stamp, so no mentor
    reads it.
  - **Mentor Administration Role** and **Marketing Admin Role**: read all and
    edit all. They need edit to mark a follow-up done.
  - No role is given delete.

## 1. Names

The entity is `CSurveyResponse`, typed as `SurveyResponse`: the CRM adds the
`C`. Its fields and its five links are stored as written: `engagement`,
`mentorProfile`, `event`, `contact` and `businessEvaluation`.

The reverse links on the custom entities are stored as typed:

- `CEngagement.surveyResponses`;
- `CMentorProfile.surveyResponses`;
- `CEvent.surveyResponses`;
- `CBusinessEvaluation.surveyResponses`.

The reverse link on `Contact` gains a `c`: `Contact.cSurveyResponses`.

## 2. Apply

From the build computer (Doug's desktop computer, host name
doug-System-Product-Name), in `~/Dropbox/Projects/cbm-client-intake`:

    PYTHONPATH=. uv run python scripts/run_with_admin.py --env <the CRM's env file> \
        scripts/apply_crm_plan.py crm-plans/survey-response.json              # dry run
    ... crm-plans/survey-response.json --apply --production --expect b3aff8f4964e
    PYTHONPATH=. uv run python scripts/run_with_admin.py --env <the CRM's env file> \
        scripts/migrate_feedback_roles.py --apply

For the Association, `./scripts/evaluation_bma.sh feedback-apply` runs the
plan and the grants. For production, run them from inside the deployed web
container, as the header of `scripts/apply_crm_plan.py` describes. The
fingerprint covers the work still to do, so recheck it with a dry run on each
CRM.

## 3. Check

- `GET /Metadata` reads:
  - `entityDefs.CSurveyResponse.links` with the five links;
  - `entityDefs.CEngagement.links` with `surveyResponses`.
- The org-wide key reads `GET /CSurveyResponse?maxSize=1` and gets HTTP 200.
- As a real non-admin mentor (Joe Mentor), the Feedback tab on one of his
  engagements lists that engagement's responses. As a real non-admin in the
  Mentor Administration Team, the mentor's Feedback tab lists every response
  and **Mark follow-up done** saves.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-20-26 02:20 | Claude (Claude Code) | Created with phases 8 and 9. |
