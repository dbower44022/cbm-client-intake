# Submission Admin (`/ops`) — functional reference

*For CBM staff on the Marketing Admin Team (CRM admins always have access).
Sign in once at the portal (`/`); the Submission Admin tile appears if you're
entitled. Rebuilt 2026-07-19 (v0.106.0–v0.108.0).*

## What it is

Every submission from the public forms (client intake, volunteer,
info-request, partner, sponsor) is captured durably before anything else
happens, then delivered into the CRM by a background worker. Submission Admin
is where staff watch that pipeline, fix anything stuck, and — for
information requests — **carry the conversation with the submitter through to
resolution** without leaving the page.

## The front page (the work queue)

- The grid fills the window and scrolls under a sticky header. Every column
  **sorts** (click the header; click again to reverse) and **resizes** (drag
  the right edge of a header). Rows alternate colors; clicking anywhere on a
  row opens it.
- The **search box at the top center** filters live across reference, form,
  status, submitter, error text, notes, and dates.
- The **Open / Resolved / All** select defaults to **Open** — the grid shows
  the requests still waiting on someone. Resolved rows carry a green
  ✓ chip; the count chips include `open` / `resolved` totals.
- The **Reply** column answers "who spoke last?" for each open submitter:
  - **↳ reply owed** (red) — their email is the newest; we owe them a reply.
  - **waiting on them** — our email is the newest.
  - **—** — no email conversation yet.
  It fills in a moment after the grid loads (it checks your mailbox), and
  sorting by it surfaces everything that needs a response.
- **Re-drive** re-queues a stuck submission (needs-attention / retry / held /
  discarded) for the worker to run again — safe, it resumes from what was
  already created. **Discard** parks an undeliverable one (undo by
  re-driving). Both ask for a confirming second click.

## The submission page

Three tabs, like the Client Management record pages.

### Overview
- **Left**: who submitted and where it stands — name, email (click to
  compose), phone, company, their message, the form, delivery status,
  received/processed times, attempts, and the resolved stamp.
- **Top center**: **Submission notes** — free-form triage notes for other
  admins ("left a voicemail", "duplicate of…"). Click Edit, type, Save.
  Notes are staff-only; they never go to the CRM or the submitter.
- **Below the notes**: the **conversation with the submitter** — the latest
  emails between your CBM mailbox and their address, newest first. Click a
  message to jump to the Communications tab.
- **Header buttons**: **Mark resolved / Reopen** (the workflow flag — use it
  when the request is done, whatever "done" meant), plus Re-drive/Discard
  when applicable.

### Details
The raw record: the exact payload the form sent, delivery progress, the last
error, and — once delivered — **links straight into EspoCRM** for each record
the submission created (Contact, Account, information request, …).

### Communications
The full email history with the submitter, with readable cleaned bodies
(click a message to expand; quoted reply chains are tucked into a gray
block). **Email the submitter** opens the standard compose:

- **New conversation on an info-request** → the **InfoRequestReply** template
  is pre-applied (subject + body, personalized to the recipient). Edit and
  send. (Template name configurable via `OPS_REPLY_TEMPLATE`.)
- **Existing conversation** → the button reads **↩ Reply to the submitter**
  and the compose opens as a reply: "Re:" subject, and the send stays on the
  same email thread in both inboxes.

Messages send from **your own @cbmentors.org mailbox** (your name on the
From line, your signature appended), exactly like the composes in the other
staff tools.

## Why don't I see…

- **…the conversation / the Reply column?** Email features need the Gmail
  integration on for the deployment AND your login linked to a CBM profile
  with a `cbmEmail`. Without them the page says exactly which is missing —
  everything else still works.
- **…an email another admin exchanged with this submitter?** The
  conversation is read live from **your** mailbox. If a colleague ran the
  exchange, it's in theirs. Check the submission notes — that's what they're
  for — or ask them to Mark resolved when done.
- **…the template in the compose?** The template must exist in EspoCRM with
  the exact name `InfoRequestReply` (or the name set in `OPS_REPLY_TEMPLATE`).
  A missing template just opens a blank compose — the template picker inside
  the dialog still lists everything you can use.

## The intended flow for an information request

1. Open Submission Admin — the grid shows **open** items; sort by **Reply**
   to see who's waiting on you.
2. Click the request. Read the message and facts on the left; check the
   notes for anything a colleague already did.
3. **Email the submitter** — the canned reply is pre-filled on first
   contact; later rounds are proper replies on the same thread.
4. Jot what happened in **Submission notes**.
5. When it's handled, **Mark resolved** — it leaves the queue (still
   findable under Resolved/All).
