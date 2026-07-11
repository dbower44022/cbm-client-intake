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
| Google service account with domain-wide delegation | The mailbox check/creation feature (v0.11.0) | Its JSON key is in the Email Setup screen (`/mentoradmin` → Email Setup) or the `GOOGLE_SERVICE_ACCOUNT_JSON` env var in the gitignored overlay |
| Managed Postgres + `delivery-worker` + pre-deploy migrate | V2 activation | `/healthz` shows `durableStore: true` |
| App at **v0.35.0 or later** | The Communications build | `/healthz` version |
| Managers have a CBM mailbox + login | Mentor provisioning | Each syncing manager's `CMentorProfile` has `cbmEmail` set AND an assigned login User — **both are required**; profiles missing either are silently skipped |

---

## Part 1 — Google: authorize the Gmail scopes

The service account already has Directory scopes authorized. You are ADDING
two Gmail scopes to the SAME grant — no new service account, no new key.

1. **Find the service account's Client ID.** Open the service-account JSON
   key (the one pasted into Email Setup / the overlay) and copy the value of
   `"client_id"` — a ~21-digit number. (Alternatively: GCP Console → IAM &
   Admin → Service Accounts → the account → "Unique ID".)
2. Sign in to **admin.google.com** as a Workspace super-admin.
3. Go to **Security → Access and data control → API controls →
   Manage Domain Wide Delegation**.
4. Find the row with that Client ID (it exists — it carries the Directory
   scopes) and click **Edit**.
5. In the OAuth scopes box, keep the existing scopes and ADD these two,
   comma-separated:

   ```
   https://www.googleapis.com/auth/gmail.readonly,
   https://www.googleapis.com/auth/gmail.send
   ```

6. **Authorize** / Save. Propagation is usually minutes; allow up to an hour.
7. Also confirm the **Gmail API is enabled** on the service account's GCP
   project: GCP Console → APIs & Services → Library → "Gmail API" → Enable
   (the Admin SDK is already enabled for the Directory checks).

> Security note (for the record): domain-wide delegation is domain-wide — the
> app code restricts impersonation to (a) enumerated managers' mailboxes for
> sync and (b) the signed-in user's own mailbox for search/send, and logs every
> access. The scopes stay read+send only (no modify/delete). This was accepted
> in the design; see the plan §3.4.

## Part 2 — CRM: build the entities (crm-test first)

Full field-by-field spec: **`cconversation-entity.md`**. Condensed steps
(EspoCRM Administration, as admin):

1. **Entity Manager → Create Entity** `CConversation` (type Base). Add fields:
   `conversationStatus` (enum: Open/Closed/Uncertain, default Open),
   `summary` (text), `actionItems` (text), `keyTopics` (varchar 255),
   `participants` (varchar 500), `firstMessageAt` (datetime),
   `lastMessageAt` (datetime), `messageCount` (int),
   `summarizedAt` (datetime, **no default, nullable**).
2. **Entity Manager → Create Entity** `CCommunication` (type Base). Add:
   `direction` (enum: Inbound/Outbound), `sentAt` (datetime),
   `fromAddress` (**varchar 255 — NOT the email field type**; an email-type
   field silently stores nothing), `fromName` (varchar 255),
   `toAddresses` (varchar 500), `ccAddresses` (varchar 500),
   `snippet` (varchar 255), `bodyCleaned` (wysiwyg),
   `rfcMessageId` (varchar 255), `gmailThreadId` (varchar 64),
   `gmailMessageId` (varchar 64), `sourceMailbox` (varchar 255).
3. **Relationships** (Entity Manager → CConversation → Relationships):
   - many-to-many to **CEngagement** — link `engagements`, foreign link
     **`conversations`** (the foreign name must be exactly `conversations`);
   - many-to-many to **CPartnerProfile** — link `partnerProfiles`, foreign
     link `conversations`;
   - many-to-many to **CSponsorProfile** — link `sponsorProfiles`, foreign
     link `conversations`;
   - many-to-many to **Contact** — link `contacts`, foreign `conversations`;
   - one-to-many to **CCommunication** — link `communications`, foreign
     link `conversation`.
4. **Enable collaborators**: Entity Manager → CConversation → Edit → turn ON
   **Assigned Users** (the multi-user collaborators field). Required — the
   sync stamps owners there so read-own roles see their conversations.
5. **Grants** (Administration → Roles):
   - `CustomAppAPIRole` (the intake API user): create + read + edit on BOTH
     entities.
   - The three session gate roles (Mentor Team / Partner Management Team /
     Sponsor Management Team roles): read on both — `CCommunication` read
     must be **team or all** (messages aren't owner-stamped; "own" hides
     them). Simplest: read=all on both (see the spec §3 for the tighter
     alternative).
6. **Layouts**: add a "Conversations" relationship panel to the detail
   layouts of CEngagement, CPartnerProfile, CSponsorProfile (columns: name,
   conversationStatus, messageCount, lastMessageAt).
7. **Administration → Rebuild.**

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

## Prod rollout (after crm-test passes)

1. Part 2 on the prod CRM (same entities/grants/layouts).
2. Part 1 covers prod already if prod uses the same Workspace domain + service
   account (it does — `@cbmentors.org`); otherwise repeat it for the prod key.
3. Part 3 in `.do/app.prod-crm.yaml`, apply to the prod app.
4. Part 4 against a real manager, then announce to staff.
