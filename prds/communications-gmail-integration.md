# Communications — Gmail Conversation Integration (Design & Plan)

**Status: APPROVED PLAN — not yet built.** Decisions recorded 2026-07-10 with Doug.
This wires the session tools' **Communications tab** (today a UI-only scaffold,
`sessions/frontend/`) to real email: the app ingests each manager's
`@cbmentors.org` Gmail, strips the redundant quoted text, stores the result as
**conversations in the CRM** attached to the engagement / partner / sponsor
record, summarizes them with Claude, and lets the manager reply from the tab.

Heavily informed by the proven pipeline in the **CRM_Extender** project
(`~/Dropbox/Projects/CRM_Extender/CRMExtender` — see "Prior art" at the end);
we port its cleaning architecture and sync patterns rather than reinvent them.

---

## 1. Decisions (made 2026-07-10)

| Question | Decision |
|---|---|
| Email source | **Gmail direct** — the existing Google service account with domain-wide delegation, extended with Gmail scopes; no per-user OAuth, no EspoCRM IMAP accounts. |
| Source of truth for display | **CRM entities** — new `CConversation` + `CCommunication` records, parent-linked to the engagement/partner/sponsor and readable by CRM users on the record. |
| Cleaning | Deterministic (libraries + tuned regex, ported from CRM_Extender) at ingest time. Raw mail is **not** copied into the CRM — Gmail remains the immutable original; each stored message keeps its Gmail ids for deep-linking. |
| LLM layer | **Built in v1 but OPTIONAL** (revised 2026-07-10): per-conversation summary, open/closed status, action items via the Claude API, refreshed when new mail arrives, behind a free triage gate — the whole layer is gated by a `COMMS_AI_SUMMARY` flag (default **off**) + an Email Setup toggle, and the UI degrades cleanly when disabled. |
| Ingest scope | **Active records only** — engagements in active statuses, current partners/sponsors. A record turning active triggers a retroactive backfill of its contacts' mail history. |
| v1 scope | **Read + send** — the compose/reply modal ships working in v1 (`gmail.readonly` + `gmail.send`). |
| Record attachment | Live contact-address matching at thread level + record-level include/exclude overrides (shared across co-mentors, stored app-side). |

---

## 2. Architecture overview

```
                       ┌─────────────────────────────────────────────┐
   Google Workspace    │  delivery-worker (existing, python -m worker)│
  ┌──────────────┐     │  ┌────────────────────────────────────────┐ │
  │ manager      │◄────┼──│ Gmail sync loop (new)                  │ │
  │ mailboxes    │ SA  │  │  enumerate mailboxes → historyId pull  │ │
  │ @cbmentors.org│ DWD │  │  → match to active records' contacts  │ │
  └──────────────┘     │  │  → clean (strip quotes/signatures)     │ │
                       │  │  → dedup by Message-ID                 │ │
        ▲              │  │  → upsert CConversation/CCommunication │ │
        │ send as      │  │  → triage → Claude summary             │ │
        │ manager      │  └────────────────────────────────────────┘ │
        │              └───────────────┬─────────────────────────────┘
  ┌─────┴────────────┐                 │ create/update (API user)
  │ web (sessions    │                 ▼
  │ router, per-user │   ┌──────────────────────────┐   ┌───────────┐
  │ token)           │──►│ EspoCRM                  │   │ Postgres  │
  │  Communications  │   │  CConversation           │   │ sync state│
  │  tab read + send │   │  CCommunication          │   │ overrides │
  └──────────────────┘   │  linked to CEngagement/  │   └───────────┘
                         │  CPartner/CSponsorProfile│
                         └──────────────────────────┘
```

- **Reads in the UI run as the signed-in user** (portal SSO token, ACL-enforced),
  exactly like every other sessions read — via the parent record's link.
- **The sync worker writes as the intake API user** (`customapps`), like the
  submission pipeline — needs create/read/edit grants on the two new entities.
- **Gmail access (read + send) uses the service account** with domain-wide
  delegation, impersonating one specific mailbox per operation.

---

## 3. Google Workspace side

### 3.1 Configure Gmail access — step-by-step

The app reuses the Google service account that already does the Directory
mailbox check/creation (v0.11.0). Configuration = adding two Gmail scopes to
that account's EXISTING domain-wide delegation grant and enabling the Gmail
API. No new service account, no new key, no per-mentor step.

**Step 1 — Find the service account's Client ID.**
1. Open the service-account JSON key. It is either pasted into the admin
   **Email Setup** screen (`/mentoradmin` → Email Setup) or stored as the
   `GOOGLE_SERVICE_ACCOUNT_JSON` value in the gitignored deploy overlay.
2. Copy the value of the `"client_id"` property — a number of ~21 digits.
   (Also note the `"project_id"` value; Step 2 needs it.)
   Alternative: console.cloud.google.com → IAM & Admin → Service Accounts →
   click the account → copy **Unique ID**.

**Step 2 — Enable the Gmail API on the GCP project.**
1. Go to **console.cloud.google.com** and sign in with the Google account
   that owns the service account's project.
2. In the project picker (top bar), select the project whose id matches the
   key's `"project_id"`.
3. Go to **APIs & Services → Library**.
4. Search for **Gmail API** and open it.
5. Click **Enable**. (If it says "Manage" instead, it is already enabled —
   nothing to do.)

**Step 3 — Add the Gmail scopes to the delegation grant.**
1. Go to **admin.google.com** and sign in as a Google Workspace
   **super-admin** for the cbmentors.org domain.
2. Go to **Security → Access and data control → API controls**.
3. Click **Manage Domain Wide Delegation** (bottom of the page).
4. Find the row whose **Client ID** matches the number from Step 1 (it
   exists — it carries the Directory scopes today).
5. Click that row, then click **Edit**.
6. In the **OAuth scopes** box, KEEP everything already there and APPEND
   these two, separated by commas:

   ```
   https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send
   ```

7. Click **Authorize**.
8. Confirm the row now lists the Directory scope(s) AND both Gmail scopes.

**Step 4 — Wait for propagation.**
1. Google applies delegation changes within minutes, occasionally up to an
   hour. Nothing else to click.

**Step 5 — Verify.**
1. There is no test button in Google Admin; the proof is the app itself.
   After `GMAIL_SYNC=true` is deployed (§Part 3 of
   `GMAIL-INTEGRATION-GUIDE.md`), watch the worker logs:
   - success: `gmail access as <mailbox> (scope=readonly)` lines and a
     `gmail sync pass: {...}` summary;
   - not authorized / not propagated yet: `Gmail auth failed for <mailbox>`
     — re-check Step 3's scope list, then wait out Step 4.

### 3.2 Token minting and the subject rule

`core/google_directory.py` already mints delegated tokens with an arbitrary
`subject`. Factor that into a shared `core/google_auth.py` (or extend the
existing class) so a new `core/gmail.py` `GmailClient` can be constructed
**per mailbox**:

- **Sync**: `subject = <manager's cbmEmail>` for each enumerated mailbox.
- **UI send/search**: `subject` is derived **only from the signed-in session's
  CRM identity** (their `CMentorProfile.cbmEmail` / linked User's userName) —
  never from request input. This is the control that scopes a domain-wide
  grant down to "your own mailbox only".
- Log every impersonated access (mailbox, operation, acting app identity).

Gmail is called via plain REST with `httpx` (same style as `google_directory`
— no `google-api-python-client` dependency). Endpoints used:
`users.history.list`, `users.messages.list/get` (`format=full`),
`users.threads.get`, `users.messages.send`, `users.getProfile` (initial
historyId).

### 3.3 Credential storage (already built)

No new mechanism: the service-account JSON stays in the encrypted `app_config`
Postgres store (Fernet keyed by `APP_ENCRYPTION_KEY`), managed through the
admin-only **Email Setup** screen, with `GOOGLE_*` env vars as fallback.
The Email Setup screen gains a "Gmail integration" toggle + a test button
("read 1 message from my own mailbox") so the whole feature can be turned
on/off at runtime without a deploy.

New deploy config: a `GMAIL_SYNC` master flag (default **false** — the entire
pipeline is a no-op until enabled, matching the project's gated-rollout
convention); `COMMS_AI_SUMMARY` (default **false**) + `ANTHROPIC_API_KEY`
(worker) only if/when the optional summary layer is enabled (§5.6).

### 3.4 Trust note (recorded, accepted)

Domain-wide delegation is domain-wide: the app restricts `subject` in code,
but the key + grant could technically read any mailbox. Accepted with these
mitigations: subject-derivation rule above, per-access logging, scopes limited
to `gmail.readonly`/`gmail.send` (no modify/delete), key stored encrypted,
and the CRM-visible result means mailbox access is observable, not silent.

---

## 4. CRM side — new entities (build handoff, like `cinformation-request-entity.md`)

### 4.1 `CConversation` — one email conversation

| Field | Type | Notes |
|---|---|---|
| `name` | varchar | Subject of the first message (truncated) |
| `conversationStatus` | enum: `Open`, `Closed`, `Uncertain` | From the LLM (`ai_status` in CRM_Extender terms); default `Open` |
| `summary` | text | LLM 2–4 sentence summary |
| `actionItems` | text | LLM bullet list (newline-joined) |
| `keyTopics` | varchar | comma-joined topic tags |
| `firstMessageAt` / `lastMessageAt` | datetime | drives sort + staleness |
| `messageCount` | int | |
| `participants` | text | display names/addresses (denormalized, for the list row) |
| `summarizedAt` | datetime | null ⇒ needs (re-)summarization |
| links | | `contacts` (linkMultiple → Contact); **`engagements`** (linkMultiple → CEngagement); **`partnerProfiles`** (linkMultiple → CPartnerProfile); **`sponsorProfiles`** (linkMultiple → CSponsorProfile); `communications` (hasMany → CCommunication) |

A conversation can attach to more than one record (a contact who spans an
engagement and a partnership), hence linkMultiple, not a single parent.
**Lesson applied:** custom linkMultiple links are read via `list_related` and
written via relate/unrelate — never `<link>Ids` on the record
([[espo-custom-linkmultiple-is-a-relationship]]).

### 4.2 `CCommunication` — one cleaned email message

| Field | Type | Notes |
|---|---|---|
| `name` | varchar | Subject |
| `direction` | enum: `Inbound`, `Outbound` | relative to CBM |
| `sentAt` | datetime | RFC822 Date |
| `fromAddress` / `fromName` | varchar | |
| `toAddresses` / `ccAddresses` | varchar | comma-joined |
| `snippet` | varchar | first ~200 chars of cleaned text |
| `bodyCleaned` | wysiwyg (html) | cleaned body; meaningful quoted reply kept inside `<blockquote class="quoted-reply">` (two-zone rendering), signatures/boilerplate removed |
| `rfcMessageId` | varchar | RFC822 `Message-ID` — the **global dedup key** |
| `gmailThreadId` / `gmailMessageId` / `sourceMailbox` | varchar | provenance + "open in Gmail" deep link (`https://mail.google.com/mail/u/<mailbox>/#all/<messageId>`) |
| links | | `conversation` (belongsTo CConversation), `fromContact` (belongsTo Contact, when resolved) |

**Raw mail is NOT stored in the CRM.** Gmail is the immutable original; the
`gmail*` ids let anyone recover it. (This also answers CRM_Extender's
"we accidentally overwrote the raw plain text" lesson — we never hold it.)

### 4.3 Grants and visibility

- **`CustomAppAPIRole`** (the intake API user): create/read/edit on both
  entities (edit needed for re-summarization + appends).
- **Staff/manager roles** (the session-tool gate roles): read on both. As with
  `CSession`, a plain `read-own` scope would hide them — the worker therefore
  **stamps `assignedUsers`** on each conversation with the owning manager(s)
  of every record it links (same owner-stamp pattern that fixed CSession
  visibility). Alternatively the CRM team can grant team-scope read; decide
  during the CRM build.
- **Layout**: add a Conversations panel to CEngagement/CPartnerProfile/
  CSponsorProfile detail views so CRM users see correspondence on the record —
  this is the whole point of the CRM-entities decision.
- Add both entities to the crmbuilder program set
  (`ClevelandBusinessMentors/programs/`, e.g. `MN-Communications.yaml`) per
  the repo's governance (requirement-first) process.

---

## 5. App side — the pipeline (new `comms/` package + worker loop)

### 5.1 Mailbox + scope enumeration

Each sync cycle (worker timer, default every 5 min, own interval env):

1. **Managers**: `CMentorProfile` rows with a linked login User and a
   `cbmEmail` — each is a mailbox to sync.
2. **Active records per domain** (reuses `sessions/config.py` reverse links):
   - mentor: the manager's engagements with `engagementStatus` in the active
     set (`Active`, `Assigned`, `Pending Acceptance`, `On-Hold`) — same list
     the sessions tools use;
   - partner: `managedPartners` with `partnershipStatus` in an env-configurable
     active set (default: not `Ended`/`Declined`);
   - sponsor: `managedSponsors` (all, or by a status field if one is added).
3. **Address book per mailbox**: the union of email addresses (primary +
   secondary) of every contact related to those records. Only mail matching
   these addresses is ever fetched-full/stored — the app never retains a
   manager's unrelated mail.

### 5.2 Incremental sync (port of CRM_Extender `sync.py`, adapted)

Per mailbox, in Postgres (`email_sync_state` table, Alembic `0004`):
`(mailbox, history_id, last_synced_at, initial_done)`.

- **Initial sync**: `messages.list` with a query built from the address book
  (`{from:a@x to:a@x cc:a@x} OR …`, chunked if long) bounded by
  `GMAIL_BACKFILL` (default `newer_than:365d`); store the profile's current
  `historyId`.
- **Incremental**: `history.list(startHistoryId=…, historyTypes=[messageAdded])`,
  fetch the added messages, keep only address-book matches, group by
  `threadId`. On a 404 (expired cursor) fall back to a **date-window re-query
  with one-day overlap** — dedup makes the overlap safe (CRM_Extender's
  `HistoryExpiredError → _backfill_sync` pattern, verbatim).
- **New-record backfill**: when a record enters the active set (or a contact
  gains an address), run a targeted historical query for just those addresses
  — this is what makes matching retroactive.
- Rate limiting (Gmail ~5 rps, same as CRM_Extender) + the worker's existing
  backoff/alerting conventions; sync results feed `core/monitoring` so the
  Phase-3 alerting covers this pipeline too.

### 5.3 Dedup and conversation formation

- **Message identity = RFC822 `Message-ID`** (falling back to
  `(mailbox, gmailMessageId)` when absent). Before creating a
  `CCommunication`, look up `rfcMessageId` — the same email seen in a
  co-mentor's CC'd mailbox becomes ONE stored message. (CRM_Extender left its
  `header_message_id` columns unused and accepted per-account duplicates; we
  need the cross-mailbox merge because engagements have co-mentors.)
- **Conversation identity**: Gmail `threadId` per mailbox, merged across
  mailboxes via the messages' Message-ID/References overlap — if an incoming
  thread contains a message already in a conversation, append to that
  conversation. Subject/participant heuristics are NOT used (matches
  CRM_Extender's decision; provider threading is trusted).
- **Creation gating** (port of `_should_create_conversation`): a thread only
  becomes a conversation if it matched the record's contacts (already
  guaranteed by scope) — plus the triage filter below keeps no-reply/marketing
  senders out entirely.
- On append: update `messageCount`, `lastMessageAt`, null `summarizedAt`
  (forces re-summary), and relate any newly-matched records.

### 5.4 Record attachment + curation overrides

Attachment rule, evaluated at ingest and on demand:

```
attach(conversation, record) =
      (any message ↔ any of record's contact addresses)  OR  included
  AND NOT excluded
```

Overrides live in Postgres (`conversation_override` table, Alembic `0004`):
`(parent_entity, parent_id, conversation_key, action include|exclude,
created_by, created_at)` — **record-level and shared** (an exclusion by one
co-mentor hides it for all; decided when storage moved to shared CRM records).
The sync consults overrides before relating/unrelating the CRM links, so the
CRM state always reflects the resolved rule.

Curation flows (endpoints in §6):
- **Exclude**: "Not related — hide from this engagement" on a conversation.
- **Include by search**: search the signed-in manager's mailbox live
  (readonly, as them), pick a thread, "Add to this engagement" → immediate
  targeted ingest of that thread + include row.
- **Fix the cause**: the include flow offers "also add <address> to
  <contact>'s record" (writes a secondary email address to the Contact as the
  user) — the durable fix; future mail auto-matches everywhere.

### 5.5 Cleaning module (`core/email_clean.py`, ported from CRM_Extender)

Port `email_parser.py` + `html_email_parser.py` (dual-track):

1. **HTML track**: `quotequail.quote_html` (keep first reply block) →
   BeautifulSoup structural removal by selector (`div.gmail_quote`,
   `blockquote[type=cite]`, signature containers, Outlook separators,
   unsubscribe footers, `#appendonsend` + following siblings) → text cleanup.
   Keep their edge-case guards verbatim: body-inside-`gmail_signature`
   re-parse (~10% of Gmail mail), `--` false-positive validation, valediction
   guard ("no substantive sentences after Regards,").
2. **Plain-text fallback**: `mail-parser-reply` + the regex layer — **retuned**:
   drop the financial-industry vocabulary (CFP/CPA credential lists, Forbes),
   keep the generic patterns (forwarded headers, `On … wrote:`, mobile sigs,
   legal disclaimers, `--`/`____` separators, line-unwrapping).
3. **Two-zone output** (their documented UI correction): the meaningful quoted
   reply chain is retained inside `<blockquote class="quoted-reply">` in
   `bodyCleaned` — de-emphasized by the frontend — while signatures/boilerplate
   are deleted outright.

New deps: `quotequail`, `beautifulsoup4`, `lxml`, `mail-parser-reply`.
Testing: build a fixture corpus (their approach: audit old-vs-new on a real
set before trusting it) from real CBM mail during crm-test verification;
sanitize with the existing `sanitizeHtml` on render regardless.

### 5.6 LLM layer — triage + summaries (OPTIONAL — flag-gated)

**The summary layer is an option, not a dependency** (Doug, 2026-07-10). It is
gated by **`COMMS_AI_SUMMARY`** (default **false**) plus a runtime toggle on
the admin Email Setup screen (same pattern as the Gmail toggle, §3.3) — so CBM
can run the whole pipeline (ingest, clean, store, display, send) with no LLM,
no `ANTHROPIC_API_KEY`, and no email content leaving Google/the CRM. With the
flag off: `summary`/`actionItems`/`keyTopics` stay null,
`conversationStatus` stays at its `Open` default, and the frontend simply
omits the summary block (it already renders nothing for empty fields).
Turning it on later summarizes go-forward and backfills any conversation with
`summarizedAt` null — no migration needed. The triage filter (below) runs
regardless of the flag, since it also keeps junk out of the store.

- **Triage (free, pre-LLM)** — port of CRM_Extender `triage.py`: drop
  automated senders (`no-reply@`, `billing@`…), auto-reply/OOO subjects,
  bodies containing unsubscribe markers. Triage rejects are not stored at all.
- **Summarizer** (`comms/summarize.py`): official `anthropic` SDK, structured
  outputs via `client.messages.parse(...)` with a Pydantic model —
  no fragile JSON-in-prompt parsing:

  ```python
  class ConversationSummary(BaseModel):
      status: Literal["Open", "Closed", "Uncertain"]   # bias Open
      summary: str                                     # 2–4 sentences
      action_items: list[str]
      key_topics: list[str]
  ```

  Model: **`claude-opus-4-8`** default, `SUMMARY_MODEL` env override; adaptive
  thinking (`thinking={"type": "adaptive"}`); long threads compressed to
  first-2 + last-3 messages under a char cap (their pattern). Runs in the
  worker after each conversation upsert where `summarizedAt` is null; result
  written back to the CRM fields. Failures degrade to `Uncertain` + WARNING —
  never block ingestion.
- **Cost**: at CBM volume (tens of conversations/week, ~3k in / ~300 out
  tokens per call at $5/$25 per MTok) ≈ $0.02–0.03 per summary — negligible.
  If volume ever grows, the Batches API halves it (worker is already async).
- **Privacy note for Doug/CBM to sign off**: summarization sends mentor–client
  email text to the Anthropic API (30-day retention). Triage keeps junk out;
  scope is already limited to active-record correspondence.

### 5.7 Sending (v1)

`POST` reply/compose (endpoints §6) → build MIME (text + simple HTML),
`users.messages.send` **as the signed-in manager** (subject rule §3.2). For a
reply: set `In-Reply-To`/`References` from the replied-to message's RFC ids
and pass Gmail's `threadId` so it lands on the real thread; recipient defaults
to the conversation's contact participants. The sent message lands in the
manager's real Sent folder, and the **next sync cycle ingests it** through the
normal path (it matches the contact address; Message-ID dedup makes this
exactly-once). The API response also optimistically appends it to the UI so
the manager sees it immediately.

Guardrail: recipients must be addresses already related to the record's
contacts (or explicitly typed by the user with a confirm) — the app never
invents recipients.

---

## 6. Endpoints (per-domain, `/{slug}/api`, existing auth/gates)

| Endpoint | Purpose |
|---|---|
| `GET /records/{id}/conversations` | Conversation list for the record — read from the CRM **as the user** via the parent link (newest `lastMessageAt` first; includes status/summary/count) |
| `GET /conversations/{cid}` | Full thread: ordered `CCommunication` bodies (+ summary block) |
| `POST /records/{id}/conversations/{cid}/exclude` | Curation: hide from this record (override row + unrelate) |
| `GET /mailsearch?q=` | Live Gmail search of the signed-in manager's own mailbox (readonly), for the include flow |
| `POST /records/{id}/conversations/include` | `{gmailThreadId}` → targeted ingest + relate + include row |
| `POST /contacts/{contact_id}/addresses` | Add a secondary email address to a Contact (as the user; the durable matching fix) |
| `POST /records/{id}/messages` | Send: `{to[], subject, bodyHtml, replyToCommunicationId?}` — sends as the manager, returns the optimistic message row |

All follow the existing `_crm_failure` 401/403/502 handling; Gmail failures map
to a plain-language 502 ("Couldn't reach the mailbox — try again").

## 7. Frontend (`sessions/frontend/`)

Replace the `SAMPLE_MESSAGES` scaffold in `renderComms()`:

- **Conversation list** (per record): subject, participants, message count,
  last activity, status chip (Open/Closed), one-line summary — replaces the
  flat message grid.
- **Thread view**: summary + action-items callout on top when populated
  (reuses the session card callout styles; omitted entirely when the AI layer
  is off — §5.6), then messages newest-last; `bodyCleaned` rendered
  through `sanitizeHtml`, `blockquote.quoted-reply` styled muted/indented
  (two-zone); per-message "Open in Gmail" link.
- **Curation UI**: row action "Not related…", an "Add emails…" search modal
  (mailsearch → include), and the add-address-to-contact prompt.
- **Compose/reply**: wire the existing `#commModal` to the send endpoint;
  reply pre-fills recipients/subject and threads.
- Banner ("rows are examples") is removed; the tab drops its scaffold status.

## 8. Milestones (all inside v1; verify each on crm-test before the next)

| # | Milestone | Verification |
|---|---|---|
| M1 | Google setup: scopes on the delegation grant; `core/gmail.py` token + REST client; Email Setup toggle | Script: read 1 message + send 1 test mail as a test mentor mailbox, live |
| M2 | Cleaning module ported + fixture corpus | Unit corpus green; spot-check real CBM emails |
| M3 | CRM entities built (CRM team handoff, §4) + grants | GET/POST both entities as API user + read as a gate-role user, live |
| M4 | Sync worker: enumerate → pull → match → clean → dedup → upsert → link; sync-state + overrides migrations | Seeded mailbox ↔ crm-test: conversations appear on an engagement; co-mentor CC dedups to one message; cursor expiry backfill exercised |
| M5 | LLM summaries — optional layer behind `COMMS_AI_SUMMARY` (+ `ANTHROPIC_API_KEY` on worker); triage ships in M4 regardless | Flag off: pipeline + UI fully functional, no summary block, no API calls. Flag on: summaries/status/action items appear on real threads + backfill runs |
| M6 | Endpoints + frontend (read, curation, send) | Browser: full loop — read thread, exclude, include-by-search, reply lands in Gmail thread AND back in the tab |

Rollout: everything behind `GMAIL_SYNC` (off in prod until crm-test verified
end-to-end); prod additionally needs the CRM entities + grants replicated and
the delegation scopes authorized on the prod Workspace (same domain — one
grant covers both if the same service account is used).

## 9. Open items (decide during build)

1. **Retention/deletion policy** for stored conversations (e.g. when an
   engagement closes — keep forever? CRM-side decision).
2. Exact **partner/sponsor "active" status sets** (env defaults proposed §5.1).
3. Whether CRM-side users get **team-scope read** on conversations vs the
   worker's assignedUsers stamping (§4.3) — pick one during the CRM build.
4. Google **Admin access** to authorize the new scopes (who clicks it, when).
5. Whether the summary should also surface on the **Overview tab** (next to
   the session-notes feed) — cheap follow-up once data exists.

## 10. Prior art — CRM_Extender (what we're porting vs changing)

Port nearly as-is: dual-track cleaning (`poc/email_parser.py`,
`poc/html_email_parser.py`) with its tuned edge-case guards; `historyId`
incremental sync with expired-cursor date-window backfill (`poc/sync.py`);
free triage gate (`poc/triage.py`); thread-id conversation formation with
creation gating; re-summarize-on-append. Design docs worth rereading during
the build: `PRDs/email-stripping.md` (the stripping spec + lessons),
`PRDs/communication-provider-sync-prd.md` (error-handling table),
`PRDs/conversation-formation-prd.md`.

Deliberate changes: service-account delegation instead of per-user desktop
OAuth token files; CRM entities instead of a local SQLite/Postgres store;
cross-mailbox Message-ID dedup (their unused-columns extension point);
record-level (not per-mailbox) curation overrides; structured outputs via
`messages.parse` instead of prompt-enforced JSON; Gmail kept as the raw
store (no raw bodies copied); the financial-industry regex vocabulary dropped.
