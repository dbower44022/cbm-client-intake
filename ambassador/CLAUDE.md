# ambassador/ — the Ambassador Program

Last Updated: 11-21-26 11:47 · Revision 1.1

Members log how they spread the word; each report is recorded on the right
partner, funder or client, and referrals are credited. Decisions AM1 to AM7
(Doug, 11-21-26): `prds/Ambassador Program/ambassador-program-decisions.md`.
Build document: `prds/Ambassador Program/ambassador-program-prd.md`. Dark
behind `AMBASSADOR_PROGRAM`; what is owed is in `OPEN-ITEMS.md` #91.
Claude Code loads this file only when a session works in this folder.

## The pieces

- `frontend/index.html` + `app.js` — `/ambassador/`, the member's page: the
  shared sign-in box (`frontend/shared/signin.js`) when signed out, the form,
  the thank-you, My activity with Correct.
- `frontend/review/` — `/ambassador/review/`, the program team's list.
- `router.py` — `/ambassador/api/…`. Mentor routes gated by
  `AMBASSADOR_ALLOWED_TEAMS`, review routes by `AMBASSADOR_REVIEW_TEAMS`
  (plus Mentor Administration for the read-only tab's route).
- `lookup.py` — the form's fill-in, read **as the mentor**.
- `store.py` + migration 0053 — `ambassador_report`, written before any CRM call.
- `runner.py` — the web's one try and the worker's retries (backoff 1 minute
  to 6 hours, then failed); `delivery.py` — the chain, under the org-wide
  key through `ResumableClient`.
- `referrals.py` — new referred people, and the credit at application
  (called by the client, partner and funder form deliveries).
- `service.py` — My activity, corrections, the review list and its actions.
- `notify.py` + `email.py` — every email, from `OPS_MAILBOX`, wording
  versioned `ambassador.v1`.
- `analytics/ambassador.py` — the Ambassador Program analytics page.

## Rules kept here

- **Never tell a mentor who is a client** (AM3 item 3). The thank-you is the
  same for every outcome; the lookups return only Contact and Company fields;
  My activity reads `MINE_SELECT`, which leaves out `matchStatus` and
  `routedTo`; the Mentor Role's field rules hide them in the CRM too
  (`scripts/migrate_ambassador_roles.py`).
- **A report belongs to the sign-in**: the mentor's profile is resolved on
  the server (`sessions.service.resolve_manager_profile`), never sent by the
  browser.
- **A mentor's report never overwrites curated CRM data**: corrections stay
  on the activity; Referred by fills only when empty; the marketing opt-in
  is set true only.
- **"Ambassador Contact" sessions are never mentoring.**
  `core/session_kinds.py` is the one rule; `tests/test_ambassador.py` fails
  when a module reads `CSession` without it or an exemption with a reason.
- **The action log points at the mentor's profile** and names the activity
  in its details: `CActionLog.record` cannot name a `CAmbassadorActivity`.
- **A referred funder starts Prospective** (the existing funder status for
  "being approached"); a referred partner starts Candidate, as the partner
  form's own inbound value.
- **The partner and funder forms reuse a referred profile only when** it is
  on the same company, has Referred by, has no manager and still has its
  starting status (`referrals.referred_candidate`).
- **No possessive of the organization's name** in any wording.
- **The review list writes under the org-wide key, read back**
  (`service.write_checked`, v0.360.2). Staff are usually in the Mentor Team
  too, and the Mentor Role's field rules then drop the follow-up and review
  fields with an HTTP 200 (found on the Association 11-21-26). Never move
  those writes back to the staff member's own sign-in.

Tests: `tests/test_ambassador.py`; fakes in `tests/ambassador_fakes.py`.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 11-21-26 11:47 | Claude (Claude Code) | The review list writes under the key (v0.360.2). |
| 1.0 | 11-21-26 03:01 | Claude (Claude Code) | Created with the build (v0.360.0). |
