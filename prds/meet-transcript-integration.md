# Meeting Transcript Integration — Google Meet (plan v0.1)

**Status: Phases 1+2 BUILT and DEPLOYED (v0.83.0, 2026-07-18, both envs) —
gated OFF by `MEET_TRANSCRIPTS`. Phase 0 progress (2026-07-18): licensing
CONFIRMED (CBM is on Business Standard — the blocking prerequisite below is
resolved); CRM fields built + probe-verified on crm-test, API-key CSession
READ verified; REMAINING: the three Google-side changes (Meet transcription
admin toggle, `meetings.space.created` on the DWD row, Meet API on in GCP),
then the flag + live verification.** App side: `core/gmeet.py`, the schedule-time auto-enable
in `sessions/gcal.py`, the worker retrieval job `sessions/transcripts.py`, and
the "Transcript document" facts-grid row. CRM handoff:
`csession-transcript-fields.md`. Originally drafted 2026-07-17 from Doug's
rulings (below) and verified API research. The app-side UI was already built
and feature-gated (v0.37.0): the session view's Transcript zone and the
editor's Transcript box activate automatically once
`CSession.sessionTranscription` exists in the CRM — this plan covers
everything between the meeting happening and that field being filled.

## Doug's rulings (2026-07-17)

1. **Auto-enable always** — every Meet the app schedules has transcription
   turned on programmatically; no per-session opt-in, no reliance on the host
   clicking "Start transcription". (Participants see Google's standard
   in-meeting transcription notice.)
2. **Meet now, Zoom later** — build the Google Meet path; structure retrieval
   per-provider so a Zoom source can slot in later. Hand-typed Zoom links get
   no automatic transcript in phase 1.
3. **Store both** — speaker-attributed transcript text into
   `CSession.sessionTranscription` (lights up the waiting UI) **plus** a link
   to the permanent Google Doc transcript.
4. **Licensing: to verify** — CBM's Workspace edition must be confirmed before
   activation (see the blocking prerequisite).

## Verified API facts the plan rests on (researched 2026-07-17)

- **Meet REST API v2** (GA): `conferenceRecords.transcripts` returns transcript
  metadata incl. `docsDestination` (the Google Doc + `exportUri`);
  `conferenceRecords.transcripts.entries` returns structured entries
  (participant, text, language, start/end times). **Entries are retained only
  30 days after the conference** — the Doc in the organizer's Drive is
  permanent ("Meet Recordings" folder; participants get no automatic access).
- **Auto-transcription is GA** (April 2025):
  `spaces.config.artifactConfig.transcriptionConfig.autoTranscriptionGeneration
  = "ON"` via `spaces.patch` — only the **meeting organizer** (space owner) can
  set it, which matches our model (the calendar hook acts as the organizing
  manager).
- **DWD works**: the Meet API explicitly supports service-account domain-wide
  delegation impersonating the organizer — same stack/key as Gmail/Calendar/
  Drive. Scope: `https://www.googleapis.com/auth/meetings.space.created`
  (sensitive, not restricted) covers config writes and transcript reads on
  spaces the impersonated user owns. Reading the Doc **link** needs no Drive
  scope (`docsDestination.exportUri` comes from the Meet API); we do not fetch
  the Doc's content.
- **Correlation**: `conferenceRecords.list` filters on `space.meeting_code`
  (the code in the stored `videoMeetingLink`) + a `start_time` window — no new
  identifier needs storing.
- **Push exists but isn't worth it**: Workspace Events API can push
  `transcript.v2.fileGenerated` to a Pub/Sub topic, but subscriptions expire
  and need renewal machinery. At CBM volume, worker polling (existing pattern)
  is simpler and sufficient.
- **Licensing gate**: Meet transcripts require **Business Standard or above**
  for the meeting organizer. The free Google Workspace for Nonprofits tier is
  Business-Starter-class and does NOT include them; nonprofit-discounted
  Business Standard is ~$3/user/month and only session-hosting users need it.
- **Zoom (deferred)**: paid plan per host + cloud recording + audio-transcript
  toggle + a Server-to-Server OAuth app; transcript is a post-hoc VTT
  (`recording.transcript_completed` webhook, lags the meeting substantially);
  local recordings are unreachable by any API.
- Gemini **smart notes** (AI summaries) are separately retrievable
  (`conferenceRecords.smartNotes`, GA April 2026) — out of scope here, noted
  as a possible later add.

## Blocking prerequisite — licensing check (Doug)

In the Google Admin console (admin.google.com → Billing → Subscriptions),
confirm which edition the `@cbmentors.org` users hold:

- **Business Standard / Plus / Enterprise** → no blocker, proceed.
- **Google Workspace for Nonprofits (free)** → transcripts are unavailable;
  upgrade the session-hosting users (mentors + partner/sponsor managers) to
  nonprofit Business Standard before activation.

Also confirm the Meet transcription feature is allowed for the org unit:
Admin console → Apps → Google Workspace → Google Meet → Meet video settings →
Transcription = ON.

## Architecture

Everything is gated by a new **`MEET_TRANSCRIPTS`** env flag (default false):
web needs it for the schedule-time enable, worker for retrieval. Best-effort
throughout (gcal-hook precedent): no Google failure ever breaks a session save
or a worker cycle.

### 1. CRM fields (build handoff — crm-test first, then prod)

- **`CSession.sessionTranscription`** — wysiwyg. Already feature-detected by
  `/fields` and `GET /sessions/{id}`; the UI needs no change.
- **`CSession.transcriptDocUrl`** — url. New; feature-detected the same way
  (calendar-field precedent). Session view shows it as a "Transcript document"
  copy-link row in the facts grid (small frontend addition).
- **Grant**: the API user's role (`CustomAppAPIRole`) needs **CSession
  read + edit** — the retrieval job runs under the API key (comms-sync
  precedent), and today the intake key has no CSession grant at all.

A field-spec handoff doc (`csession-transcript-fields.md`,
csession-calendar-field.md style) will be authored at build kickoff.

### 2. Google side (one-time, admin)

- Add `meetings.space.created` to the SA's existing DWD row in Google Admin.
  **Gotcha (documented previously): the scope field REPLACES — edit the
  existing line keeping all current scopes** (gmail.readonly, gmail.send,
  calendar.events, drive, admin.directory scopes as applicable).
- Enable the Meet API on GCP project `espcrm-498315`.
- The transcription admin toggle + licensing per the blocking prerequisite.

### 3. Schedule-time: auto-enable transcription (`sessions/gcal.py` + new `core/gmeet.py`)

After the calendar hook creates an event with a generated Meet conference:

1. Extract the meeting code from the Meet link.
2. As the organizer (same impersonated mailbox the event was created with),
   `spaces.get` by meeting code, then `spaces.patch` setting
   `artifactConfig.transcriptionConfig.autoTranscriptionGeneration = "ON"`.
3. Result rides the existing `calendar:{...}` save-response notice
   (best-effort; a failure means the meeting simply isn't auto-transcribed —
   the retrieval job still picks up manually-started transcripts).

Hand-typed links (Zoom or otherwise) are untouched, matching the hook's
existing rule. Edits that move a session's time don't need re-enabling (the
setting lives on the space, not the event); a regenerated Meet link gets the
same treatment as create.

### 4. Retrieval: worker periodic job (new `sessions/transcripts.py`)

New worker timer (`MEET_TRANSCRIPTS_POLL_SECONDS`, default ~1800, monitoring-
check pattern), running under the API-key client:

1. **Candidate query**: CSessions whose `dateStart` is past (window: last
   `TRANSCRIPT_GIVE_UP_DAYS`, default 14 — comfortably inside Google's 30-day
   entries retention), `sessionTranscription` empty, and `videoMeetingLink`
   contains `meet.google.com`. Status is deliberately NOT required to be
   Completed — mentors don't reliably flip it.
2. **Organizer resolution**: the session's `assignedUser` → their
   `CMentorProfile.cbmEmail` (the same resolution the hook used to create the
   event), falling back to the parent record's manager profile. No resolvable
   mailbox ⇒ skip with a log line.
3. **Provider seam**: a small `TranscriptSource` interface — given (session,
   organizer mailbox) return `ready(html, doc_url)` / `not_ready` /
   `permanent_skip`. Phase 1 ships only `MeetTranscriptSource`; a Zoom source
   slots in later keyed off the link's host.
4. **Meet source**: impersonate the organizer; `conferenceRecords.list`
   filtered by `space.meeting_code` + a start-time window around the session's
   `dateStart` (handles reused/recurring codes); pick the transcript whose
   state is ended; page through `transcripts.entries`; resolve participant
   display names via `conferenceRecords.participants`; format
   speaker-attributed, timestamped HTML (sanitized, matching what the
   transcript UI expects); take `docsDestination.exportUri` for the Doc link.
5. **Write-back**: one CSession update — `sessionTranscription` +
   `transcriptDocUrl`. The session's existing `assignedUsers` stamps keep it
   visible to the mentor team; the write is attributed to the API user.
6. **No conference record / no transcript yet** ⇒ not_ready, retried next
   cycle until the give-up window passes (meeting never happened, or
   transcription was off). Oversized transcripts are clamped with a truncation
   note appended (wysiwyg columns are finite).

### 5. Out of scope (deliberately)

- **Zoom** — later phase behind the provider seam (paid-plan + cloud-recording
  prerequisites are CBM-side decisions first).
- **Gemini smart notes** — possible later add (`conferenceRecords.smartNotes`).
- **Real-time transcription** — Meet Media API is Developer Preview only; not
  production-usable.
- **Retroactive transcripts** — meetings held before activation (or with
  transcription off) cannot be transcribed after the fact.

## Phasing

- **Phase 0 (no code)**: licensing check + admin transcription toggle; Meet API
  on in GCP; DWD scope added; CRM fields built on crm-test
  (`sessionTranscription` wysiwyg + `transcriptDocUrl` url) + CSession
  read/edit on CustomAppAPIRole.
- **Phase 1**: `core/gmeet.py` (MeetClient: spaces get/patch, conference
  records, transcripts, participants) + schedule-time auto-enable in the gcal
  hook. Harness + unit tests.
- **Phase 2**: worker retrieval job + write-back + the "Transcript document"
  facts-grid row. Live verification on crm-test: schedule a real session →
  hold a short real Meet → transcript appears in the tab within a poll cycle;
  verify the Doc link, the give-up path (a meeting never held), and a
  non-admin mentor's visibility.
- **Phase 3 (unscheduled)**: Zoom source; smart-notes summaries if wanted.

## Consent / privacy notes

- Google shows every participant its standard transcription notice in-meeting;
  the organizer can still turn transcription off for a given meeting from
  inside Meet (the retrieval job then simply finds nothing and gives up).
- Consider one sentence in the calendar-event description ("This session is
  transcribed for CBM's records.") — cheap transparency for clients; decide at
  build time.
- Transcript text lands in the CRM under CSession's existing ACL (mentor team
  visibility) — same audience as session notes today.
