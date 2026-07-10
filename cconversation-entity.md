# `CConversation` + `CCommunication` — CRM build specification

**Status: NOT BUILT — required for the Communications integration** (the app
side shipped, gated off by `GMAIL_SYNC`; see
`prds/communications-gmail-integration.md`). This is the CRM-team handoff, in
the style of `cintake-submission-entity.md`. Build on **crm-test first**; prod
follows after live verification. Should be tracked as a crmbuilder program in
`ClevelandBusinessMentors/programs/` (e.g. `MN-Communications.yaml`) per that
repo's requirement-first process.

## What these are

One **`CConversation`** per email conversation between a CBM manager and the
contacts of an engagement / partner / sponsor record, holding the optional AI
summary and the links to the records it belongs to. One **`CCommunication`**
per email message, storing the *cleaned* body (quotes/signatures stripped by
the app) — the raw original stays in Gmail, reachable via the stored Gmail ids.
The app's sync worker creates/updates both; staff read them in the session
tools AND directly on the CRM record's detail view (that visibility is the
point of storing them in the CRM).

## 1. Entity: `CConversation`

Type: Base. Name field = subject of the first message.

| Field | Type | Options / notes |
|---|---|---|
| `name` | varchar (255) | Subject (app-written) |
| `conversationStatus` | enum | `Open`, `Closed`, `Uncertain` — default `Open` |
| `summary` | text | AI summary (empty when the AI layer is off) |
| `actionItems` | text | newline-separated action items (AI) |
| `keyTopics` | varchar (255) | comma-separated topic tags (AI) |
| `participants` | varchar (500) | display names, denormalized for lists |
| `firstMessageAt` | datetime | |
| `lastMessageAt` | datetime | |
| `messageCount` | int | |
| `summarizedAt` | datetime | null = (re-)summarization pending — **must be nullable, no default** |

Links (define BOTH sides; all are many-to-many except `communications`):

| Link on CConversation | Type | Foreign entity | Reverse link (foreign side) |
|---|---|---|---|
| `engagements` | manyMany | CEngagement | **`conversations`** |
| `partnerProfiles` | manyMany | CPartnerProfile | **`conversations`** |
| `sponsorProfiles` | manyMany | CSponsorProfile | **`conversations`** |
| `contacts` | manyMany | Contact | `conversations` |
| `communications` | hasMany | CCommunication | `conversation` (belongsTo) |

The reverse link name on each parent **must be exactly `conversations`** — the
app reads `GET /{parent}/{id}/conversations`.

**Enable `assignedUsers` (collaborators) on `CConversation`** — the sync stamps
the owning manager(s) so read-own roles see their conversations (same
requirement as `CSession`; see CLAUDE.md's session-tools ACL bullet).

## 2. Entity: `CCommunication`

Type: Base. One per email message.

| Field | Type | Options / notes |
|---|---|---|
| `name` | varchar (255) | Subject |
| `direction` | enum | `Inbound`, `Outbound` |
| `sentAt` | datetime | |
| `fromAddress` | varchar (255) | **plain varchar — NOT the email field type** (an email-type field silently stores nothing; the `submitterEmail` lesson) |
| `fromName` | varchar (255) | |
| `toAddresses` | varchar (500) | comma-joined |
| `ccAddresses` | varchar (500) | comma-joined |
| `snippet` | varchar (255) | first ~200 chars of the cleaned text |
| `bodyCleaned` | wysiwyg | cleaned HTML; quoted reply kept in `<blockquote class="quoted-reply">` |
| `rfcMessageId` | varchar (255) | RFC822 Message-ID — the global dedup key; **index it** |
| `gmailThreadId` | varchar (64) | |
| `gmailMessageId` | varchar (64) | |
| `sourceMailbox` | varchar (255) | which manager's mailbox this copy came from |

Links: `conversation` (belongsTo CConversation — reverse `communications`).

## 3. Grants

| Role | CConversation | CCommunication |
|---|---|---|
| **`CustomAppAPIRole`** (intake API user — the sync's writer) | create + read + edit | create + read + edit |
| Session-tool gate roles (Mentor Team / Partner Management Team / Sponsor Management Team members) | read (own is fine — the sync owner-stamps via assignedUsers) | **read: team or all** (messages aren't stamped; own-scope would hide them) |

Simplest working set: gate roles get read=all on both (conversation content is
only *reachable* in the app through records the user already owns). If CBM
wants tighter CRM-side visibility, read=team on both + put the sync's records
in a team — decide at build time.

## 4. Layout

Add a **Conversations** relationship panel to the detail layouts of
`CEngagement`, `CPartnerProfile`, and `CSponsorProfile` (columns: name,
conversationStatus, messageCount, lastMessageAt) — this is what makes the
correspondence visible to CRM users on the record. Optionally a panel of
`communications` on the CConversation detail view (name, direction, sentAt,
fromName).

## 5. Build checklist

1. Create both entities + fields exactly as named above (crm-test).
2. Create the links with the exact reverse-link names (`conversations`).
3. Enable `assignedUsers` on `CConversation`.
4. Index `CCommunication.rfcMessageId` (it's queried on every ingest).
5. Grants per §3 (API role + the three gate roles).
6. Layout panels per §4.
7. Rebuild.

## 6. App-side verification (after the build)

Run with `GMAIL_SYNC=true` against crm-test (needs the Google scopes from
`prds/communications-gmail-integration.md` §3.1 authorized):

- worker log shows a sync pass (`gmail sync pass: {...}`);
- a mail exchange with a test engagement's contact appears as a CConversation
  linked to the engagement, with cleaned CCommunication bodies;
- the same email CC'd to a second manager stays ONE CCommunication;
- the Communications tab lists/opens it as the manager; reply lands on the
  real Gmail thread AND back in the tab;
- `CIntakeSubmission`-style cleanup: delete any ZZTEST conversations in the UI.
