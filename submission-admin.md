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

## What's in the queue (and what closes itself)

Only submissions that need a **reply from this team** stay open: **information
requests** (the web info-request form, and emails to info@). A **client intake,
volunteer, partner, or sponsor** submission creates its CRM records and is then
handled by the downstream admin team (Client / Partner / Funder Administration)
— there's nothing for Submission Admin to do with it, so once it delivers
successfully it **closes itself automatically** with the reason **"Process
completed"** and drops out of the open queue. You'll still find those under
**Resolved / All** (their State reads "Process completed"); if one shows as
*needs attention* instead, its delivery failed and it's worth a Re-drive.

## One status vocabulary — and a receipt in the CRM for every arrival

Since the intake-receipt redesign (2026-07-27), the app and the CRM speak the
**same six words** about a submission's processing state:

| Status | Meaning |
|---|---|
| **Received** | In hand and being processed (covers waiting, delivering, and automatic retries — the filter offers "Received — waiting / delivering / retrying" when you need the distinction). |
| **Completed** | All CRM records were created. |
| **Held-Spam** | The form's hidden spam trap was triggered; nothing was created. |
| **Held-Email** | An email to info@ awaiting your Approve/Discard. |
| **Error** | Delivery failed and a person needs to act (the receipt carries a what-happened-and-how-to-fix explanation). |
| **Discarded** | A person decided no records should be created — always with a recorded reason. |

Every arrival — including every info@ email, *before* anyone touches it — has
a matching **Intake Submission receipt in EspoCRM** showing the same status,
the submitted content (for emails, the message itself plus a Gmail link), and,
once someone acts, **who dispositioned it, when, and why**. The receipt
updates automatically as things change; an hourly reconciliation heals any
write the CRM missed, and the **Sync receipts** button in the toolbar runs
that reconciliation on demand (safe to press any time).

## The front page (the work queue)

- The grid fills the window and scrolls under a sticky header. Every column
  **sorts** (click the header; click again to reverse) and **resizes** (drag
  the right edge of a header). Rows alternate colors; clicking anywhere on a
  row opens it.
- The **search box at the top center** filters live across reference, form,
  intake status, response status, submitter, error text, notes, and dates.
- Two plainly-separate status columns replace the old blended "State":
  - **Intake status** — *what happened to this arrival?* — straight from the
    CRM receipt: **Received / Completed / Held-Spam / Held-Email / Error /
    Discarded**.
  - **Response status** — *where does the reply conversation stand?* —
    **New → In progress → Reply owed / Waiting on them → Responded → Closed**
    (**Delivery failed** if a reply bounced). It's worked out for you from the
    stored request status and the live emails. Sorting by it surfaces the
    reply-owed items first. The reply lifecycle only applies once an item is a
    **live request** (a delivered form, or an *approved* email): a Held-Email
    that nobody has triaged yet reads **Awaiting review** (never a reply
    direction), and a Held-Spam / Error / Discarded arrival — which has no
    conversation — reads **—**.
- **Three filters** (Intake status / Response status / Form), each offering
  **every** value, plus a live search. The Response-status filter also has an
  **Open (not closed)** shortcut for the work-queue view.
- **The count chips are clickable filters.** Each chip at the top —
  `Completed`, `Held-Email`, `Error`, … and `open` / `resolved` — applies the
  filter that produced its count when you click it (click again to clear); the
  matching filter dropdown stays in step. `total` clears all filters.
- The **Last activity** column shows **who did the last thing and when** —
  the signal that a colleague is already on an item (there's no formal
  "owner"; visibility is how the team avoids two people answering the same
  request). Sort by it to find what's gone quiet.
- **Re-drive** re-queues a stuck submission (Error / Held / Discarded) for
  the worker to run again — safe, it resumes from what was already created.
  **Discard ▾** parks one for good and **requires a reason** (Spam / Junk /
  Duplicate / Not actionable / Other + note): the decision — who, when, why —
  is recorded on the row, in the Activity feed, and on the CRM receipt. Undo
  a mistaken discard by re-driving.
- **Inbound emails** (form "info-email", status **Held-Email**) carry
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
conversation view (and the State column) reads.

## Other correspondence

The **Other correspondence** button (top of the queue, shown when the shared
info@ mailbox is configured) opens a separate list: inbound email on
info@cbmentors.org that **isn't tied to a submission**. In practice this is
someone replying to a message staff sent as info@ — from a record's
Communications tab, or the quick-compose "email this address" links. Those
replies land in the info@ inbox but never become queue items (the poller only
turns genuinely new inbound requests into submissions), so without this list
they'd sit unseen in Gmail.

Each row shows who it's with, the subject, when the last message arrived, and
a **Reply owed** chip when they spoke last. Click a thread to read it, then
**Reply** — the reply goes out as info@ (Cleveland Business Mentors) and stays
on the same email thread, exactly like a submission reply. Nothing here is
stored or tracked as a work item; it's a live window on the shared inbox so
you don't have to open Gmail. Threads that ARE submissions never appear here —
they're in the queue.

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
   arrival. *(You don't have to Approve separately before replying: clicking
   **Reply to the submitter** on a not-yet-approved email will offer to approve
   it for you — a reply is a real request, so it confirms first that the Intake
   status will move Held-Email → Received and the CRM records will be created,
   then opens the compose.)*
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
