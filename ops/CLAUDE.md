# ops/ — Submission Admin

Last Updated: 10-30-26 01:09 · Revision 1.0

Detail for Submission Admin (`/ops`): the two status axes, coordination, held rows, close and discard, thread-anchored email, the info@ capture.

Claude Code loads this file only when a session reads or edits files in this
folder. The rules other packages depend on stay in the root `CLAUDE.md`, which
also points here. Moved word for word from the root file on 10-30-26, when
it passed its 80,000-character limit; edit it here from now on.

## Submission Admin — `/ops`

Marketing Admin Team. A multi-admin review-and-respond workspace over the
durable store. Staff reference: `submission-admin.md`.

- **Two status axes, deliberately separate**: **Intake status** (what happened
  to this arrival — Received / Completed / Held-Spam / Held-Email / Error /
  Discarded, the CRM receipt vocabulary) and **Response status** (where the
  reply conversation stands — New → In progress → Reply owed / Waiting on them →
  Responded → Closed). Machine words like `pending`/`needs_attention` never
  render. Count chips are one-click filters; filtering is client-side.
- **No owner — coordination by visibility**: an attributed comment stream, an
  automatic activity feed, and presence ("viewed 4 min ago").
- **A Held-Company row has its own control, not Approve** (v0.238.0): the
  company the submission names exists at a different web address, so
  *Company ▾* offers *Same company* / *Different company* (name required,
  must differ from the one on file); both write `delivery_overrides` and
  re-queue. A bare re-drive is not offered — it would hit the same conflict.
- **Close requires a reason**; discard requires one too (422 without) and stamps
  who/when/why on the CRM receipt. A submitter replying on an anchored thread
  after close **auto-reopens** it.
- **Record-creating submissions auto-close** on successful delivery ("Process
  completed") — they are owned by the downstream admin team from that point, so
  the open queue is only info-request and info-email items needing a reply.
- **Email is thread-anchored**, not an address search: every send records its
  Gmail thread on the submission, and the conversation view reads only anchored
  threads. Sends go as **`OPS_MAILBOX`** (info@, display name "CBM Info") so
  every admin sees the same conversation.
- **Inbound info@ capture**: the worker polls the shared inbox and captures each
  new thread as a **held `info-email` submission** for triage. Approve = redrive
  (creates CRM records via the info-request orchestrator); Discard = spam with
  zero CRM residue. Layered stateless dedup means replies to anchored threads
  never double-capture. **Only ONE poller may run** — setting `OPS_MAILBOX` on
  both environments double-captures.
- **Other correspondence** surfaces inbound info@ threads not tied to a
  submission (replies to notices staff sent), read and replied to in-app,
  nothing stored.
- `?submission=<id>` deep-links a row even when filtered out; alert emails use
  it via `APP_BASE_URL`.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-30-26 01:09 | Claude (Claude Code) | Created from the root `CLAUDE.md` section, word for word (Doug's approval 10-30-26). |
