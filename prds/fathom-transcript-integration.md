# Meeting Transcript Integration — Fathom note taker (plan v0.1)

**Status: Phases 1+2 BUILT (v0.124.0, 2026-07-21, 944 tests green) — gated
OFF by `FATHOM_TRANSCRIPTS`. Remaining: Phase 0 (Doug — Fathom tier/key/
team-sharing + the listing probe), the `sessionAiSummary` CRM field build
(`csession-ai-summary-field.md`), then Phase 3 live verification.** App
side: `core/fathom.py`, the multi-source seam + `FathomTranscriptSource` in
`sessions/transcripts.py`, the AI Summary view zone. One build note: when
the CRM lacks `sessionAiSummary`, the action-items → empty-`nextSteps` path
STILL works (that field exists today); only the summary and the
items-overflow case are skipped. Originally drafted 2026-07-20 from Doug's
rulings (below) and verified API research. This plan extends the shipped
Google Meet transcript integration (`prds/meet-transcript-integration.md`,
v0.83.0 — Phases 1+2 built, gated by `MEET_TRANSCRIPTS`) so the retrieval
pipeline supports **either note taker**: Fathom (fathom.video) or Google
Meet's native transcription. The `TranscriptSource` provider seam in
`sessions/transcripts.py` was built for exactly this — Fathom becomes the
second source behind it.

## Doug's rulings (2026-07-20)

1. **One team API key** — the app authenticates to Fathom with a single
   `FATHOM_API_KEY` (from a CBM admin/service Fathom account), the app's
   standard single-service-credential pattern. This requires mentors'
   Fathom recordings to be **shared to the CBM team** (Fathom keys are
   user-level and read only "meetings recorded by you or shared to your
   Team" — see the API facts). Per-mentor keys are the documented fallback
   if team sharing turns out not to cover it.
2. **Fathom first, Meet-native fallback** — for a session whose meeting
   could have both (mentor runs Fathom inside a Meet call), the Fathom
   source is tried first; the Meet source fills in when Fathom has nothing.
   Fathom also covers hand-typed **Zoom/Teams links**, which the Meet
   source never could — this widens transcript coverage beyond generated
   Meet links for the first time.
3. **Store everything Fathom offers** — the speaker-attributed transcript
   (existing `sessionTranscription` + the Fathom share link into
   `transcriptDocUrl`), **plus** Fathom's AI summary (new feature-detected
   CRM field — see §CRM) **and** action items. **Action-items placement
   (amended 2026-07-21):** Fathom's task list goes into the EXISTING
   `CSession.nextSteps` field ("Action items / next steps" in the editor)
   **when that field is empty** at write-back time; if the mentor already
   wrote anything there, the list is appended to `sessionAiSummary` as an
   "Action items" section instead — existing human content is never
   touched. The summary itself always goes to `sessionAiSummary`, never
   to `sessionNotes`.
4. **Poll, don't webhook** — reuse the existing worker retrieval timer.
   Fathom webhooks exist but need a public authenticated endpoint;
   polling matches the shipped pattern and the 60 req/min rate limit is
   a non-issue at CBM volume. Webhooks are a possible later latency
   upgrade, noted out of scope.

## Verified API facts the plan rests on (researched 2026-07-20)

- **Base URL**: `https://api.fathom.ai/external/v1`. Auth: `X-Api-Key`
  header (Bearer also accepted). Rate limit: **60 calls/minute** across all
  of an account's keys. Official docs: https://developers.fathom.ai
- **API keys are user-level**: a key reads meetings **recorded by that
  user or shared to their Team**; an admin key does NOT see other users'
  unshared meetings. ⇒ the one-key model stands or falls on CBM's Fathom
  team-sharing configuration (Phase 0 verification).
- **`GET /meetings`** — filters: `created_after`/`created_before`,
  `recorded_by[]` (emails), `teams[]`, `meeting_type`,
  `calendar_invitees_domains[]`; content flags `include_transcript`,
  `include_summary`, `include_action_items`, `include_crm_matches`;
  cursor pagination (`next_cursor`). Each meeting carries:
  - **`meeting_url`** — the underlying platform join link (Meet/Zoom/
    Teams). **This is the correlation key to our stored
    `CSession.videoMeetingLink`** — no new identifier needs storing
    (same property the Meet plan had via the meeting code).
  - `recording_id`, `url` / **`share_url`** (permanent Fathom links),
    `title`, `scheduled_start_time`/`end_time`,
    `recording_start_time`/`end_time`, `calendar_invitees` (name/email),
    `recorded_by` (user), `shared_with` scope.
  - Summary as **markdown** + template name; action items.
- **`GET /recordings/{recording_id}/transcript`** — returns
  `transcript[]` of `{speaker: {display_name,
  matched_calendar_invitee_email}, text, timestamp: "HH:MM:SS"}` —
  directly mappable to the existing speaker-attributed HTML format
  (`core/gmeet.format_transcript_html` shape: merged consecutive
  same-speaker entries, elapsed [MM:SS] stamps).
- **Sync or async**: both summary/transcript endpoints return data
  directly when `destination_url` is omitted — we always omit it.
- **Webhooks** exist (fire when meeting content is ready; can carry
  transcript/summary/action items) — deliberately unused (ruling 4).
- **No schedule-time hook is possible or needed**: Fathom auto-joins from
  the *mentor's* calendar per their own Fathom settings. Our calendar
  hook already creates the event on the organizing manager's calendar, so
  a mentor with Fathom auto-record ON gets recorded with zero app work.
  (The Meet auto-transcription enable stays as-is — it powers the
  fallback source.)

## Blocking prerequisites — Fathom side (Doug, Phase 0)

1. **Plan tier**: confirm CBM's Fathom edition includes API access
   (check Settings → API / developers.fathom.ai key creation on the CBM
   account; free-tier API availability is unverified).
2. **Service identity**: pick/create the CBM Fathom account that owns the
   API key (an admin on the CBM Fathom team). Generate the key.
3. **Team sharing**: confirm mentors' recordings are (or can default to)
   **shared to the CBM team** — the one-key model reads nothing else.
   Fathom team settings should allow a default share-with-team policy;
   verify, and verify externally-recorded meetings follow it.
4. **Mentor onboarding**: which mentors use Fathom, auto-record settings
   ON for calendar meetings. (Mentors without Fathom silently keep the
   Meet-native path — no configuration needed per mentor in the app.)
5. **Probe**: one read-only `GET /meetings?created_after=…` with the key
   proves tier + sharing before any code ships (same spirit as the CRM
   grant probes).

## Architecture

Gated by a new **`FATHOM_TRANSCRIPTS`** env flag (default false) +
`FATHOM_API_KEY` (SECRET, **worker** component only — no web involvement;
there is no schedule-time Fathom hook). Best-effort throughout, identical
to the Meet contract: no Fathom/CRM failure ever crashes a worker cycle;
a per-session failure never blocks the batch; no retry state — a session
stays a candidate until it resolves or ages out of
`TRANSCRIPT_GIVE_UP_DAYS`.

### 1. Seam refactor (`sessions/transcripts.py`) — from one source to an ordered list

- `run_transcript_cycle` builds an **ordered source list** instead of a
  single source: `[FathomTranscriptSource (if flag+key),
  MeetTranscriptSource (if MEET_TRANSCRIPTS + SA)]` — order IS the
  precedence ruling. The existing `source=` test-injection param becomes
  `sources=`.
- Per session: walk the list; skip sources whose `matches(link)` is
  false; on `ready` → write back and stop; on `not_ready`/`skip` → try
  the next source. All sources `not_ready` ⇒ retry next cycle (unchanged
  give-up semantics).
- **Candidate query widening**: the current where-clause hard-codes
  `videoMeetingLink contains meet.google.com`. With Fathom on, the
  contains-filter relaxes to "videoMeetingLink is not empty" (Fathom
  covers Zoom/Teams/Meet); per-link routing stays in Python via
  `matches()`. With Fathom off, the query keeps today's narrow filter —
  zero behavior change for existing deploys.
- The worker timer gate becomes `meet_transcripts OR fathom_transcripts`;
  the existing `MEET_TRANSCRIPTS_POLL_SECONDS` name is **kept** as the
  shared cadence (overlay stability; renaming buys nothing).
- `SourceResult` gains optional `summary_html` and `action_items_html`;
  `_write_back` writes the summary to the new CRM field when it exists
  (feature-detected, same as `transcriptDocUrl` today) and routes the
  action items per the amended ruling: the candidate query re-reads
  `nextSteps` (added to the select), and the list lands in `nextSteps`
  only when it is empty — where "empty" includes blank wysiwyg markup
  (`<p><br></p>` etc., the established empty-richtext test the Overview
  notes placeholder uses), not just null — otherwise it is appended to
  `sessionAiSummary` under an "Action items" heading. Both writes ride
  the same single CSession update as the transcript.
- The organizer-mailbox resolution stays (the Meet source needs it for
  DWD); the Fathom source ignores the mailbox for auth but uses the
  organizer email as a **soft disambiguation check** (log-only) against
  `recorded_by`/invitees.

### 2. New `core/fathom.py` — `FathomClient` + pure helpers (gmeet pattern)

- `FathomClient(api_key, timeout)`: httpx, `X-Api-Key`, cursor
  pagination, 429/5xx backoff honoring Retry-After (GmailClient
  precedent). Surface: `list_meetings(created_after, created_before,
  include_summary, include_action_items)` (paged) and
  `get_transcript(recording_id)`.
- Pure helpers, unit-testable without network:
  - `normalize_meeting_url(link)` → a canonical key per platform: Meet
    meeting code (reuse `core/gmeet.meeting_code`), Zoom meeting id from
    `zoom.us/j/{id}` (ignoring `?pwd=`), Teams meeting id; `None` for
    unrecognizable links.
  - `format_transcript_html(entries)` → the same sanitized,
    speaker-attributed HTML shape the Meet formatter emits (consecutive
    same-speaker merge, [H:MM:SS] stamps from the `timestamp` field) so
    the existing Transcript UI zone renders both providers identically.
  - `summary_html(markdown_text)` + `action_items_html(items)` →
    sanitized HTML (small local markdown-subset renderer or plain
    paragraph/list mapping — no new dependency unless one already
    ships).

### 3. `FathomTranscriptSource` — matching and fetching

- `matches(link)` = `normalize_meeting_url(link) is not None` (any
  platform Fathom records).
- **One listing sweep per cycle, not per session**: the source lazily
  fetches `GET /meetings?created_after={give-up cutoff}` once per cycle
  (summary + action items inlined; transcript NOT inlined — payload
  size), and indexes meetings by `normalize_meeting_url(meeting_url)`.
  All candidate sessions resolve against this in-memory index; only a
  matched session costs a per-recording transcript call. Worst case at
  CBM volume: a handful of calls per cycle against the 60/min limit.
- **Match rule** (mirrors the Meet source's reused-code handling):
  normalized URL equal AND the meeting's start
  (`recording_start_time`, falling back to `scheduled_start_time`)
  within the existing ±36h `_MATCH_WINDOW` of the session's `dateStart`;
  multiple matches ⇒ closest start wins.
- `ready` ⇒ `SourceResult(html=transcript_html,
  doc_url=share_url, summary_html=…, action_items_html=…)`. A matched
  meeting whose transcript array is empty ⇒ `not_ready` (Fathom may
  still be processing — a meeting that ended minutes ago often has no
  transcript yet); no match ⇒ `not_ready` ("no Fathom recording yet"),
  letting the Meet source try and the cycle retry.

### 4. CRM fields (build handoff — crm-test first, then prod)

- Existing, unchanged: `CSession.sessionTranscription` (wysiwyg),
  `CSession.transcriptDocUrl` (url — now carries EITHER the Google Doc
  export link or the Fathom `share_url`; the session-view row label
  generalizes from "Transcript document" to "Transcript / recording
  link").
- **New: `CSession.sessionAiSummary`** (wysiwyg) — Fathom's AI summary.
  Feature-detected like the transcript fields: the write and the UI zone
  are inert until it exists. Action items are NOT part of this field by
  default — they go to the existing `nextSteps` when it's empty (the
  amended ruling); this field only carries them (as an appended "Action
  items" section) when the mentor had already written next steps.
- **Existing: `CSession.nextSteps`** ("Action items / next steps") — the
  preferred destination for Fathom's task list. Written ONLY when empty
  (null or blank wysiwyg markup) at write-back time; since the transcript
  write happens once per session (the null-transcript candidate filter),
  the app can never later overwrite next steps a mentor adds afterward.
  No CRM build needed — the field exists on both CRMs.
- Grants: none new — `CustomAppAPIRole` already has CSession read+edit
  from the Meet build.
- Field-spec handoff doc at build kickoff:
  `csession-ai-summary-field.md` (csession-transcript-fields.md style).

### 5. UI (small, feature-detected)

- Session view gains an **"AI Summary"** zone above the Transcript zone,
  rendered only when `sessionAiSummary` exists in metadata and is
  non-empty (exact `sessionTranscription` precedent — `/fields` +
  `GET /sessions/{id}` already carry the detection pattern).
- The facts-grid link row label generalizes (§4).
- No editor box for the summary in v1 (read-only AI output; the
  transcript editor box precedent doesn't apply — staff corrections to
  an AI summary weren't asked for).

### 6. Settings

```
FATHOM_TRANSCRIPTS=false        # gate (worker)
FATHOM_API_KEY=                 # SECRET (worker)
FATHOM_BASE_URL=https://api.fathom.ai/external/v1   # override for tests
# shared with the Meet path, unchanged:
MEET_TRANSCRIPTS_POLL_SECONDS=1800
TRANSCRIPT_GIVE_UP_DAYS=14
```

`MEET_TRANSCRIPTS` keeps gating only the Meet source + the schedule-time
auto-enable. Either flag alone runs the cycle; both together = the
Fathom-first/Meet-fallback ruling.

## Out of scope (deliberately)

- **Webhooks** (ruling 4) — later latency upgrade if polling ever feels
  slow.
- **Sessions with no `videoMeetingLink`** — Fathom may have recorded an
  ad-hoc meeting, but there is nothing to correlate on; not attempted.
- **Fathom CRM-match ingestion** (`include_crm_matches`) — Fathom's own
  CRM linking is irrelevant; EspoCRM correlation is ours.
- **Per-mentor API keys** — fallback only if team sharing fails Phase 0.
- **Zoom's native transcript API** — superseded: Fathom covers Zoom
  meetings without the Server-to-Server OAuth app the Meet plan deferred.

## Phasing

- **Phase 0 (no code, Doug)**: the Fathom-side prerequisites above —
  tier check, service account + key, team-share verification, mentor
  onboarding, the read-only listing probe.
- **Phase 1 (code)**: `core/fathom.py` + the seam refactor + the Fathom
  source + settings; transcript + share-link write-back only. Unit tests
  (client paging/backoff, URL normalization incl. Meet/Zoom/Teams +
  pwd-param cases, formatter, match-window/closest-start, source
  ordering incl. Fathom-not_ready→Meet-fallback, candidate-query
  widening on/off) + stub-harness sanity.
- **Phase 2 (code)**: `sessionAiSummary` CRM field (crm-test) + summary/
  action-items write-back + the AI Summary view zone + label
  generalization. Tests: action items → empty `nextSteps`; blank wysiwyg
  markup counts as empty; pre-existing next steps → items appended to
  `sessionAiSummary` with the human field untouched; summary always →
  `sessionAiSummary`; missing `sessionAiSummary` field ⇒ summary/items
  writes skipped, transcript still stored.
- **Phase 3 (live verification, crm-test)**: a real mentor with Fathom
  holds a short Meet AND a short Zoom meeting against scheduled
  sessions → both transcripts + summaries appear within a poll cycle;
  Fathom-first precedence observed on the Meet one (doc_url = Fathom
  share link, not the Google Doc); action items land in the empty
  `nextSteps` on one session and append to the AI summary on a session
  where the mentor pre-filled next steps; a session whose mentor has no
  Fathom still fills via Meet-native; the give-up path; a non-admin
  mentor sees the new zone. Then prod (field build + flag on the prod
  overlay).

## Open questions / risks

1. **Team-share coverage** (the load-bearing unknown): if CBM's Fathom
   plan can't default-share mentors' recordings to the team, the one-key
   model reads nothing and the per-mentor-key fallback (Email-Setup-style
   encrypted storage) becomes a real build. Settle in Phase 0 before any
   code.
2. **`meeting_url` fidelity**: assumed to carry the same join URL the
   session stores; verify against a real recording in the Phase 0 probe
   (especially Zoom links with/without `?pwd=`).
3. **Summary quality/PII**: Fathom's AI summary lands in the CRM under
   CSession's existing ACL (mentor-team visibility — same audience as
   session notes). Same consent posture as the Meet plan; Fathom shows
   its own in-meeting recording notice.
4. **Rate limit**: 60/min is ample; the one-sweep-per-cycle design keeps
   usage to (pages + matched transcripts) per 30 minutes.
