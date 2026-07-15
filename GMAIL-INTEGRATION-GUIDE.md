# Gmail Integration — Setup Guide

Step-by-step instructions for activating the Communications (Gmail
conversation) integration. Follow the parts **in order**: Google first, then
the CRM, then the app, then verify. Do everything against **crm-test / the
test app first**; repeat Parts 2–4 for prod once the test verification passes.

- What it does: the app reads each manager's `@cbmentors.org` mailbox, keeps
  only mail exchanged with the contacts of their active engagements /
  partners / sponsors, strips quoted text and signatures, stores the result as
  **conversations on the CRM record**, and lets managers read and reply from
  the session tools' Communications tab. Optional: Claude-generated summaries.
- Design: `prds/communications-gmail-integration.md`.
  CRM entity details: `cconversation-entity.md`.
- Everything is gated by `GMAIL_SYNC` (default off). Nothing in this guide
  changes behavior until Part 3 flips that flag.

## Prerequisites (already in place — verify, don't build)

| Requirement | Where it came from | How to check |
|---|---|---|
| Google service account | **Does NOT exist yet** (verified 2026-07-11 — the v0.11.0 mailbox-check code shipped without credentials) | Created from scratch in Part 1 |
| Managed Postgres + `delivery-worker` + pre-deploy migrate | V2 activation | `/healthz` shows `durableStore: true` |
| App at **v0.35.0 or later** | The Communications build | `/healthz` version |
| Managers have a CBM mailbox + login | Mentor provisioning | Each syncing manager's `CMentorProfile` has `cbmEmail` set AND an assigned login User — **both are required**; profiles missing either are silently skipped |

---

## Part 1 — Google: create the service account + authorize the Gmail scopes

No service account exists yet, so this part creates one from scratch. A
*service account* is a robot Google identity (JSON-key authentication, no
inbox); Google assigns it a ~21-digit **OAuth2 Client ID**, which is what the
Domain-wide Delegation screen lists. All of Part 1 is Google-side.

The full step-by-step (create project → create service account → download the
JSON key → enable the Gmail API → Add new delegation row with the key's
`"client_id"` + the two scopes → put the JSON in the overlay) is in
**`prds/communications-gmail-integration.md` §3.1** — follow it verbatim.
The two scopes, for copy-paste:

```
https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send
```

> **v0.40.0 addition:** the sessions Google Calendar integration
> (`csession-calendar-field.md`) needs a THIRD scope on the **same**
> delegation row (all scopes for one client id live in one row — edit the
> row, don't add a second): `https://www.googleapis.com/auth/calendar.events`
> — plus the **Google Calendar API** enabled in the same GCP project. Full
> three-scope value:
>
> ```
> https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/calendar.events
> ```

> Security note (for the record): domain-wide delegation is domain-wide — the
> app code restricts impersonation to (a) enumerated managers' mailboxes for
> sync and (b) the signed-in user's own mailbox for search/send, and logs every
> access. The scopes stay read+send only (no modify/delete). Accepted in the
> design; see the plan §3.4.

## Part 2 — CRM: build the entities (crm-test first)

Full field-by-field spec: **`cconversation-entity.md`**. Every step below is
one action in the EspoCRM admin UI.

### 2.1 Create the two entities and their fields

1. Go to **Administration → Entity Manager → Create Entity**. Name:
   `CConversation`, type **Base**. Save.
2. In **CConversation → Fields**, add each field with **Add Field**:
   - `conversationStatus` — type **Enum**, options `Open`, `Closed`,
     `Uncertain`, default `Open`
   - `summary` — type **Text**
   - `actionItems` — type **Text**
   - `keyTopics` — type **Varchar**, max length 255
   - `participants` — type **Varchar**, max length 500
   - `firstMessageAt` — type **Date-Time**
   - `lastMessageAt` — type **Date-Time**
   - `messageCount` — type **Integer**
   - `summarizedAt` — type **Date-Time**, **no default value** (must be able
     to stay empty)
3. Go back to **Administration → Entity Manager** and click
   **Create Entity** again. Name: `CCommunication`, type **Base**. Save.
4. Go to **Administration → Entity Manager**, click the **Communication**
   entity (custom entities show without their internal `C` prefix), then
   click **Fields**. Add each field below with **Add Field**:
   - `direction` — type **Enum**, options `Inbound`, `Outbound`
   - `sentAt` — type **Date-Time**
   - `fromAddress` — type **Varchar**, max length 255 (**NOT the Email field
     type** — an email-type field silently stores nothing)
   - `fromName` — type **Varchar**, 255
   - `toAddresses` — type **Varchar**, 500
   - `ccAddresses` — type **Varchar**, 500
   - `snippet` — type **Varchar**, 255
   - `bodyCleaned` — type **Wysiwyg**
   - `rfcMessageId` — type **Varchar**, 255
   - `gmailThreadId` — type **Varchar**, 64
   - `gmailMessageId` — type **Varchar**, 64
   - `sourceMailbox` — type **Varchar**, 255

### 2.2 The relationships

**UI orientation** (Entity Manager → an entity → Relationships): the button is
**+ Create Link**; the list columns are **Foreign Link | Link Type | Link |
Foreign Entity**. In the create/edit dialog there are TWO panels each with a
"Name" field: the **left panel is the entity you're standing in** (its Name =
the **Link** column) and the **right panel is the other entity** (its Name =
the **Foreign Link** column). EspoCRM shows custom entities WITHOUT their
internal `C` prefix — "Conversation" in the UI is `CConversation` to the API.
EspoCRM's link types are directional: **One-to-Many means the LEFT entity is
the One and the RIGHT entity is the Many.** Never use One-to-One Right/Left
here.

**Deleting a wrong build first** (e.g. crm-test as first built): custom
relationship rows have a small **▾ arrow at the far right** → **Remove**; rows
without the arrow are system links — leave them. Removing a relationship
removes BOTH sides, so each one is deleted once, from either entity's screen.
The first crm-test build required removing, on **Communication →
Relationships**: the row with Link `conversation` (Foreign Entity
Conversation) and the row with Link `contact` (Foreign Entity Contact — a
per-message contact link that isn't in this design at all); and on
**Conversation → Relationships**: the rows with Link `engagements`,
`partnerProfiles`, `sponsorProfiles`, and `contacts`. Safe while no data
exists.

**Where you must be standing: Entity Manager → Conversation → Relationships.**
The dialog's left panel is FIXED to whatever entity you opened — it cannot be
changed inside the dialog. Every numbered step below assumes the left panel
says **Conversation**; if your left panel says anything else (Engagement,
Contact, …), close the dialog and reopen from Conversation's Relationships
screen. (Creating from the OTHER entity's screen does produce the same
relationship, but then the two Name values must be SWAPPED — e.g. from
Engagement: left Name `conversations`, right Entity Conversation, right Name
`engagements`. Unless you're deliberately doing that, always start from
Conversation so the steps below apply verbatim. What actually matters is
which entity each name lands on: `engagements`/`partnerProfiles`/
`sponsorProfiles`/`contacts`/`communications` must end up on the
**Conversation** side, and `conversations`/`conversation` on the other
entity's side.)

**Link 1 — Engagements**
1. Go to **Administration → Entity Manager** and click the **Conversation**
   entity.
2. Click **Relationships**.
3. Click **+ Create Link**. Confirm the dialog's LEFT panel header says
   **Conversation** — if it says anything else, you opened the dialog from
   the wrong entity: close it and restart at step 1.
4. **Link Type**: **Many-to-Many**
5. Left panel (Conversation) **Name**: `engagements`  **Label**: `Engagements`
6. Right panel **Entity**: **Engagement**
7. Right panel **Name**: `conversations` (lowercase, plural, exactly — the app
   reads `GET /CEngagement/{id}/conversations`)  **Label**: `Conversations`
8. **Save**. Conversation's Relationships list now shows: Foreign Link
   `conversations` | Many-to-Many | Link `engagements` | Engagement.

**Link 2 — Partner Profiles**
1. Go to **Administration → Entity Manager** and click the **Conversation**
   entity.
2. Click **Relationships**.
3. Click **+ Create Link**. Confirm the LEFT panel header says
   **Conversation**.
4. **Link Type**: **Many-to-Many**
5. Left panel (Conversation) **Name**: `partnerProfiles`  **Label**: `Partner Profiles`
6. Right panel **Entity**: **Partner Profile**
7. Right panel **Name**: `conversations`  **Label**: `Conversations`
8. **Save**.

**Link 3 — Sponsor Profiles**
1. Go to **Administration → Entity Manager** and click the **Conversation**
   entity.
2. Click **Relationships**.
3. Click **+ Create Link**. Confirm the LEFT panel header says
   **Conversation**.
4. **Link Type**: **Many-to-Many**
5. Left panel (Conversation) **Name**: `sponsorProfiles`  **Label**: `Sponsor Profiles`
6. Right panel **Entity**: **Sponsor Profile**
7. Right panel **Name**: `conversations`  **Label**: `Conversations`
8. **Save**.

**Link 4 — Contacts**
1. Go to **Administration → Entity Manager** and click the **Conversation**
   entity.
2. Click **Relationships**.
3. Click **+ Create Link**. Confirm the LEFT panel header says
   **Conversation**.
4. **Link Type**: **Many-to-Many**
5. Left panel (Conversation) **Name**: `contacts`  **Label**: `Contacts`
6. Right panel **Entity**: **Contact**
7. Right panel **Name**: `conversations`  **Label**: `Conversations`
8. **Save**. Note: EspoCRM auto-prefixes custom links on built-in entities,
   so Contact's side will save as `cConversations` — expected and fine (the
   app never reads that side; only the four record entities need the exact
   `conversations` name, and Engagement/Partner/Sponsor take it as typed).

**Link 5 — Communications (the only one that is NOT Many-to-Many)**
1. Go to **Administration → Entity Manager** and click the **Conversation**
   entity.
2. Click **Relationships**.
3. Click **+ Create Link**. Confirm the LEFT panel header says
   **Conversation**.
4. **Link Type**: **One-to-Many** (Conversation is the left = the One; one
   conversation has many messages)
5. Left panel (Conversation) **Name**: `communications`  **Label**: `Communications`
6. Right panel **Entity**: **Communication**
7. Right panel **Name**: `conversation` (singular — each message belongs to one
   conversation)  **Label**: `Conversation`
8. **Save**. The list shows: Foreign Link `conversation` | One-to-Many |
   Link `communications` | Communication.

### 2.3 Enable Multiple Assigned Users + Collaborators on Conversation

These are TWO SEPARATE checkboxes creating two separate fields (verified live
2026-07-14 — checking only Collaborators leaves the entity without the
`assignedUsers` field the integration writes):

1. Go to **Administration → Entity Manager** and click the **Conversation**
   entity.
2. Click **Edit** (the entity's own edit button — not Fields, not Layouts).
3. Check **Multiple Assigned Users**. **This one is REQUIRED** — it creates
   the multi-user `assignedUsers` field; the sync stamps the owning managers
   there so read-own roles see their conversations (the same setting
   CEngagement and CSession have on).
4. Check **Collaborators** as well (matches the verified crm-test build).
5. **Save**.

### 2.4 Grants

Four roles get access. crm-test role names below; **on the prod CRM the API
user's role is named `CustomAppAPIRole` instead of `ClientMentorIntakeRole`**
(the other three names match). The entities appear in the role editor as
**Conversation** and **Communication**.

**Role 1 of 4 — ClientMentorIntakeRole** (the intake API user — the sync's
writer):
1. Go to **Administration → Roles**.
2. Click **ClientMentorIntakeRole**, then **Edit**.
3. Scroll to **Conversation**: set **Access = enabled**, **Create = yes**,
   **Read = all**, **Edit = all**, **Delete = no**.
4. Scroll to **Communication**: set **Access = enabled**, **Create = yes**,
   **Read = all**, **Edit = all**, **Delete = no**.
5. Scroll to **User**: set **Access = enabled**, **Read = all** (leave
   Create/Edit/Delete = no). Without this, the sync's owner stamp — relating
   the owning manager's User into the conversation's Assigned Users — fails
   with `cannotRelateForbidden (User, read)`: EspoCRM requires the relating
   user to be able to READ the record being related. The stamp is
   best-effort (a WARNING per message, conversations still store), and with
   the manager roles reading Conversation at "all" (below) visibility does
   not depend on it — but any future move to read-own does, so grant it.
   (Discovered live on the 2026-07-14 prod rollout; the crm-test build had
   the same gap and its conversations are unstamped.)
6. Click **Save**.

**Role 2 of 4 — Mentor Role:**
1. **Administration → Roles → Mentor Role → Edit**.
2. **Conversation**: **Access = enabled**, **Create = no**, **Read = all**,
   **Edit = no**, **Delete = no**.
3. **Communication**: **Access = enabled**, **Create = no**, **Read = all**,
   **Edit = no**, **Delete = no**.
4. **Save**.

**Role 3 of 4 — Partner Manager Role:**
1. **Administration → Roles → Partner Manager Role → Edit**.
2. **Conversation**: **Access = enabled**, **Create = no**, **Read = all**,
   **Edit = no**, **Delete = no**.
3. **Communication**: **Access = enabled**, **Create = no**, **Read = all**,
   **Edit = no**, **Delete = no**.
4. **Save**.

**Role 4 of 4 — Sponsor Manager Role:**
1. **Administration → Roles → Sponsor Manager Role → Edit**.
2. **Conversation**: **Access = enabled**, **Create = no**, **Read = all**,
   **Edit = no**, **Delete = no**.
3. **Communication**: **Access = enabled**, **Create = no**, **Read = all**,
   **Edit = no**, **Delete = no**.
4. **Save**.

(The manager roles get Read = all because the app only shows a manager the
conversations linked to records they own; the broader CRM-side read is the
simple, working setting.)

### 2.5 Layouts (optional but recommended)

1. On the detail layout of **CEngagement**, **CPartnerProfile**, and
   **CSponsorProfile**, add a **Conversations** relationship panel (columns:
   name, conversationStatus, messageCount, lastMessageAt) — this is what
   makes correspondence visible to CRM users on the record.

### 2.6 Rebuild

1. **Administration → Rebuild.**

## Part 3 — App: enable the integration

Config goes in the gitignored App Platform overlay for the target app
(`.do/app.prod.yaml` = crm-test app, `.do/app.prod-crm.yaml` = prod app).

1. Add to the **web** service AND the **worker** envs:

   ```yaml
   - key: GMAIL_SYNC
     value: "true"
   ```

   (The web app needs it for the endpoints + `commsEnabled`; the worker for
   the sync loop. `DATABASE_URL` must already be on both — it is.)
2. Optional tuning (worker): `GMAIL_SYNC_SECONDS` (default 300),
   `GMAIL_BACKFILL` (default `newer_than:365d` — the initial history window),
   `COMMS_ENGAGEMENT_STATUSES`, `COMMS_PARTNER_EXCLUDED_STATUSES`.
3. Apply:

   ```bash
   doctl apps update <app-id> --spec .do/app.prod.yaml --wait
   ```

   The PRE_DEPLOY migrate job runs Alembic `0004_comms_sync` automatically
   (the sync-cursor + curation-override tables).
4. **Local dev** instead: set `GMAIL_SYNC=true`, `DATABASE_URL` (the
   docker-compose Postgres), and `GOOGLE_SERVICE_ACCOUNT_JSON` in `.env`,
   run `uv run alembic upgrade head`, then `python -m worker` alongside
   uvicorn.

The service-account credentials need **no change** — the Gmail client reads
the same key the mailbox check uses (Email Setup config first, `GOOGLE_*` env
fallback).

## Part 4 — Verify (the go-live check)

Use a manager whose `CMentorProfile` has a `cbmEmail` + assigned User and who
owns at least one **active** engagement with a contact whose email you control.

1. **Worker is syncing.** `doctl apps logs <app-id> delivery-worker --type run -f`
   — expect `gmail sync enabled (every 300s)` at startup, then
   `gmail sync pass: {'mailboxes': N, 'fetched': …, 'stored': …, 'errors': 0}`
   each cycle. `mailboxes: 0` means no profile passed the cbmEmail+User check.
2. **Ingest.** From the contact's address, email the manager's
   `@cbmentors.org` address (subject e.g. `ZZTEST comms check`); have the
   manager reply from Gmail. Within a cycle: a `CConversation` appears in the
   CRM linked to the engagement, with two `CCommunication` messages, bodies
   cleaned (no quoted tails/signatures).
3. **CRM visibility.** Open the engagement in EspoCRM — the Conversations
   panel shows it.
4. **App read.** Sign in to the session tool as the manager → the record →
   Communications tab: the conversation lists and opens; quoted text renders
   demoted; "Open in Gmail" links work.
5. **Send.** Reply from the tab → the mail arrives at the contact's address
   threaded on the same conversation, shows in the manager's Gmail **Sent**,
   and appears in the tab immediately.
6. **Curation.** "Not related — remove" hides a conversation (and it stays
   hidden after the next sync); "Add emails…" finds an unrelated thread in
   the manager's mailbox and attaches it.
7. **Dedup.** CC a second manager on a test mail: still ONE CCommunication,
   both managers see the conversation.
8. **Cleanup**: delete the ZZTEST conversations/communications in the CRM UI.

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| `Gmail auth failed for <mailbox>` in worker logs | Scopes not authorized for the Client ID (Part 1), still propagating, or the Gmail API isn't enabled on the GCP project |
| `gmail sync: no Google service-account credentials configured` | No key in Email Setup and no `GOOGLE_SERVICE_ACCOUNT_JSON` env on the worker |
| `mailboxes: 0` in the sync pass | No CMentorProfile has BOTH `cbmEmail` and an assigned login User |
| Conversation created but invisible in the app | Gate role lacks read on the entities, or `assignedUsers` wasn't enabled on CConversation (Part 2 steps 4–5) |
| `create CConversation failed: HTTP 403` | `CustomAppAPIRole` missing create/edit grants (Part 2 step 5) |
| Endpoints return 503 "isn't enabled" | `GMAIL_SYNC` not set on the **web** component |
| Endpoints return 503 "needs the database" | `DATABASE_URL` missing on the web component |
| Tab shows the sample banner | The browser cached old config — refresh; or `commsEnabled` false (web flag) |
| Mail from a contact never ingests | The record isn't in an active status, or the contact's sending address isn't on their CRM record — use "Add emails…" once and add the address to the contact |

## Part 5 — Optional: AI summaries

Off by default; everything above works without it. Enabling sends
conversation text to the Anthropic API (30-day retention) — get CBM's
sign-off first.

1. Create an API key at **console.anthropic.com** (Settings → API keys).
2. Add to the **worker** envs (encrypted):

   ```yaml
   - key: COMMS_AI_SUMMARY
     value: "true"
   - key: ANTHROPIC_API_KEY
     type: SECRET
     value: "sk-ant-…"
   ```

   Optional: `SUMMARY_MODEL` (default `claude-opus-4-8`).
3. Redeploy. The next sync pass summarizes every conversation whose
   `summarizedAt` is empty (i.e. all of them, once) and re-summarizes any
   conversation when new mail arrives. Expect ≈ $0.02–0.03 per summary at
   CBM volume.
4. Verify: conversations gain a status chip, a 2–4 sentence summary, and
   action items in both the CRM record and the tab.

## Rollback

Set `GMAIL_SYNC=false` (web + worker) and re-apply the spec — the endpoints
503, the tab reverts to the scaffold, the worker stops syncing. Stored
conversations remain in the CRM (harmless); Postgres cursors are kept, so
re-enabling resumes incrementally rather than re-backfilling.

## Prod rollout (after crm-test passes) — ✅ DONE 2026-07-14

Completed 2026-07-14: prod CRM entities/grants built (three gaps caught by
read-only schema probes against crm-test's as-built metadata — worth
re-running that diff on any future instance), overlay applied, first
backfill pass clean (7 mailboxes, 1061 stored, 0 errors). Open: first live
SEND on prod, and the §2.4 Role-1 **User Read=all** grant + one-shot
`GMAIL_RESYNC=true` on both CRMs (owner-stamp backfill).

1. Part 2 on the prod CRM (same entities/grants/layouts).
2. Part 1 covers prod already if prod uses the same Workspace domain + service
   account (it does — `@cbmentors.org`); otherwise repeat it for the prod key.
3. Part 3 in `.do/app.prod-crm.yaml`, apply to the prod app.
4. Part 4 against a real manager, then announce to staff.
