# Kickoff Prompt — Document Management (DOC-MGMT) Phase 3

Operating mode: DETAIL

> Drafted at the end of the Phase 2 session and REVISED 2026-07-17 after
> Doug's access-model rulings (PRD v1.3, D-08/D-09) — those rulings are
> final; do not re-litigate them. The ⚠ items below (archive failure
> contract, DOC-08 retry depth, OI scoping) are still open — get rulings
> before building each.

## Session setup (do these before any work)

1. This session targets **`dbower44022/cbm-client-intake`** (Doug's Phase 1
   ruling: the web app, not crmbuilder). Read its `CLAUDE.md` (the
   "Documents tab" bullet in the Session Management section covers Phases
   1+2 as built; the "ACCESS MODEL RULED" block in Current status has the
   rulings), `docs/`, `core/gdrive.py`, and the Documents sections of
   `sessions/frontend/app.js` + `mentoradmin/frontend/app.js`.
2. Read the governing spec: `CBM-DocMgmt-Implementation-PRD.docx` (this
   folder; **v1.3**). Sections 3.4 (Authentication and Access Model), 5
   (DOC-07, DOC-08, DOC-09 revised), 7 (D-08/D-09), 8 (open issues as of
   v1.3), and 9 (Phase 3) govern this session. The Executive Summary v1.3
   §1.2/§1.3 is the plain-language contract the build must honor.
3. Confirm the operating prerequisites, live, before building on them:
   `GDRIVE_IDENTITY=service` set on both envs' web components, the service
   account's `client_email` a Content Manager member of the "CBM
   Documents" shared drive, **all human members removed** (the ruling: no
   person is ever a member), and Phase 2 viewing verified against the real
   drive (`GDRIVE-DOCS-SETUP.md` Task 5 items 6–7). If any of these are
   not yet done, they are Doug-side actions — ask, don't work around.

## Objective

Implement Phase 3 — CRM integration and lifecycle, per the PRD (v1.3 —
note the finalized access model in §3.4 / D-08 / D-09; Doug's rulings
2026-07-16 are binding: no person is a drive member, all Drive ops run as
the service account, and Drive-side access is folder-level **Commenter**
grants mirroring CRM assignments, with mentor personnel folders granted to
NO ONE):

0. **Drive access grants (DOC-09 revised — the access model's build):**
   folder-level Commenter grants issued/revoked by the same app actions
   that change entitlements — engagement assignment (`assign_engagement`),
   co-mentor add/remove, partner/sponsor manager changes, mentor
   offboarding — plus grants on folder creation for already-entitled
   people; suppress Google's sharing-notification emails
   (`sendNotificationEmail=false`); NEVER grant on `Mentors/` (Contact)
   folders. A **nightly reconciliation job** (worker, monitoring-check
   pattern) re-derives the full grant set from the CRM and corrects both
   directions of drift (log corrections, alert on unexpected grants).
   Grant/revoke failures never fail the business action (best-effort +
   reconciliation backstop). Open in Drive stays: it now works for
   grant-holders (already correct — the button opens webViewLink; Google
   enforces the grant).
1. **Archive / restore (DOC-07):** enable the existing disabled Archive
   action. Archive sets `status = archived` in metadata AND moves the Drive
   file to an `/_Archived` subfolder of the record folder; an "include
   archived" toggle reveals archived rows; Restore reverses both steps.
   Hard deletion stays out of the app. ⚠ Decide the failure contract
   (metadata flipped but Drive move failed, or vice versa) BEFORE building —
   Phase 1's rollback rule (never leave the two inconsistent) is the
   precedent; get a ruling on which side is authoritative mid-failure.
2. **CRM link write-back (DOC-08):** on first upload for a record, populate
   the record's read-only `documentsFolderUrl` field with the record
   FOLDER's webViewLink (one stable link per record, D-05). Idempotent
   (no write when the value already matches); CRM failure never fails the
   upload — ⚠ the PRD says "queued and retried": decide whether the
   existing durable-store worker pattern is warranted or a
   best-effort-with-log write (calendar-hook precedent) satisfies CBM
   volume. Get a ruling.
   **CRM prerequisite (build first, crm-test then prod):** the
   `documentsFolderUrl` URL field on `CEngagement` + `Contact`, read-only
   in layouts (NFR-03), via the CRM team / crmbuilder handoff — write a
   spec doc in this repo's root (the `csession-calendar-field.md`
   precedent), and note the folder's webViewLink must be captured at
   folder-creation time (Phase 1/2 code doesn't store it — a small
   `app_document` or folder-cache addition, or a Drive `files.get` on the
   folder id).
3. **Open-issue scoping (PRD §8 as of v1.3, resolve with Doug, build only
   what he rules in):** OI-02 link-existing-Drive-files (Drive picker,
   metadata row without upload — "a likely fast follow"); OI-05 the
   orphan/duplicate report (largely closed by the access model — only
   admin-console actions can create drive-side surprises now); OI-07
   whether to set `copyRequiresWriterPermission` on granted folders
   (hides download/print/copy from commenters in Drive's UI). OI-04 is
   superseded (no per-user OAuth exists).

## Out of scope this session

A web upload page for non-app users (OI-03). Document content search/OCR.
Retention/purge policies. Anything Phase 4+ or not in the PRD.

## Working rules (DETAIL mode)

- One consequential thing at a time; surface PRD-vs-architecture conflicts
  before resolving them (the ⚠ items above are known ones — get rulings).
- Repo conventions hold: minimal surgical edits, no new dependencies without
  confirmation, pytest + stub-harness verification, ruff clean, commit but
  never push.

## Definition of done

- DOC-09 (grants + reconciliation) + DOC-07 + DOC-08 implemented (plus
  whatever OI-02/OI-05/OI-07 scope Doug rules in); tests passing; ruff
  clean.
- Grants verified live: assign a mentor → their folder appears in Shared
  with me at Commenter (can comment, cannot upload/edit); unassign →
  access gone; the nightly reconciliation corrects a hand-made drift.
- The `documentsFolderUrl` CRM field spec handed off (and, if built in
  time, the write-back verified live on crm-test).
- Live verification against the real shared drive: archive a document
  (file lands in `/_Archived`, row leaves the default list, toggle reveals
  it), restore it, and confirm the CRM link write-back on a first upload.
- CHANGELOG/CLAUDE.md/DEPLOYMENT.md/GDRIVE-DOCS-SETUP.md updated; commit(s)
  staged with clear messages; state the next required step. This closes the
  PRD's phased plan — note any follow-on work as new open items rather than
  drafting a Phase 4 prompt.
