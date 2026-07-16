# Kickoff Prompt — Document Management (DOC-MGMT) Phase 3 (DRAFT)

Operating mode: DETAIL

> Drafted by Claude at the end of the Phase 2 session (2026-07-16), per the
> Phase 2 prompt's definition of done. Review before use — especially the
> web-adaptation decisions marked ⚠ and the open-issue scoping calls, which
> Phase 2's rulings did not cover.

## Session setup (do these before any work)

1. This session targets **`dbower44022/cbm-client-intake`** (Doug's Phase 1
   ruling: the web app, not crmbuilder). Read its `CLAUDE.md` (the
   "Documents tab" bullet in the Session Management section covers Phases
   1+2 as built), `docs/`, `core/gdrive.py`, and the Documents sections of
   `sessions/frontend/app.js` + `mentoradmin/frontend/app.js`.
2. Read the governing spec: `CBM-DocMgmt-Implementation-PRD.docx` (this
   folder; v1.2 at drafting time). Sections 5 (DOC-07, DOC-08), 8 (open
   issues), and 9 (Phase 3) govern this session.
3. Confirm Phase 2 is verified live first (view a PDF/image/Google-native
   doc against the real shared drive — `GDRIVE-DOCS-SETUP.md` Task 5
   item 6). Phase 3 builds on trusted viewing.

## Objective

Implement Phase 3 — CRM integration and lifecycle, per the PRD:

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
3. **Open-issue scoping (PRD §8, resolve with Doug, build only what he
   rules in):** OI-02 link-existing-Drive-files (Drive picker, metadata row
   without upload — "a likely fast follow"); OI-05 the orphan/duplicate
   report ("decide whether the report is in scope for Phase 3"); OI-04
   scope narrowing (evaluate only — the shared-drive listing likely keeps
   full `drive` scope).

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

- DOC-07 + DOC-08 implemented (plus whatever OI-02/OI-05 scope Doug rules
  in); tests passing; ruff clean.
- The `documentsFolderUrl` CRM field spec handed off (and, if built in
  time, the write-back verified live on crm-test).
- Live verification against the real shared drive: archive a document
  (file lands in `/_Archived`, row leaves the default list, toggle reveals
  it), restore it, and confirm the CRM link write-back on a first upload.
- CHANGELOG/CLAUDE.md/DEPLOYMENT.md/GDRIVE-DOCS-SETUP.md updated; commit(s)
  staged with clear messages; state the next required step. This closes the
  PRD's phased plan — note any follow-on work as new open items rather than
  drafting a Phase 4 prompt.
