# Submission Admin — multi-admin review & respond workflow

**Status: BUILT + DEPLOYED (v0.137.0–0.138.1, 2026-07-22; crm-test + prod at
0.138.1) — live two-admin verification pass still pending.** All three phases
shipped in one pass (collaboration core + lifecycle + presence), plus two
follow-ups: **auto-close of record-creating submissions** as "Process
completed" (§7a; v0.138.0) and uniform-height detail action buttons (v0.138.1).
Authored from Doug's rulings in the design discussion this session (recorded
verbatim in §2; §7 resolved). Mockup: the artifact published this session.
Verified: full test suite green + a Postgres round-trip of the new store
methods + migration up/down + the notes→comment fold + a stub-harness browser
pass (no console errors). Live verification pending deploy (§8). Extends the
v0.106.0–v0.134.0 Submission Admin rebuild (`ops/` package,
`submission-admin.md`). CHANGELOG 0.137.0 has the built mechanics.

Companion references: `submission-admin.md` (current functional reference),
`email-management.md` (umbrella email reference),
`submission-email-flow.md` (the inbound/outbound email lifecycles),
`prds/info-mailbox-rollout-plan.md` (the shared info@ mailbox this builds on).

## 1. The problem in one paragraph

Submission Admin today is a **single-admin-at-a-time** tool. A group of
Marketing-Admin staff share one queue, but nothing helps them work it
*together*: there is no way to see who is already handling an item (so two
admins can reply to the same request), the `notes` field is one shared blob
that last-write-wins clobbers, the only record of who did what is `acted_by`
(the *last* actor, nothing before), replies go out with no visible sign of
which admin sent them, and "done" is ambiguous — a submission can be
`request_status="Closed"` without being `resolved`, or vice versa, so the
queue and the CRM disagree. The goal: let a group **review a submission,
coordinate a response, run a multi-message conversation, and close it
cleanly** — with visibility as the coordination mechanism, not formal
assignment.

## 2. Doug's rulings (design discussion, 2026-07-22)

1. **No ownership — visibility only.** Submissions stay a shared pool; no
   assignee field. Collision-avoidance comes from *seeing* who's on an item
   (presence + a "last activity — who/when" signal), not from assignment.
2. **Comments AND activity, both.** Replace the single `notes` blob with an
   attributed, timestamped **comment stream**; alongside it an automatic
   **activity feed** for system events.
3. **Direct send, attributed.** Replies still send immediately as
   *Cleveland Business Mentors <info@cbmentors.org>*, but each reply is
   stamped with **which admin sent it**, shown in the thread and the activity
   feed.
4. **Lifecycle** (worked through and approved):
   - Conversational state is **derived, not hand-set**: New → In Progress
     (once touched) → *reply owed / waiting on them* comes automatically from
     the actual emails (the existing Reply column). The manual **"Responded"**
     request-status value is dropped.
   - **One terminal action — "Close (with reason)"** — sets the done-state,
     the internal resolved flag, and writes `requestStatus="Closed"` to the
     CRM **together**, so queue and CRM never drift. Any admin can close.
   - **Auto-reopen** if the submitter replies on the thread after Close (back
     into the queue + an activity entry). A genuinely new thread stays a fresh
     queue item, as today.
5. **Close reasons** — the pick-list (each logged to the activity feed), free
   text optional on top:
   - Responded — resolved
   - Referred (intake / mentor / other team)
   - Duplicate
   - No response needed
   - Spam / not legitimate

   *(Confirm/adjust this list before build — §7 open item.)*

## 3. The lifecycle, precisely

A submission carries three orthogonal facts. Keep them distinct; the UI's job
is to make them read as one coherent state.

| Fact | Source | Values | Editable? |
|------|--------|--------|-----------|
| **Delivery status** | machine (`status`) | pending … completed / needs_attention / held_review … | no (redrive/discard/approve only) |
| **Conversational state** | **derived** | New · In Progress · Reply owed · Waiting on them · Closed | no — computed |
| **Closed** | staff (`closed_at`/`closed_by`/`close_reason`) | open / closed | Close & Reopen actions |

**Derivation of the conversational state** (one function, server-side, so the
grid and the detail agree):

- **Closed** if `closed_at` is set.
- else **Reply owed** if the newest thread message is inbound (the Reply
  column's `owed`).
- else **Waiting on them** if we sent the newest message (`waiting`).
- else **In Progress** if there's any comment, any sent reply, or a non-New
  touch.
- else **New**.

This replaces the hand-set `request_status` for display. We keep the
`request_status` *column* only as the CRM write-through carrier (it holds
"Closed" when closed; otherwise it tracks the derived state loosely for the
CRM worklist — see §5). Staff never pick it from a dropdown anymore.

**Close** (terminal, any admin):
1. `closed_at = now`, `closed_by = user`, `close_reason = <pick-list value>`,
   optional `close_note`.
2. `resolved_at`/`resolved_by` set (keeps the existing Open/Resolved grid
   filter working — Close *is* resolve).
3. `request_status = "Closed"` + best-effort CRM write-through to
   `CInformationRequest.requestStatus` (the v0.134.0 path, unchanged).
4. Activity entry: "Closed — {reason} by {admin}".

**Reopen** (any admin, or automatic): clears `closed_at`/`closed_by`/
`close_reason`, clears `resolved_at`, activity entry. Automatic reopen fires
from the inbound poller / thread read when a **new inbound message lands on an
anchored thread of a closed submission**.

## 4. Schema changes

Two new tables + a few columns on `submission`. All additive; the feature is
inert until migrated (the store pattern).

**`submission_comment`** (migration `0016`) — the internal discussion:
```
id            uuid pk
submission_id fk -> submission.id  (indexed)
author        varchar(128)   -- userName
author_name   varchar(255)   -- display name at time of writing
body          text
created_at    timestamptz
```
Comments are append-only (edit/delete out of scope for v1; a correction is a
new comment). The old `submission.notes` blob is **migrated in** as a single
seed comment (author "legacy") on upgrade, then the column is left in place
read-only for one release and dropped later.

**`submission_activity`** (migration `0017`) — the automatic feed:
```
id            uuid pk
submission_id fk -> submission.id  (indexed)
kind          varchar(32)    -- status_changed | reply_sent | comment_added
                             --   | resolved | reopened | closed | redriven
                             --   | discarded | approved | inbound_received
actor         varchar(128)   -- userName, or "system" for poller events
actor_name    varchar(255)
summary       text           -- human line, e.g. "Reply sent to jane@x.com"
created_at    timestamptz
```
Written by the router at each mutating action (the `core/action_log` pattern —
best-effort, never blocks the action). `comment_added` is derivable, but
recording it here keeps the feed a single ordered source. The comment stream
and activity feed can render **interleaved by `created_at`** (one timeline) or
side-by-side — UI decides (§6).

**`submission`** columns (migration `0018`):
```
closed_at     timestamptz
closed_by     varchar(128)
close_reason  varchar(64)
close_note    text
last_activity_at   timestamptz   -- bumped on every comment/activity write
last_activity_by   varchar(128)  -- the grid's "who touched it last" signal
```
`last_activity_at/by` feed the grid column and the collision signal without a
join. (`acted_by` stays as-is for redrive/discard audit.)

## 5. API changes (`ops/router.py`)

- `GET /submissions` — each row gains `conversationState` (derived),
  `last_activity_at`, `last_activity_by`, `comment_count`. The Reply-state
  fetch already runs; fold its result into `conversationState` server-side so
  the grid shows one state column instead of separate Status/Request/Reply.
- `GET /submissions/{id}` — add `comments: [...]` and `activity: [...]`
  (newest-or-oldest-first TBD), plus the close fields.
- `POST /submissions/{id}/comments` `{body}` → append a comment (author from
  session), write a `comment_added` activity, bump `last_activity`.
- `POST /submissions/{id}/close` `{reason, note?}` → the Close transaction
  (§3), including the CRM write-through and activity entry.
- `POST /submissions/{id}/reopen` → reopen + activity.
- **Retire** `PUT /submissions/{id}/requeststatus` (the manual dropdown) and
  `PUT /submissions/{id}/notes` (single blob). `requestStatus` CRM
  write-through moves inside Close; notes become comments.
- `POST /submissions/{id}/presence` (or fold into the detail GET) — record
  "user X viewed at T"; the detail returns other admins' recent presence
  ("Bob viewed 30s ago"). Lightweight: a short-TTL in-memory or a
  `submission_presence` row keyed by (submission, user); no websockets.
- Every existing action (redrive/discard/approve/resolve, and each **reply
  sent** via the quicksend `after_send` hook) also writes an activity row.
  The reply-sent activity is where **"which admin sent it"** is captured
  (the send hook has the acting user; the thread shows the shared identity,
  the activity + comment timeline shows the person).

## 6. UI changes (`ops/frontend/`)

**Grid**
- Collapse Status / Request / Reply into a single **State** column showing the
  derived `conversationState` (with the delivery-status badge kept only when
  it's *not* completed — the exception cases). Sort/filter by State.
- New **"Last activity"** column (who + relative time) — the at-a-glance
  "someone's on this / this is stale" signal. Sortable.
- Close reason shown on resolved/closed rows.

**Detail — Overview**
- Replace the notes card with a **Discussion** panel: the comment stream
  (attributed, timestamped) with an always-visible "Add a comment" box, plus
  the **activity feed** interleaved (system events in a muted style, comments
  prominent). This is the coordination surface.
- **Presence line** at the top: "You're viewing this. Bob viewed 1 min ago."
  — the anti-double-reply cue. Refreshed on open + a periodic poll.
- Header actions: **Close (with reason)** replaces the request-status dropdown
  + Mark-resolved pair (Reopen when closed). Redrive/Discard/Approve unchanged.
- The conversation-with-submitter block stays; each sent message now shows the
  sending admin (from the activity/send record) as a small "sent by Jane" tag.

**Detail — Communications** — unchanged except the per-message "sent by {admin}"
attribution.

## 7. Open items — RESOLVED (Doug, 2026-07-22)

1. **Close-reason list** (§2.5) — ✅ **approved** as the five values.
2. **Timeline layout** — ✅ **two side-by-side panels** (Discussion | Activity),
   NOT interleaved.
3. **Presence depth** — ✅ **"last viewed by / when" is adequate** for v1 (no
   live "composing now" indicator).
4. **`notes` migration** — ✅ **OK to fold** the existing blob into a seed
   comment on the live rows.
5. **Auto-reopen scope** — ✅ **reply on the linked (anchored) thread only**;
   new unrelated threads stay separate items.

## 7a. Follow-up ruling — auto-close record-creating submissions (v0.138.0)

Doug, 2026-07-22: a **client-intake / volunteer / partner / sponsor** submission
that delivers its CRM records needs no Submission-Admin action — the downstream
admin team owns it. On successful delivery those **auto-close** with the system
reason **"Process completed"** (atomically inside `mark_completed`, both the
worker and sync paths; `core/store.ADMIN_REVIEW_FORMS` = the forms that stay
open = info-request / info-email; `autoclose_reason`). "Process completed" is
NOT a manual Close option; the grid State cell now shows a closed row's reason.
Migration 0019 back-closes the already-delivered rows. So the open queue is only
the requests that need a human reply.

## 8. Phasing

- **Phase 1 — collaboration core:** comment table + activity table + the two
  new API surfaces + the Overview Discussion panel + reply-sent attribution.
  (Delivers the "coordinate a response" half; no lifecycle change yet.)
- **Phase 2 — lifecycle:** derived conversationState, the single Close-with-
  reason action, retire the manual request-status dropdown, grid State +
  Last-activity columns, auto-reopen.
- **Phase 3 — presence:** the last-viewed collision signal (can ship with
  Phase 1 if cheap).

No CRM build required — the CRM write-through rides the existing v0.134.0
`CInformationRequest.requestStatus` path. All new state lives in Postgres.
Migrations `0016`/`0017`/`0018` run via the existing pre-deploy migrate job.
