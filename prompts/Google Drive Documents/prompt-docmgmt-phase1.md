# Kickoff Prompt — Document Management (DOC-MGMT) Phase 1

Operating mode: DETAIL

## Session setup (do these before any work)

1. Confirm with me which repository this session targets and which CLAUDE.md to read. My assumption is `dbower44022/crmbuilder` hosts the custom mentor application, but wait for my confirmation before reading anything or writing any code.
2. If parallel processes may be active, perform a fresh `rm -rf` + re-clone of the repo before starting.
3. Read the governing spec: `CBM-DocMgmt-Implementation-PRD.docx` v1.0 (I will tell you its location in the repo). Sections 3 (Architecture), 4 (Data Model), 5 (DOC-01, DOC-02, DOC-09), and 9 (Phase 1) govern this session. Do not implement anything from Phase 2 or Phase 3.

## Objective

Implement Phase 1 — Foundation of the Google Drive document management feature, per the PRD:

1. **OAuth flow (DOC-09):** Per-user OAuth 2.0 loopback flow using the system browser. Refresh token stored via the OS keyring (`keyring` library) — never plaintext config. Include a "disconnect Google account" action that revokes and clears credentials. Expired/revoked tokens must produce a clear re-authorization prompt.
2. **Schema migration:** Create the `app_document` table exactly as specified in PRD Section 4, including the composite index on `(entity_type, record_id, status)`.
3. **Upload (DOC-01):** Upload a local file to the shared drive under `/{Entity Type}/{Record Name} ({recordId})/`, creating folders as needed and caching folder IDs. Native MIME type preserved — never request conversion to Google editor formats. Resumable upload for files over 5 MB. Capture `fileId`, `webViewLink`, `modifiedTime`, `md5Checksum`; write the metadata row atomically with the upload. Rollback rule: a Drive file with no metadata row gets deleted; a metadata row is never written without a confirmed Drive file.
4. **Per-record list (DOC-02, partial):** Render the document list for the open record from the metadata table only (no Drive calls). Columns: original filename, doc_type, uploader, upload date. Actions View / Open in Drive / Archive appear as disabled placeholders — they are Phase 2/3.

## Out of scope this session

In-app viewing, caching, Google-native export, Open in Drive, archive, CRM write-back, and the lazy modifiedTime refresh. Do not build ahead.

## Manual prerequisites (mine, not yours)

I will complete these before or during the session; ask me to confirm each before the code path that depends on it:

- Google Cloud project with Drive API enabled, internal OAuth consent screen, Desktop OAuth client ID (client credentials JSON provided to the app via config path, not committed).
- "CBM Documents" shared drive created with memberships granted.

## Working rules (DETAIL mode)

- One consequential thing at a time. Ask clarifying questions before writing code; wait for my approval before each next step. Low bar for what counts as consequential.
- Surface any conflict between the PRD and existing code structure before resolving it yourself.
- Minimal changes to existing files: surgical `str_replace` edits, never wholesale rewrites. Ask before removing any existing functionality.
- New dependencies (`google-auth`, `google-auth-oauthlib`, `google-api-python-client`, `keyring`) — confirm with me before adding them to project dependencies.
- Tests: pytest coverage for the metadata layer, folder-path construction, rollback logic, and OAuth token storage (mock the Drive API; no live calls in tests). Full suite must pass before commit.
- You commit; I push via GitKraken. Never `git push`, never `rm -rf` inside the repo after initial clone, never `git reset --hard`.

## Definition of done

- All Phase 1 items implemented, tests passing, ruff clean.
- A live smoke test against the real CBM shared drive: one upload, folder auto-creation verified, metadata row verified, rollback path exercised.
- Commit(s) staged with clear messages.
- You state the next required step and draft the Phase 2 kickoff prompt.
