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

Relationships — **create every one of these while standing in Entity Manager →
CConversation → Relationships → Create Relationship**, so CConversation is
always the LEFT column of the dialog. (EspoCRM's type names are directional:
"One-to-Many" means *the left entity is the One, the right entity is the
Many*. That direction trap is what inverted the first crm-test build.)

| # | Relationship Type | Left (CConversation) Name / Label | Right Entity | Right Name / Label |
|---|---|---|---|---|
| 1 | **Many-to-Many** | `engagements` / Engagements | CEngagement | **`conversations`** / Conversations |
| 2 | **Many-to-Many** | `partnerProfiles` / Partner Profiles | CPartnerProfile | **`conversations`** / Conversations |
| 3 | **Many-to-Many** | `sponsorProfiles` / Sponsor Profiles | CSponsorProfile | **`conversations`** / Conversations |
| 4 | **Many-to-Many** | `contacts` / Contacts | Contact | **`conversations`** / Conversations |
| 5 | **One-to-Many** | `communications` / Communications | CCommunication | `conversation` / Conversation |

- Rows 1–4 are **Many-to-Many** (never One-to-Many): one conversation can
  attach to several records and one record has many conversations.
- Row 5 is **One-to-Many** *from CConversation* (one conversation, many
  messages). If created from CCommunication instead, the type flips to
  Many-to-One. Do not use One-to-One Right/Left anywhere.
- The right-side Name on rows 1–3 **must be exactly `conversations`**
  (plural) — the app reads `GET /{parent}/{id}/conversations`. On row 4,
  EspoCRM auto-prefixes custom links on the built-in Contact entity, so its
  side saves as `cConversations` — expected; the app never reads that side.

**Enable Collaborators on `CConversation`** (Entity Manager → CConversation →
Edit → the **Collaborators** checkbox — the multi-user *Assigned Users* field,
the same toggle CEngagement and CSession have on): the sync stamps the owning
manager(s) there so read-own roles see their conversations (same requirement
as `CSession`; see CLAUDE.md's session-tools ACL bullet).

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

Prescribed values (one per dropdown — no alternatives). Role names: the intake
API user's role is **`ClientMentorIntakeRole` on crm-test** and
**`CustomAppAPIRole` on prod**; the three manager roles are named the same on
both: **Mentor Role**, **Partner Manager Role**, **Sponsor Manager Role**.

| Role | Entity | Access | Create | Read | Edit | Delete |
|---|---|---|---|---|---|---|
| ClientMentorIntakeRole (prod: CustomAppAPIRole) | Conversation | enabled | yes | all | all | no |
| ClientMentorIntakeRole (prod: CustomAppAPIRole) | Communication | enabled | yes | all | all | no |
| Mentor Role | Conversation | enabled | no | all | no | no |
| Mentor Role | Communication | enabled | no | all | no | no |
| Partner Manager Role | Conversation | enabled | no | all | no | no |
| Partner Manager Role | Communication | enabled | no | all | no | no |
| Sponsor Manager Role | Conversation | enabled | no | all | no | no |
| Sponsor Manager Role | Communication | enabled | no | all | no | no |

Rationale for Read = all on the manager roles: the app only shows a manager
the conversations linked to records they own, so the broader CRM-side read is
the simple, working setting. Step-by-step click path:
`GMAIL-INTEGRATION-GUIDE.md` §2.4.

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
