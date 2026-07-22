# Submission Admin (`/ops`) — functional reference

*For CBM staff on the Marketing Admin Team (CRM admins always have access).
Sign in once at the portal (`/`); the Submission Admin tile appears if you're
entitled. Rebuilt 2026-07-19 (v0.106.0–v0.108.0); the shared info@ mailbox
model added in v0.110.0.*

> **The bigger picture:** submission email is one part of CBM's email
> system — [`email-management.md`](email-management.md) is the umbrella
> reference (the sending identities, My Email, the compose dialog,
> templates/signatures, and how submissions fit in), and
> [`submission-email-flow.md`](submission-email-flow.md) is the end-to-end
> design summary: the inbound and outbound email lifecycles plus the Google
> Workspace changes that activate the shared info@ mailbox.

## What it is

Every submission from the public forms (client intake, volunteer,
info-request, partner, sponsor) is captured durably before anything else
happens, then delivered into the CRM by a background worker. **Emails sent to
info@cbmentors.org enter the same queue**: the worker watches that mailbox and
each new inbound conversation appears as an "info-email" submission awaiting
your triage. Submission Admin is where staff watch that pipeline, fix anything
stuck, and **carry the conversation with the submitter through to resolution**
without leaving the page.

All submission email — reading and sending — goes through the **shared
info@cbmentors.org mailbox** under the generic name **Cleveland Business Mentors**: every admin
sees the same conversation, replies come from the same address the public
already knows, and a submission's conversation shows **only the email threads
that belong to it** (the thread the submitter started, plus any thread you
started from the submission page — never their unrelated mail).

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
- **Inbound emails** (form "info-email", status "held review") carry
  **Approve** instead of Re-drive: approving creates the CRM records —
  Contact, plus the Information Request — exactly as if the person had used
  the website form (marked as source "Email"). **Discard** is the spam
  button: the email leaves the queue and nothing is ever written to the CRM.

## The submission page

Three tabs, like the Client Management record pages.

### Overview
- **Left**: who submitted and where it stands — name, email (click to
  compose), phone, company, their message, the form, delivery status,
  received/processed times, attempts, and the resolved stamp.
- **Top center**: **Submission notes** — free-form triage notes for other
  admins ("left a voicemail", "duplicate of…"). Click Edit, type, Save.
  Notes are staff-only; they never go to the CRM or the submitter.
- **Below the notes**: the **conversation with the submitter** — the emails
  on this submission's own threads in the shared info@ mailbox, newest
  first; every admin sees the same list. Click a message to jump to the
  Communications tab.
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

Messages send from **the shared info@cbmentors.org mailbox as "Cleveland Business Mentors"** —
deliberately not your personal name or address (no personal signature is
added either). Who actually clicked Send is still recorded internally. Every
send ties its email thread to the submission, which is exactly what the
conversation view (and the Reply column) reads.

## Why don't I see…

- **…the conversation / the Reply column?** Email features need the Gmail
  integration on for the deployment (and the shared mailbox configured).
  Without them the page says exactly which is missing — everything else
  still works.
- **…an email the submitter sent that isn't in the conversation?** The
  conversation shows only the threads that belong to THIS submission. Mail
  they sent info@ about something else becomes its own queue item; mail they
  exchanged with a staffer's personal mailbox never involves info@ at all.
- **…the template in the compose?** The template must exist in EspoCRM with
  the exact name `InfoRequestReply` (or the name set in `OPS_REPLY_TEMPLATE`).
  A missing template just opens a blank compose — the template picker inside
  the dialog still lists everything you can use.

## The intended flow for an information request

1. Open Submission Admin — the grid shows **open** items; sort by **Reply**
   to see who's waiting on you.
2. Click the request. Read the message and facts on the left; check the
   notes for anything a colleague already did.
3. **If it arrived by email** (form "info-email"): first decide — **Approve**
   (a real request; the CRM records are created) or **Discard** (spam; gone,
   no CRM residue). Form submissions skip this step — they delivered on
   arrival.
4. **Email the submitter** — the canned reply is pre-filled on first
   contact; later rounds are proper replies on the same thread. Everything
   sends as **Cleveland Business Mentors <info@cbmentors.org>**.
5. Jot what happened in **Submission notes**.
6. When it's handled, **Mark resolved** — it leaves the queue (still
   findable under Resolved/All).

## How email-originated submissions work (v0.110.0)

- The worker checks the info@ inbox every few minutes. A **new** conversation
  (a thread not already tied to any submission) becomes a queue item holding
  the sender's name/address, the subject, and the readable message text.
- A **reply** to an existing conversation never becomes a new item — it
  simply appears in that submission's conversation view.
- Mail the mailbox itself started (someone writing from the Gmail UI) and
  delivery bounces are ignored.
- The same person emailing again later — a genuinely new thread — is a new
  queue item, which is correct: a resolved request stays resolved, and new
  contact means someone is waiting again. If they ALSO filled the form, the
  two items show up separately; handle one and discard/resolve the other
  (the notes field is the place to say so).
