# Email Quality Improvement Plan — closing the gaps between the app and Gmail

**Status: Phase 1 BUILT (v0.132.0, 2026-07-22) — §3 complete in code
(attachment auto-filing + ledger/chips, View original + cid endpoint, the
viewer-mailbox Open-in-Gmail fix, bounce cards/chips on record threads +
My Email), harness/test-verified, NOT yet driven live (§3.5 verification
open; the outbound-body repair script run per env still pending). Phases
2–3 not started.** Originally authored 2026-07-21 from Doug's
priority rulings this session (recorded in §2) after a full review of the
email system (docs + code sweep of `core/gmail.py`, `core/email_clean.py`,
`comms/`, `myemail/`, `ops/inbound.py`, and the compose frontend).
Companion references: `email-management.md` (umbrella),
`communications-tab.md`, `submission-email-flow.md`,
`prds/communications-gmail-integration.md` (the original design).

## 1. The problem in one paragraph

The email system is a poll-based, CRM-centric Gmail mirror: it stores only
cleaned "new text" and deep-links to Gmail for everything else. That design
loses information in ways that erode user trust — inbound **attachments are
invisible** in-app, **original formatting and inline images are gone**, the
cleaner can **over-strip** a message to nothing, and the "Open in Gmail"
escape hatch is **broken** (wrong mailbox, mailbox-specific ids). Separately,
mentors have **no signal on their grids** that a record has mail waiting, and
several known reliability loose ends (bounces invisible in record threads,
truncated stored outbound bodies, the info@ 100-thread window) remain open.

## 2. Doug's rulings (2026-07-21)

| Area | Ruling |
|---|---|
| A. Reading fidelity (attachments, formatting, inline images, over-strip) | **CRITICAL** — "users will not trust us if we lose information" |
| Attachments | Auto-file into the record's **Documents tab**; **hash the file** (or equivalent) so multiple copies are never created |
| Attachment filter | **Real attachments only** (content-disposition: attachment); inline/signature images never become documents (stay viewable via View original) |
| Domains | Attachment auto-file covers **all three domains** (engagement / partner / funder) |
| View original for non-recipients | Fetch from the **source mailbox under the service identity** — any viewer entitled to the record sees the full original |
| B. Timeliness (push vs 5-min poll) | **Low priority — deferred** |
| C. Two-way state sync (read-state → Gmail, labels, archive) | **Low priority — deferred** |
| D. Forward with attachments | **Important** — mentors frequently forward key documents to another mentor or SME (not assigned to the engagement) for quick analysis |
| E. Full-text search over stored mail | Nice to have — **deferred** |
| F. Known loose ends (bounces, repair script, info@ window, staff-notice replies) | **Clear up** |
| Unread awareness | Build **all four** surfaces: grid unread chips, portal tile badge, awaiting-reply grid chip, daily email digest |
| Open in Gmail | Was a good idea; currently **broken** — fix it |

Key architectural fact underpinning Phase 1: **no new Google scopes are
needed.** `gmail.readonly` already permits fetching attachment bytes and
full originals on demand from any delegated mailbox; every Phase 1 item is
a storage/UX build, not a permissions change. **No CRM entity changes are
needed either** — new state lives in the app's Postgres store; the
`CCommunication` schema is untouched.

## 3. Phase 1 — Never lose information (A + critical F)

### 3.1 Inbound attachments auto-file to Documents

- `core/gmail.py`: `parse_message`/`_walk_parts` additionally collect
  attachment parts — filename, mimeType, size, `attachmentId`,
  content-disposition (today only the first text/plain + text/html parts
  are read and attachments are discarded). New
  `GmailClient.get_attachment(message_id, attachment_id)` wraps
  `users.messages.attachments.get`.
- **Filter (ruling):** only parts with `Content-Disposition: attachment`
  qualify. Inline parts (`inline`, `cid:`-referenced images, signature
  logos) are never filed — they remain visible through View original
  (§3.2).
- Sync ingest (`comms/sync.py`): for each newly stored message with
  qualifying attachments, fetch the bytes, compute **SHA-256**, and file
  through the existing documents pipeline (`docs/service.py`) into the
  record's Drive folder under the **service identity** — docType
  **"Email attachment"**, `uploaded_by` = the mailbox owner. All records
  the conversation links to receive the filing (per-record dedup applies).
- **Dedup (ruling):** per record, by content hash. `app_document` gains a
  `content_sha256` column (Alembic migration); before filing, look up the
  hash among the record's documents — a five-reply thread re-attaching the
  same PDF stores it **once**. (Per-record rather than global: Drive
  grants and folder placement are per-record; the same file legitimately
  appears on two records as two entries.)
- New app table `comm_attachment` (Alembic migration):
  `(rfc_message_id, part_index, filename, mime_type, size, sha256,
  status filed|duplicate|too_large|failed, document_id nullable)` — the
  render source for chips, and the retry ledger.
- **Thread view chips:** each message renders its attachments as chips —
  filed ones link to the document (existing view/download proxy);
  `too_large` (over `GDRIVE_MAX_FILE_MB`) and `failed` chips say so and
  point at View original / Gmail.
- **Best-effort contract** (comms conventions): a Drive/DB failure never
  fails message ingest — the row is marked `failed` and re-attempted on
  subsequent passes until filed (idempotent by `(rfc_message_id,
  part_index)`); persistent failures WARN.
- Gates: requires both `GMAIL_SYNC` and `GDRIVE_DOCS` (+ `DATABASE_URL`).
  Worker already carries the `GDRIVE_*` envs (nightly reconciliation).
- **Backfill:** applies to newly ingested messages go-forward. A one-shot
  `scripts/backfill_email_attachments.py` (dry-run default) can sweep
  stored conversations' Gmail originals for historical attachments —
  run per env after the feature is verified.

### 3.2 "View original" in-app

- New endpoint per domain: `GET /{slug}/api/communications/{id}/original`
  — parent-record ACL check **as the signed-in user** (the same gate as
  the thread read), then fetch the complete original from the
  **source mailbox** via the service-account delegation (ruling: any
  viewer entitled to the record sees it; consistent with the conversation
  already being shared on the record). Log every such access (mailbox,
  message, acting user) per the §3.4 trust note in the original design.
- Renders in the standard overlay viewer: sanitized original HTML,
  formatting intact; **inline `cid:` images resolved** through a
  companion subresource endpoint (same ACL + provenance checks).
- This is the systemic answer to over-stripping (A4): the cleaned text
  stays the readable transcript; the untouched original is one click away
  in-app for every viewer — "(no new text…)" messages become recoverable
  without leaving the product.
- Failure modes are readable: message deleted in Gmail
  (`MessageGoneError`) → "the original no longer exists in the source
  mailbox"; transient Gmail errors → plain-language 502.

### 3.3 Fix "Open in Gmail"

- Root cause (diagnosed 2026-07-21): the link is
  `mail.google.com/mail/u/<sourceMailbox>/#all/<gmailMessageId>`
  (`sessions/frontend/app.js:1845`). `sourceMailbox` is the mailbox the
  sync read from — usually not the viewer, so Google refuses; and Gmail
  message ids are **mailbox-specific**, so the id is only valid there
  anyway.
- Fix: link to the **viewer's own mailbox** by RFC id —
  `https://mail.google.com/mail/u/<viewer cbmEmail>/#search/rfc822msgid:<rfcMessageId>`
  — the RFC `Message-ID` is identical in every mailbox and already
  stored. The viewer's cbmEmail comes from the session (`/mailbox` /
  session payload), never from request input.
- If the viewer has no cbmEmail, or wasn't a participant (the message
  isn't in their mailbox), the Gmail link can't work — the UI keeps the
  link (it degrades to an empty search) but View original (§3.2) is the
  guaranteed path; the button copy points there on failure.

### 3.4 Bounce visibility in record threads (closes F14)

- The `looks_like_bounce` helper (v0.130.0) is used by /ops only; the
  record-level sync ingests bounces as ordinary replies — a mentor's
  failed send reads as a client response.
- Classify at **render/enrichment time** from stored fields (from-address
  mailer-daemon/postmaster + DSN subject — both stored; no CRM schema
  change, self-heals on deploy like the v0.125.0 outbound fix): thread
  view renders a red **"Delivery failed"** card (the /ops treatment);
  `enrich_conversation_rows` reports a bounce-terminated thread as
  **"✕ delivery failed"** instead of unread/awaiting-reply; My Email rows
  show the same chip.

### 3.5 Operational items riding this phase

- Run `scripts/repair_outbound_bodies.py` per env (dry-run → `--write`,
  worker console) — heals stored truncated sent bodies (v0.125.0's
  pending step).
- Verification (crm-test, live): send a real email with a PDF + a
  signature-logo'd body to a mentor → attachment files once into the
  engagement's Documents (logo does NOT), chip links to it; reply
  re-attaching the same PDF → `duplicate`, no second document; View
  original shows real formatting + inline images for mentor AND
  co-mentor; Open in Gmail opens the thread in the viewer's own mailbox;
  a bounced send shows the red card + chip.

## 4. Phase 2 — Forward with attachments + unread awareness

### 4.1 Server-side forward (D)

- Forward today is a client-side quoted text block — attachments are
  dropped. New: the forward compose carries the source
  `communicationId`; on send, the server fetches the original's
  qualifying attachments from the source mailbox (service identity, same
  provenance logging as §3.2) and includes them on the outgoing MIME.
- UI: forwarded attachments appear as pre-selected removable chips
  (template-attachment pattern); the existing 20 MB cap applies; a chip
  that can't be fetched at send time **blocks the send** (ET-131 rule —
  never send an email that silently lost its attachment).
- The SME use case works frictionlessly: `@cbmentors.org` recipients
  already bypass the unknown-recipient confirm; outside addresses keep
  it. "Attach from documents" remains available in the same compose for
  filed documents.
- Minor hardening in the same code area: populate the **`References`**
  header chain on replies/forwards (today always empty — threading rides
  In-Reply-To + threadId only, weaker for non-Gmail recipients).

### 4.2 Unread awareness (all four surfaces — ruling)

1. **Grid unread chips:** the record grids (Client / Partner / Funder
   Management) gain a per-row blue **"● N unread"** chip — one batched
   `enrich_conversation_rows`-style query per page (the machinery exists;
   this is surfacing), sortable/filterable. Decoration contract: failures
   render nothing, never break the grid.
2. **Portal tile badge:** the My Email tile shows the signed-in user's
   total unread count (one aggregate query on portal load; absent when
   the store/Gmail integration is off).
3. **Awaiting-reply chip on grids:** the amber "awaiting reply" state per
   row alongside the unread chip (same batched read).
4. **Daily email digest:** a worker daily job (monitoring-timer pattern,
   `COMMS_DIGEST_SECONDS` default 86400, flag `COMMS_DIGEST`) sends each
   manager a morning summary of their records with unread / awaiting
   conversations, each a deep link to the record page. Sent from the
   shared identity (`OPS_MAILBOX`, "Cleveland Business Mentors") to the
   manager's cbmEmail; **no empty digests** (nothing pending = no email).
   Open sub-decisions at build time: send hour anchoring, and whether
   digest is opt-out per user (recommend: on for all managers, revisit
   on feedback).

## 5. Phase 3 — remaining F loose ends

- **info@ poller window:** paginate past the newest-100 inbox threads
  (time-bounded by the last successful pass) so a burst can't scroll a
  new request past the window (`ops/inbound.py` known limitation).
- **Staff-notice replies (F15):** replies to Phase-2 quick-compose
  notices land only in the info@ Gmail inbox — no in-app surface.
  Options to decide at kickoff: (a) an "Other correspondence" list in
  /ops for inbound info@ threads not tied to a submission (read + reply);
  (b) accept the Gmail-watch model and document it as deliberate.
  Recommend (a) — it removes the last reason Marketing Admin must watch
  raw Gmail.

## 6. Deferred (recorded so we never re-litigate from scratch)

| Item | Why deferred | What it would take |
|---|---|---|
| B. Real-time push | 5-min latency accepted for now | `users.watch` + Pub/Sub infra (new GCP surface), or shorter poll (quota cost across mailboxes) |
| C. Read-state sync to Gmail; labels; archive | Low priority | **`gmail.modify` scope** on the DWD grant — widens the trust surface recorded in the design's §3.4; revisit deliberately |
| Server-side / Gmail drafts | Low priority (localStorage autosave exists) | `gmail.compose` or `gmail.modify` scope |
| Scheduled send / undo send | Not requested | App-side queue (delay-then-send) — no Gmail API support for undo |
| E. Full-text search over stored mail | Nice to have | Local Postgres FTS mirror of `bodyCleaned` (the CRM can't full-text search), or per-mailbox live search only (status quo) |

## 7. Prerequisites / impact summary

- **Google:** none. No new scopes, no new APIs (Drive + Gmail already
  enabled and delegated).
- **CRM:** none. No entity/field changes; all new state is app-side.
- **DB:** two Alembic migrations (`content_sha256` on `app_document`;
  new `comm_attachment`) — ride the standard pre-deploy migrate job.
- **Config:** no new required vars for Phase 1 (existing `GMAIL_SYNC` +
  `GDRIVE_DOCS` gate it); Phase 2 digest adds `COMMS_DIGEST` (+ interval).
- **Ops:** the two one-shot scripts (outbound-body repair; attachment
  backfill) run per env from the worker console, dry-run first.
