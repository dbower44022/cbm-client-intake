# docs/ — Google Drive documents

Last Updated: 10-30-26 01:09 · Revision 1.0

Detail for the Google Drive documents feature: the folder scheme, the access model, grants and reconciliation, rollback and archive.

Claude Code loads this file only when a session reads or edits files in this
folder. The rules other packages depend on stay in the root `CLAUDE.md`, which
also points here. Moved word for word from the root file on 10-30-26, when
it passed its 80,000-character limit; edit it here from now on.

## Documents — Google Drive

`docs/` package, gated by `GDRIVE_DOCS`. Setup runbook: `GDRIVE-DOCS-SETUP.md`;
PRD in `prompts/Google Drive Documents/`.

- Folder scheme under the shared drive: `{Entity Label}/{Record Name} (id)/`,
  with engagement folders **nested under their client**. Labels are configurable
  (`GDRIVE_ENTITY_LABELS`: Contact=Mentors, CEngagement=Clients, …).
- **Access model (Doug's ruling, PRD v1.5)**: no person is a member of the
  shared drive except the two designated system administrators; the **service
  account is the operational member** and all Drive ops run as it
  (`GDRIVE_IDENTITY=service`). Drive-side access is per-person folder-level
  **Commenter** grants mirroring CRM entitlements, revoked by the same app
  actions that end the entitlement, plus a **nightly reconciliation** that
  re-derives grants from the CRM. `Mentors/` personnel folders get **no**
  grants. Commenter means uploads can never bypass the app's index.
- **A grant needs a real Google account.** The person's address is their
  `CMentorProfile.cbmEmail`, and mentor provisioning back-fills that
  (`firstname.lastname@` the `MENTOR_EMAIL_DOMAIN` setting, default
  `cbmentors.org`) **without creating a Workspace mailbox**
  — so the address often doesn't exist, which is the norm on crm-test. Drive
  400s a silent share to an unknown address, so `create_permission` raises
  `DriveNoAccountError` and the reconciliation counts it as `unfulfillable`,
  **not** an error: logged and counted, never alerted, retried every pass so it
  self-heals the day the mailbox appears. In-app document access is unaffected
  either way (the app reads Drive as the service account); only opening the
  folder directly in Drive needs the grant.
- **A drive member needs no grant.** The two designated administrators ARE
  shared-drive members, so Drive reports their access on every folder as
  *inherited* (`permissionDetails[].inherited`, `permissionType: member`) and
  merges any file-level grant into that one permission. The engine treats
  at-least-Commenter inherited access as satisfying the entitlement —
  `driveMembers` in the result, never a create and never a delete. Before
  v0.201.2 it skipped inherited permissions outright, so it re-created the same
  grant every night forever without converging.
- **Rollback rule**: a row-write failure deletes the Drive file; a Drive failure
  never writes a row. Uploads pre-assign ids via `files.generateIds` so a retry
  can't duplicate.
- **Archive** moves the file to `_Archived` **first**, then flips metadata, with
  a move-back rollback on a mid-failure.
- Viewing streams through an ACL-gated proxy; **the browser is the cache**
  (immutable responses on modifiedTime-versioned URLs). Office formats
  convert-on-view; `?original=true` streams exact bytes for download.
- `documentsFolderUrl` write-back is feature-detected and inert until the CRM
  field exists.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-30-26 01:09 | Claude (Claude Code) | Created from the root `CLAUDE.md` section, word for word (Doug's approval 10-30-26). |
