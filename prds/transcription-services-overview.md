# Meeting Transcription & AI Note-Taking — Options for CBM

**Version 1.0 — 2026-07-24. Audience: CBM leadership.** A plain-language
overview of the meeting note-taking landscape and what it would take for our
mentoring platform to support each option, written to support a discussion of
which services CBM should endorse. Companion technical references:
`prds/meet-transcript-integration.md` (Google Meet, built),
`prds/fathom-transcript-integration.md` (Fathom, built).

---

## 1. Why this matters

Every mentoring session recorded in our Client Management tool has a notes
area, an AI-summary area, and a transcript area. When a note-taking service
covers a meeting, the platform can **automatically** attach the transcript,
the AI summary, and the action items to the right session record — no
copy-paste, no lost notes, and the whole mentor team (co-mentors, staff) sees
them. The question is *which services we support*, because mentors already use
different tools, and CBM's philosophy (per Doug's 2026-07-24 ruling on Zoom)
is **"let the mentor use the tool they already have"** rather than forcing one
tool on everyone.

## 2. What CBM already has (built and working)

| Capability | Status |
|---|---|
| **Google Meet native transcription** | Built. Sessions scheduled through the app with a generated Meet link get transcription auto-enabled; the worker retrieves the transcript and files it on the session. Included in CBM's Google Workspace Business Standard licenses — no extra cost. |
| **Fathom** | Built and verified live. Fathom auto-joins from the mentor's calendar (Meet, Zoom, or Teams); the platform matches each recording to its session by meeting link, time, and attendee overlap, then files the transcript, AI summary, and action items (action items land in the session's Next Steps when empty). |
| **The matching engine** | The hard part — correlating a vendor's recording to the right session — is vendor-independent and already built. Adding a vendor is a bounded, incremental job, not a rebuild. |

Two Fathom decisions are still open: whether CBM uses one team API key (needs
Fathom team-sharing to cover mentors' recordings) or per-mentor keys, and
turning the feature flag on in production.

## 3. How a note-taker can connect — three integration models

Understanding these three models is most of the decision, because each vendor
only supports some of them.

**A. API pull (what Fathom uses).** The platform periodically asks the
vendor's API "any new recordings?" and matches them to sessions. Requires an
API key. Reliable and invisible to the mentor once set up.

**B. Webhook push.** The vendor calls our platform the moment a meeting's
notes are ready. No polling, but the *mentor* must paste our webhook address
into their vendor settings — a one-time setup step per mentor, and a support
burden if they get it wrong.

**C. Email ingestion (a universal fallback we could build).** Nearly every
note-taking product emails the host a summary after each meeting. The platform
already syncs every mentor's `@cbmentors.org` mailbox and has an
email-cleaning pipeline. A source that recognizes note-taker summary emails
and files them on the matching session would work for **any vendor — even the
ones with no usable API** — with one build instead of one per vendor. The
trade-off: the email usually contains the summary and a link to the recording,
not the full verbatim transcript.

## 4. The vendor landscape

Assessment against CBM's constraint: the mentor brings their own account,
usually a free or personal-tier one.

| Vendor | Platforms covered | How we'd connect | Verdict for CBM |
|---|---|---|---|
| **Google Meet native** (built) | Meet only | Google API under our own Workspace | Keep — zero cost, zero mentor setup, but Meet-only |
| **Fathom** (built) | Meet, Zoom, Teams | API pull; user-level key sees own + team-shared recordings | Keep — already proven end-to-end |
| **Fireflies.ai** | Meet, Zoom, Teams + more | API pull (per-user key, **available on the free plan**) and webhooks | **Best candidate to add** — the only major vendor whose free tier includes API access |
| **Read.ai** | Meet, Zoom, Teams, Webex | REST API (open beta) + webhooks (paid plans) | Possible, less mature API; paid plan needed for webhooks |
| **tl;dv** | Meet, Zoom, Teams | API + webhooks (paid plans; webhooks arranged through their team) | Possible, but setup friction and paid-tier requirement |
| **Otter.ai** | Meet, Zoom, Teams | Public API exists but is **Enterprise-workspace only** — a mentor's personal Otter account has **no API at all** | **Not integrable directly.** Otter users are only reachable via email ingestion (or manual paste) |
| **Zoom AI Companion** | Zoom only | API requires **Zoom account-admin** credentials; there is no way for a user to grant access to just their own summaries | **Not integrable** under mentor-supplied Zoom. Same fallback: email ingestion |
| **Recall.ai** (aggregator) | All platforms via a bot that joins the meeting | One paid API, our credentials, per-meeting pricing | A different philosophy — CBM would be *supplying* the note taker, not supporting the mentor's own. Only relevant if the goal becomes "guarantee every session has notes" |

Sources: Fireflies API docs (free-tier per-user keys, GraphQL + webhooks);
Otter.ai help center (Public API "available for all Enterprise workspaces");
Read.ai help center (REST API open beta, webhooks); tl;dv help center; Zoom
developer forum threads confirming AI Companion summaries are admin-scope
only; Recall.ai product docs. Gathered 2026-07-24 — this market moves fast,
so re-verify tiers/pricing before committing.

## 5. What each choice would cost

**App engineering** (rough, based on the Fathom build):

| Option | Build size | Ongoing burden |
|---|---|---|
| Fireflies as a third API source | Small-to-medium (a source class + credential storage; the matcher is shared) | Low |
| Per-mentor "connect your note taker" self-service (paste your own API key in My Mentor Profile) | Medium (encrypted per-user key storage + UI; we have the encryption machinery) | Low — mentors self-serve |
| Generic webhook receiver (Fireflies/Read/tl;dv push) | Medium (endpoint + per-vendor payload normalizers) | Mentor-setup support calls |
| **Email ingestion fallback** | Medium (one recognizer + the existing mail sync and matcher) | Low — covers *all* vendors incl. Otter and Zoom AI Companion |
| Recall.ai | Medium | **Per-meeting fees**, ongoing |

**CBM cost:** every option above except Recall.ai costs CBM no vendor fees —
the mentor's own account (free or paid) does the recording. **Mentor cost:**
free tiers typically cap monthly recordings or transcript history; that's the
mentor's relationship with their vendor, consistent with the
bring-your-own-tool philosophy.

## 6. What "support" should mean (proposed policy)

A tiered statement CBM could adopt:

- **Tier 1 — Recommended, fully automatic:** Google Meet native + Fathom.
  CBM documents them, and sessions get transcript + summary + action items
  filed automatically. (Fathom works on Zoom PMI sessions too.)
- **Tier 2 — Supported if used:** vendors we've built an API/webhook source
  for (Fireflies would be first, *if mentor usage justifies it*). Same
  automatic filing; mentor connects their account once.
- **Tier 3 — Tolerated via the universal fallback:** any other note taker
  (Otter, Zoom AI Companion, future tools). If email ingestion is built,
  their summaries still land on the session; otherwise the mentor pastes
  notes manually.

## 7. Recommendations and the decisions to make

1. **Survey the mentors first.** Which note takers are actually in use today?
   The build order should follow reality, not the market map. (If usage is
   mostly Fathom plus scattered others, Tier 2 may need no new vendor at all.)
2. **Close the two open Fathom decisions** (team key vs per-mentor keys;
   enable in production) — it's built and verified, and it already covers
   Meet, Zoom, and Teams, which makes it the strongest single answer to
   "multiple vendors."
3. **Build the email-ingestion fallback before any additional API vendor.**
   One build covers every tool a mentor might show up with — including the
   two popular ones (Otter, Zoom AI Companion) that can never be integrated
   directly — and it de-risks vendor churn.
4. **Add Fireflies as the next API source only if the survey shows real
   usage.** Its free-tier API key makes it the cheapest possible add.
5. **Hold Recall.ai in reserve.** Revisit only if CBM's goal shifts from
   "support the mentor's tool" to "guarantee notes on every session."

## 8. Privacy note (applies to every option)

Whatever is supported, session participants are being recorded and
transcribed by a third-party AI service, and transcripts/summaries get stored
in the CRM where the mentor team can read them. CBM should decide the consent
posture once, vendor-independently: does the client agree at engagement start
(intake terms), or per meeting (the note-taker's own join announcement)?
Fathom/Fireflies/Read all announce themselves in the meeting; Meet native
shows a recording indicator. The existing AI-summary privacy sign-off
(`COMMS_AI_SUMMARY`, still off) is a related but separate decision.
