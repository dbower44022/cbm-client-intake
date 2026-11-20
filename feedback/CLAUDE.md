# feedback/ — feedback surveys

Last Updated: 11-20-26 03:20 · Revision 1.0

Feedback surveys are the second survey purpose on the survey engine. The
rulings are BE29 to BE33 in `prds/business-evaluation-plan.md`. This package
was built in phases 8 and 9 of the Business Evaluation build, in one session
(Doug's choice B). Doug decided the eight questions at stopping point (a) on
11-20-26, and they are listed below. What is owed is in `OPEN-ITEMS.md` #83.
Claude Code loads this file only when a session works in this folder.

## The decisions (11-20-26), as built

1. **CRM:** `CSurveyResponse` (`crm-plans/survey-response.json`,
   `scripts/migrate_feedback_roles.py`, `survey-response-crm-handoff.md`).
   - The Mentor Role reads own only. A response about an engagement carries
     the engagement's `assignedUsers`; event feedback carries none.
   - The Mentor Administration Role and the Marketing Admin Role read and
     edit every response (option A).
2. **The surveys:** `surveys/*.yaml`, each with a `# For:` line on every
   question.
   - Every survey opens with `recommend`, the 0-to-10 score and the only
     required question. The loader refuses any other first question.
   - A score of 6 or below sets the follow-up flag. So does a yes to
     `contact_me` (mentoring and event surveys) or to `talk_to_mentor` (event
     survey).
3. **The screens**, all drawn by `frontend/shared/feedback.js`:
   - **Client Management's Feedback tab** (`DomainConfig.feedback_tab`,
     mentor domain only): the mentor reads their engagement's responses.
     **Send feedback survey** opens the composer from the mentor's own
     mailbox (`sending.prepare_for_composer`).
   - **Mentor Administration's Feedback tab** on the mentor: staff read every
     response about the mentor's engagements, mark follow-ups done, and send
     the mentoring or the evaluation survey from the shared mailbox.
   - **Event Administration:** the event's **Feedback** tab lists its
     responses. The Follow-up tab's **Survey** card sends each attendee their
     own link (`event_send.py`) in place of the `EventSurvey` template.
4. **Alerts** (`alerts.py`): one email to each member of the responsible team
   at once, from the shared mailbox.
   - Mentoring and evaluation feedback go to the Mentor Administration Team;
     event feedback goes to the Marketing Admin Team.
   - A team with no members falls back to `ALERT_EMAIL_TO`.
   - The home page's Needs you list gets a *Feedback to follow up* row
     (`portal/router._feedback_items`), which opens the oldest open one.
   - **Mark follow-up done** needs a note. It writes `followUpDone`,
     `followUpNote` and `followUpDoneAt` as the staff member, and records the
     old and new values in the action log.
5. **What was sent** (`store.py`, migration 0052): `feedback_send` holds one
   row per moment per person, and its unique `send_key` means never twice.
   `feedback_alert` holds one row per alerted response.
6. **The moments** (`moments.py`, the worker every
   `FEEDBACK_SWEEP_SECONDS`), each with its own switch:
   - **closing:** Completed, Inactive or Abandoned, with at least one
     Completed session; the quiet period does not apply;
   - **session milestone:** the `FEEDBACK_SESSION_COUNT`-th Completed session
     (default 3), the day after it;
   - **event:** Public events, not Cancelled, 24 hours to 14 days after they
     end, to each registration marked Attended;
   - **evaluation:** one survey per round, 3 days after the round's first
     release.

   Every moment counts only if it happened within `FEEDBACK_LOOKBACK_DAYS`
   (default 7). When closing and the milestone come in one pass, only the
   closing survey goes.
7. **Recipients:**
   - The engagement's primary client contact, else the first client contact
     with an address. For events, the address the attendee registered with.
   - The CRM's opted-out flag is honoured. A CBM member (Mentor-typed, or an
     address on `MENTOR_EMAIL_DOMAIN`) is never surveyed. No marketing opt-in
     is needed.
   - Automatic sends come from the shared mailbox, with the wording in
     `email.py` (version `feedback.v1`).
8. **Analytics** (`analytics/feedback.py`):
   - A Feedback system page for the Analytics Admin, Mentor Administration and
     Marketing Admin teams.
   - Two panels on the mentor's record tab, for staff only.
   - Survey Responses in the metric builder.
   - **Mentors see no figures.**

## Rules kept here

- **The quiet period** (`FEEDBACK_QUIET_DAYS`, default 30, 0 turns it off) is
  counted per lower-cased address over `sent` rows. It skips only automatic
  sends other than the closing survey, and records the skip with a reason.
  - A send by hand is never stopped by it.
  - A send by hand does count towards it. That includes a mentor's composer
    send, counted when the email is made, even if the mentor never presses
    Send.
- **The event Survey card and the sweep share one send key**
  (`event:<event>:<registration>`), so an attendee never gets the survey
  twice.
- **Submit is replay-safe.** `service._existing` finds a response with the
  same survey, contact, engagement or event, and submit time before creating
  one.
- **Off means as before.** While `FEEDBACK_SURVEYS` is off:
  - every route answers 404, and no tab or card changes;
  - the Feedback page and the feedback metrics are out of Analytics
    (`analytics.registry.SWITCHED_METRICS`, `PageSpec.switch`);
  - the sweep sends nothing.
- **`surveys/` imports nothing from here** (`tests/test_survey_engine.py`).
- The survey files' text may use `{{org}}`. The engine fills it in on the
  page (`surveys/router._survey_view`), and `service.deliver` fills it in in
  `answersReadable`.

Tests: `tests/test_feedback.py`, `tests/test_feedback_store_pg.py`; fakes in
`tests/feedback_fakes.py`.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-20-26 03:20 | Claude (Claude Code) | Created with phases 8 and 9. |
