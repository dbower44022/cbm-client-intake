# Kickoff Prompt — Document Management (DOC-MGMT) Phase 2 (DRAFT)

Operating mode: DETAIL

> Drafted by Claude at the end of the Phase 1 session (2026-07-16), per the
> Phase 1 prompt's definition of done. Review before use — especially the
> web-adaptation decisions marked ⚠, which Phase 1's rulings did not cover.

## Session setup (do these before any work)

1. This session targets **`dbower44022/cbm-client-intake`** (Doug's Phase 1
   ruling: the web app, not crmbuilder — the Documents tab lives in the
   session tools). Read its `CLAUDE.md`, the "Documents tab" bullet in the
   Session Management section, and `docs/`, `core/gdrive.py`,
   `sessions/frontend/app.js` ("Documents tab" section).
2. Read the governing spec: `CBM-DocMgmt-Implementation-PRD.docx` v1.0 (this
   folder). Sections 5 (DOC-02 completion, DOC-03, DOC-04, DOC-05, DOC-06),
   6, and 9 (Phase 2) govern this session. Do not implement Phase 3
   (archive, CRM write-back) — do not build ahead.
3. Confirm Phase 1 is ACTIVATED live first (shared drive + `drive` DWD scope
   + `GDRIVE_DOCS` + a verified live upload). Phase 2 builds on real files.

## Objective

Implement Phase 2 — Viewing, per the PRD, adapted to the web architecture:

1. **In-app viewing (DOC-03 — the feature's primary requirement):** a View
   action on each document row renders the file inside the app. ⚠ Web
   adaptation to decide: the PRD's QPdfView/QWebEngineView are desktop
   widgets — in the browser this becomes an app proxy endpoint
   (`GET .../documents/{id}/content`, streaming `files.get?alt=media` under
   the signed-in user's delegated identity, mentorprofile-photo precedent)
   rendered in an embedded viewer (browser-native PDF view / `<img>` /
   iframe). Formats that can't render fall back to Open in Drive with a
   clear message.
2. **Cache (DOC-06):** key `fileId + modifiedTime`; changed modifiedTime
   invalidates. ⚠ Web adaptation to decide: App Platform's filesystem is
   ephemeral (a per-user desktop cache doesn't exist here) — propose either
   a server-side disk cache (fast, resets harmlessly on redeploy; size cap +
   LRU per the PRD) or HTTP caching headers on the proxy (ETag =
   fileId+modifiedTime, `Cache-Control: private`) letting each browser hold
   the bytes. Surface the trade-off before building.
3. **Google-native formats (DOC-04):** files with no native bytes (Docs/
   Sheets/Slides MIME types) are viewed via `files.export` to PDF, cached
   under the same invalidation rules. `checksum_md5` stays null;
   `modified_time` is the sole invalidation key.
4. **Open in Drive (DOC-05):** enable the existing disabled action — opens
   the row's stored `web_view_link` in a new tab (authorization happens at
   click time via the user's Workspace session).
5. **Lazy modifiedTime refresh (DOC-02 completion):** when the Documents tab
   loads, one `files.list` query scoped to the record folder refreshes each
   row's `modified_time` (and flags files changed since last cache). Must
   not block the initial render from metadata.

## Out of scope this session

Archive/restore (DOC-07), CRM write-back (DOC-08), linking existing Drive
files (OI-02), the orphan/duplicate report (OI-05). The Archive button stays
disabled.

## Working rules (DETAIL mode)

- One consequential thing at a time; surface PRD-vs-architecture conflicts
  before resolving them (the ⚠ items above are known ones — get rulings).
- Repo conventions hold: minimal surgical edits, no new dependencies without
  confirmation, pytest + stub-harness verification, ruff clean, commit but
  never push.
- Performance targets (NFR-01): cached view < 500 ms; first fetch of a
  10 MB file < 3 s.

## Definition of done

- DOC-03/04/05/06 + the lazy refresh implemented; tests passing; ruff clean.
- Live verification against the real shared drive: view a PDF + an image +
  a Google-native doc (export path), confirm cache-hit behavior, Open in
  Drive, and a modifiedTime refresh after editing a file in Drive.
- CHANGELOG/CLAUDE.md/DEPLOYMENT.md updated; commit(s) staged with clear
  messages; state the next required step and draft the Phase 3 kickoff
  prompt.
