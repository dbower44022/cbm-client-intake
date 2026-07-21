# `CSession.sessionAiSummary` — CRM build specification

**Status: BUILT (2026-07-21, per Doug) — probe-verified on crm-test the same
day (`sessionAiSummary` present, type wysiwyg, alongside both transcript
fields); prod build reported by Doug, unverifiable from the app side (the
prod overlay's API key is EV-encrypted).** Required for Phase 2 of the Fathom
note-taker integration (app side shipped in v0.124.0, gated off by
`FATHOM_TRANSCRIPTS`; plan: `prds/fathom-transcript-integration.md`). This is
the CRM-team handoff, in the style of `csession-transcript-fields.md` /
`csession-calendar-field.md`. Build on **crm-test first**; prod follows after
live verification. Track as a crmbuilder program in
`ClevelandBusinessMentors/programs/` per that repo's requirement-first process.

## What this is

When a mentor's Fathom note taker records a session's meeting, a background
job stores — alongside the transcript that goes into the existing
`sessionTranscription` field — Fathom's **AI-generated meeting summary** on
the session record. The session view renders it as a read-only "AI Summary"
zone above the Transcript zone.

The field also carries the **action-items overflow**: Fathom's task list is
written into the existing `nextSteps` field ("Action items / next steps")
when that field is empty, but if the mentor already wrote next steps, the
list is appended here under an "Action items" heading instead — human
content is never overwritten (Doug's ruling 2026-07-21).

The app **feature-detects the field via metadata** and stays completely
inert until it exists, so this build can land before or after the app deploy
in any order. Until it exists: the transcript + `nextSteps` routing still
work; only the summary (and the overflow case) are skipped with a log line.

## The build (one field)

Standing in **Entity Manager → CSession → Fields → Add Field**:

### `sessionAiSummary`

| Setting | Value |
|---|---|
| Type | **Wysiwyg** |
| Name | `sessionAiSummary` |
| Label | AI Summary |
| Required | No |
| Audited | No |
| (everything else) | defaults |

Notes:

- **App-managed**: written only by the worker retrieval job (as the API
  user); it is NOT in the session editor's field set and never rides a user
  save. Do not add it to any CRM edit layout mentors use — a detail-layout
  read-only placement in the CRM UI is fine if staff want to see it there.
- **Grants**: none new — `CustomAppAPIRole` already carries CSession
  read + edit from the Meet transcript build, and mentor visibility rides
  the session's existing `assignedUsers` ACL (same audience as session
  notes).

## Verification (after build)

1. Metadata probe: `GET Metadata?key=entityDefs.CSession.fields` shows
   `sessionAiSummary` (type wysiwyg).
2. With `FATHOM_TRANSCRIPTS=true` + `FATHOM_API_KEY` on the worker, a
   Fathom-recorded session's next poll cycle stores transcript + summary;
   the session view shows the AI SUMMARY zone.
3. The routing rule: a session whose `nextSteps` was empty gets the task
   list there; one with mentor-written next steps gets it appended to this
   field under "Action items".
