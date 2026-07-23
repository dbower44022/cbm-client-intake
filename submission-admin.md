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
  the requests still waiting on someone. The count chips include `open` /
  `resolved` totals.
- The **State** column is one at-a-glance answer to "where does this stand?",
  worked out for you from the emails and what staff have done:
  - **↳ Reply owed** (red) — the submitter's email is newest; we owe them a reply.
  - **Waiting on them** — our email is newest.
  - **In progress** — someone has commented / replied, no reply currently owed.
  - **New** — nobody has touched it yet.
  - **Closed** (green) — it's been closed with a reason.
  - **Delivery failed** — a reply bounced.

  If the machine had trouble *delivering* the submission to the CRM (rare),
  that shows as a small sub-badge next to the state (e.g. `needs attention`,
  or `held review` on an inbound email awaiting Approve). Sorting by State
  surfaces the reply-owed items first.
- The **Last activity** column shows **who did the last thing and when** —
  the signal that a colleague is already on an item (there's no formal
  "owner"; visibility is how the team avoids two people answering the same
  request). Sort by it to find what's gone quiet.
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
- **A presence line at the top** tells you who else is looking right now
  ("Marcus viewed 4 min ago") — check it before you reply, so two people
  don't answer the same request. It refreshes on its own every few seconds.
- **Left**: who submitted and where it stands — name, email (click to
  compose), phone, company, their message, the form, delivery status,
  received/processed times, attempts, and the resolved stamp — followed by
  **everything else the submitter entered on the form**, each field with a
  readable label (a file upload shows its name and size).
- **Center: Discussion and Activity, side by side.**
  - **Discussion** is the internal, staff-only conversation among admins —
    attributed, timestamped comments ("left a voicemail", "duplicate of…").
    Type in the box and click **Comment**. Every admin sees the same thread;
    nothing here goes to the CRM or the submitter.
  - **Activity** is the automatic log: what happened and who did it —
    submitted, delivered, a reply sent (**and which admin sent it**, even
    though it goes out as the shared identity), comments, resolved, closed,
    re-driven, and so on.
- **Below**: the **conversation with the submitter** — the emails on this
  submission's own threads in the shared info@ mailbox, newest first. Click a
  message to jump to the Communications tab.
- **Header controls**: **Close ▾** — the single "this is done" action. Pick a
  **reason** (Responded — resolved / Referred / Duplicate / No response
  needed / Spam) and optionally add a note; closing marks the request resolved
  *and*, on an information request, sets the matching CRM record's Request
  Status to Closed, so the queue and EspoCRM stay in step. A closed request
  shows its reason and a **Reopen** button. Re-drive / Discard appear when
  applicable. (There's no manual status dropdown any more — the State column
  works itself out from the conversation.)

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

- **…the conversation / the reply-owed State?** The email-derived parts of
  the State column and the conversation need the Gmail integration on for the
  deployment (and the shared mailbox configured). Without them the page says
  exactly which is missing — the queue, Discussion, Activity, and Close all
  still work.
- **…an email the submitter sent that isn't in the conversation?** The
  conversation shows only the threads that belong to THIS submission. Mail
  they sent info@ about something else becomes its own queue item; mail they
  exchanged with a staffer's personal mailbox never involves info@ at all.
- **…the template in the compose?** The template must exist in EspoCRM with
  the exact name `InfoRequestReply` (or the name set in `OPS_REPLY_TEMPLATE`).
  A missing template just opens a blank compose — the template picker inside
  the dialog still lists everything you can use.

## The intended flow for an information request

1. Open Submission Admin — the grid shows **open** items; sort by **State**
   to bring the reply-owed ones to the top.
2. Click the request. Check the **presence line** (is a colleague already on
   it?), read the message and facts on the left, and skim **Discussion** for
   anything a colleague already did.
3. **If it arrived by email** (form "info-email"): first decide — **Approve**
   (a real request; the CRM records are created) or **Discard** (spam; gone,
   no CRM residue). Form submissions skip this step — they delivered on
   arrival.
4. **Email the submitter** — the canned reply is pre-filled on first
   contact; later rounds are proper replies on the same thread. Everything
   sends as **Cleveland Business Mentors <info@cbmentors.org>**, and the
   **Activity** log records that you were the one who sent it.
5. Jot what happened for the team in **Discussion**. The State moves along on
   its own as the conversation goes back and forth.
6. When it's handled, **Close** it with a reason — it leaves the queue (still
   findable under Resolved/All). If the submitter later replies on that same
   thread, it **reopens automatically** and comes back to the queue.

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
