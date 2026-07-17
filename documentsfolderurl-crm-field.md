# `documentsFolderUrl` on `CEngagement` + `Contact` — CRM build specification

**Status: NOT BUILT — required for the Documents CRM link write-back
(DOC-MGMT Phase 3, PRD v1.3 DOC-08 / D-05 / §3.5).** The app side shipped
with Phase 3 and **feature-detects the field via metadata**, staying
completely inert until it exists — this build can land before or after the
app deploy in any order. Build on **crm-test first**; prod follows after live
verification. This is the CRM-team handoff, in the style of
`csession-calendar-field.md`. Track as a crmbuilder program in
`ClevelandBusinessMentors/programs/` per that repo's requirement-first
process.

## What this is

Every CRM record that owns managed documents has exactly one Google Drive
folder (`Clients/{Client} ({id})/{Engagement} ({id})/` for client work,
`Mentors/{Name} ({id})/` for mentor documents). This field holds that
folder's permanent Drive link (`webViewLink`) — **one stable link per
record**, never per file (decision D-05), so it never goes stale as files
come and go. A user clicking it from the CRM lands directly in that record's
documents; whether Drive lets them in is decided by the folder's own access
grants (PRD §3.4 — engagement folders are shared with the assigned mentor +
co-mentors; mentor personnel folders with no one).

The app writes the field on the record's **first document upload** (and
self-heals it on later uploads + a nightly re-check). The app is the only
writer; staff never edit it.

## The build (one field, two entities)

Standing in **Entity Manager → CEngagement → Fields → Add Field**, then the
same again for **Contact**:

| Setting | Value |
|---|---|
| Type | **Url** |
| Name | `documentsFolderUrl` |
| Label | Documents Folder |
| Max Length | 512 |
| Required | No |
| Default | (none) |
| Audited | No |

Notes:
- **Read-only in layouts** (NFR-03): if the field is placed on the detail
  layout (useful — it's the CRM-side entry point to the record's documents),
  set it **Read-only** so staff can't hand-edit it; a corrupted link would
  point users at the wrong folder until the next upload heals it.
- Only these two entities participate initially (PRD §3.5): `CEngagement`
  (client-work documents — the volume case, D-07) and `Contact` (mentor
  documents). CPartnerProfile/CSponsorProfile can be added later the same
  way; the app's write-back covers new entities by configuration change only.
- No new relationships. **Grant note:** the writer is the app's API user
  (role `CustomAppAPIRole`), which already has read+edit on both entities —
  no role change needed unless field-level ACL is in use (it is not, on
  either CRM).

## Verification (after the field exists on crm-test)

1. Upload a document to an engagement that has none — in `/mentorsessions`,
   open the engagement → Documents → Upload. The engagement record's
   `documentsFolderUrl` should now hold a `drive.google.com` folder link;
   opening it (as someone the folder is shared with, e.g. the assigned
   mentor) lands in that engagement's Drive folder.
2. Upload a second document — the field value must not change (idempotent:
   the app writes only when the stored value differs).
3. Upload a document for a mentor in `/mentoradmin` → the mentor's
   **Contact** record gains the link the same way.

## Related

- App side: `docs/service.py` (`write_back_folder_link` — feature-detection,
  idempotent write, self-healing best-effort per Doug's ruling 2026-07-17;
  no retry queue) and `docs/reconcile.py` (the nightly re-check).
- PRD: `prompts/Google Drive Documents/CBM-DocMgmt-Implementation-PRD.docx`
  v1.3 — DOC-08, D-05, D-07, §3.5.
