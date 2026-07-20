# Email Management — how CBM's email works, end to end

A plain-language functional reference for **everything email** in the CBM
apps, in the style of `mentor-administration.md`. This is the umbrella
document: it maps the whole system and covers each surface; two companion
docs go deeper — [`communications-tab.md`](communications-tab.md) for the
record-level Communications tab and
[`submission-admin.md`](submission-admin.md) for the Submission Admin tool.
Technical design: `prds/communications-gmail-integration.md`;
setup/activation: `GMAIL-INTEGRATION-GUIDE.md`.

**Contents**

1. [The big picture](#1-the-big-picture)
2. [The two sending identities](#2-the-two-sending-identities)
3. [Where you read email](#3-where-you-read-email)
4. [Writing email — the compose dialog](#4-writing-email--the-compose-dialog)
5. [Templates and signatures](#5-templates-and-signatures)
6. [Submission email management (Submission Admin)](#6-submission-email-management-submission-admin)
7. [Who sees what](#7-who-sees-what)
8. [Requirements and switches (for administrators)](#8-requirements-and-switches-for-administrators)
9. [Quick answers](#9-quick-answers)

---

## 1. The big picture

CBM email is ordinary **Gmail** underneath — every mentor and manager has an
`@cbmentors.org` mailbox, and there is one shared **info@cbmentors.org**
mailbox for the intake/information-request process. The apps sit on top of
Gmail and do three things:

- **Collect.** Every ~5 minutes the system reads each manager's CBM mailbox
  and files the mail that belongs to a client / partner / funder record into
  the CRM as a *conversation* on that record. Messages are cleaned (quoted
  copies, signatures, and boilerplate stripped) so the record reads like a
  transcript; the complete original always stays one click away in Gmail.
- **Show.** You read those conversations in three places — your unified
  **My Email** inbox, each record's **Communications tab**, and (for
  form submissions) **Submission Admin**. The same conversation looks the
  same everywhere.
- **Send.** Every email address shown anywhere in the staff apps is a
  **compose link** — clicking it opens the app's own compose dialog rather
  than your desktop mail program. Mail you send from the apps goes out
  through real Gmail, appears in your Gmail Sent folder, is filed onto the
  record like any other message, and is also recorded as an Email in the
  CRM's own history panels.

Nothing here replaces Gmail — you can always work in Gmail directly, and the
sync will file record-related mail either way. The apps exist so you don't
have to leave the record you're working on, and so the whole team can see
the history.

## 2. The two sending identities

| Identity | Used by | Signature | Purpose |
|---|---|---|---|
| **Your own mailbox** (`firstname.lastname@cbmentors.org`) | My Email, the record Communications tabs, every quick-compose in the staff tools | Your personal signature, seeded automatically | Relationship mail — you, personally, working with your clients, partners, and funders |
| **The shared mailbox** (`info@cbmentors.org`, displayed as **"CBM Info"**) | Submission Admin (`/ops`) only | None (deliberately generic) | Process mail — answering form submitters and information requests on behalf of the organization |

The split is intentional: a mentoring relationship speaks with a person's
voice; the intake process speaks with the organization's. Submission Admin
replies never carry a staffer's name or personal signature, and any admin
can pick up a conversation another admin started, because it all lives in
the one shared mailbox.

(Every send is still attributed internally — the app logs which signed-in
user sent each message, whichever identity it went out under.)

## 3. Where you read email

### My Email — your unified inbox (`/myemail/`)

The portal's **My Email** tile opens one inbox covering **every record you
manage** — client engagements, partners, and funders together. Each row
shows the record it belongs to (click the chip to open that record), who's
on the thread, the subject, and when the last message arrived.

- **Unread** rows are bold with a blue dot: the conversation has a message
  newer than the last time *you* opened it. (Unread state is per-person —
  your co-mentor opening a thread doesn't mark it read for you.) On day one
  the app doesn't bold your whole history: only conversations from the last
  30 days count as unread until you've opened them once. **Mark all as
  read** clears the backlog in one click.
- **Awaiting your reply** (amber chip): the last message in the conversation
  is *theirs*. Reading it doesn't clear the chip — replying does. This is
  the "don't drop the ball" view; there's a filter tab for it, with a count.
- Clicking a row opens the thread. To reply, use **"Open in record — reply
  there"** — replies happen on the record page, where the full compose
  (contact linking, templates, documents) lives.

### The record's Communications tab

Every engagement / partner / funder record has a Communications tab with
that record's conversations — the same data as My Email, scoped to one
record, plus curation: **"Not related — remove"** takes a mis-filed
conversation off the record, and **"Add emails…"** searches your mailbox to
attach one the sync didn't catch. The tab button shows the record's unread
count — "Communications (2)" — until you open the threads. Full detail:
[`communications-tab.md`](communications-tab.md).

### Submission Admin

Form submissions have their own email view — see
[section 6](#6-submission-email-management-submission-admin).

## 4. Writing email — the compose dialog

One compose dialog serves the whole product (the record pages get the full
version; address-click quick-composes elsewhere get the same dialog without
the record-specific extras). It opens at 90% of your window and can be
resized by dragging the bottom-right corner; the Send/Cancel bar stays
pinned while the body scrolls.

**Recipients.**
- On a record, every contact with an email address appears as a checkbox —
  all selected for a fresh message, so "email the client team" is the
  default. Uncheck to leave someone off; **All / None** shortcuts appear on
  long lists.
- **Other recipients** takes typed addresses (commas between them;
  `Jane Doe <jane@x.org>` works). **Cc** and **Bcc** reveal from the links
  on that line. Anything that isn't a valid address is named in an error
  before anything sends, and the footer always shows a live count —
  "Sending to 3 recipients (2 To, 1 Cc)".
- Sending to someone who **isn't a contact on the record** pauses the send
  once: each such address gets an "Add to this record" row (existing CRM
  people link; brand-new people get a small create form; CBM members become
  CBM contacts, never client contacts). Leave the box checked to add them,
  or uncheck to send one-off; then click **Add & Send**. Either way the
  conversation stays on the record and their replies keep arriving.

**Reply, Reply All, Forward.** From a thread: **Reply** answers the last
sender; **Reply all** appears when the thread has several participants
(your own address excluded); **Forward** opens with nobody selected, a
"Fwd:" subject, and the message in a forwarded block — forwarding without
adding a comment is fine. Replies and forwards carry the original message
as a quoted block so you write with the context in front of you, and
Cancel returns you to the thread, not to a closed dialog.

**Attachments.**
- **Attach files…** uploads from your computer; chips show each file's size
  and a running total against the 20 MB per-message limit.
- **Attach from documents…** (record compose, where the document integration
  is on) lists the record's Documents tab — attach the client's business
  plan without downloading and re-uploading it. The app fetches the
  original file at send time; if it can't, the send is blocked with a clear
  message rather than going out incomplete.

**You can't lose a draft.** Everything you type autosaves in your browser.
Closing the dialog with real content asks "Discard this draft?" first —
and even a crash, an accidental tab close, or a session timeout brings the
draft back the next time you open a compose there ("Restored your unsent
draft", with a Start-fresh button). Sending or discarding clears it.

**You can't send a broken email.** An empty message is blocked; a missing
subject or an unfilled template placeholder turns the button into an
explicit **"Send anyway"** with an amber explanation — one more click sends
it as-is. Big sends show upload progress on the button. Ctrl+Enter (or
Cmd+Enter) sends from anywhere in the dialog.

## 5. Templates and signatures

**Templates** are authored in EspoCRM (Emails → Email Templates) and appear
in every compose's searchable **Template** picker. The CRM fills the
placeholders — `{Person.name}`, `{Parent.*}`, `{CMentorProfile.*}` — against
the record and recipient, and the app loads the result as an editable
draft:

- Templates render in **one uniform font** — the filled-in values are
  indistinguishable from the authored text, so the recipient can't tell a
  template was used. (Structure — bold, links, lists — survives; typeface
  and color styling is deliberately flattened.)
- Placeholders the CRM couldn't fill stay visible as `{…}` tokens with an
  amber warning, and the Send button makes you confirm before one goes out.
- Picking a template over an edited draft asks first; **"No template"**
  restores what you had. Template attachments arrive as removable chips.
- A template whose EspoCRM *category* is named `Engagement`, `Partner`, or
  `Sponsor` appears only in that tool's picker; templates with no category
  (or any other category) appear everywhere.
- Don't put sign-offs in templates — the app appends the sender's signature
  below the rendered draft automatically.

**Signatures** are per-person: mentors edit theirs in **My Mentor Profile →
Email signature**; other staff use EspoCRM → Preferences → Email Signature.
The signature seeds into every new personal-identity compose. Submission
Admin's shared info@ identity never adds one.

## 6. Submission email management (Submission Admin)

Form submissions are a **subset of email management** with their own rules,
handled in **Submission Admin** (`/ops`, Marketing Admin Team). This section
covers the email side; the tool's full reference — the work queue, the
detail tabs, the intended information-request flow — is
[`submission-admin.md`](submission-admin.md), and the end-to-end design
summary (inbound + outbound lifecycles, plus the Google Workspace changes
that activate the shared mailbox) is
[`submission-email-flow.md`](submission-email-flow.md). A
"submission" is anything that enters the intake pipeline:

- the five public forms (client intake, volunteer, information request,
  partner, sponsor), and
- **inbound email to info@cbmentors.org** (see below) — email itself can BE
  a submission.

### The queue, not just a log

The Submission Admin grid is a work queue. Each submission row shows its
delivery status (was it written into the CRM?), a **Resolved** workflow
that's independent of delivery — **Mark resolved** when the human process
is finished, **Reopen** if it isn't; the grid defaults to showing **Open**
items — and a **Reply** column showing where the conversation stands with
each open submitter:

- **↳ reply owed** — their message is newest; the ball is in CBM's court.
- **waiting on them** — CBM spoke last.
- **—** — no conversation yet.

### Talking to submitters — as CBM Info

Opening a submission shows the submitter's details, staff triage notes, and
the **email conversation with that submitter**. "Email the submitter" (or
**"↩ Reply to the submitter"** once a conversation exists) opens the
standard compose — but it sends as **info@cbmentors.org / "CBM Info"**, with
no personal name or signature. Replies stay on the same Gmail thread, so
the submitter sees one continuous conversation no matter which admin
answers.

A **new** conversation on an information request opens with the
`InfoRequestReply` template already applied — edit and send, or clear it.

(Until the shared mailbox is activated, Submission Admin falls back to each
admin's own mailbox — sends go out under your name, and each admin sees
only the conversations from their own mailbox. The shared-identity model
above is the intended operating state; see section 8.)

**Anchoring — why unrelated mail can't appear.** Every reply sent from
Submission Admin records its Gmail thread on that submission. The
conversation view shows **exactly the anchored threads** — not a search of
addresses — so a submitter who also happens to email about something else
never has that mail show up on the submission. (Earlier versions searched
by address and could pick up unrelated messages; that's fixed.)

### Inbound email becomes a submission

The worker watches the info@ inbox. A **new inbound thread** — someone
simply emailing info@cbmentors.org — is captured as a **held submission**
("Email" form): sender, subject, and the cleaned message text, waiting in
the queue like any form submission. Nothing touches the CRM until a human
decides:

- **Approve** ("Create CRM records?") delivers it like an information
  request — Contact, company where given, an Information Request record,
  and the audit-log entry — with the message text preserved.
- **Discard** removes it with zero CRM residue (spam, misdirected mail).
  Discard can be undone.

Replies from a submitter to an **existing** submission conversation join
that conversation — they never become a duplicate queue item. Bounce
messages and mail the process itself sent are ignored.

### The audit trail

Every submission — form or email, delivered, held, or discarded — is also
logged as a `CIntakeSubmission` record in the CRM (the raw input, the
outcome, and a link to the created Contact), so the CRM keeps a complete
inbound history even for items handled entirely in Submission Admin.

## 7. Who sees what

- **Conversations on a record** are visible to the staff who can see that
  record in the CRM — a co-mentor sees the engagement's conversations,
  including mail from your mailbox that belongs to the shared record.
- **My Email** shows only conversations on records *you* manage (owned or
  co-mentored) — it is scoped by your assignments, not by raw CRM
  permissions.
- **Unread is personal.** Read/unread state is tracked per person; your
  reading never marks anything read for a colleague.
- **Submission conversations** live in the shared info@ mailbox and look
  identical to every Submission Admin user.
- **Your Gmail is still yours.** The sync stores only cleaned,
  record-related text in the CRM; drafts never sync; personal mail that
  matches no record is never read into anything.

## 8. Requirements and switches (for administrators)

What each capability needs. All email features degrade gracefully — when a
requirement is missing the UI says so plainly (or falls back, e.g. a
compose link falling back to your desktop mail program).

| Capability | Needs |
|---|---|
| Everything email | `GMAIL_SYNC=true` (web + worker) + the Google service-account/DWD setup (`GMAIL-INTEGRATION-GUIDE.md`) |
| A person sending/reading as themselves | Their CRM profile has a `cbmEmail` and a linked login user |
| My Email tile | Member of any management-tool team; Gmail integration on |
| Unread badges | The database (they ride the durable store; migration 0010) |
| Attach from documents | `GDRIVE_DOCS` on (the document integration) |
| Templates | Authored in EspoCRM; the user's role can read EmailTemplate |
| Signatures | The user's EspoCRM Preferences signature (mentors: My Mentor Profile) |
| Submission Admin shared identity | info@cbmentors.org as a real licensed Workspace mailbox + `OPS_MAILBOX=info@cbmentors.org` (web + worker); `OPS_MAILBOX_NAME` overrides the display name |
| Inbound info@ capture | The shared mailbox above; `OPS_INBOUND_SECONDS` tunes the poll (default 5 min) |
| Canned info-request reply | An EspoCRM template named `InfoRequestReply` (`OPS_REPLY_TEMPLATE` overrides) |
| AI conversation summaries | `COMMS_AI_SUMMARY=true` + `ANTHROPIC_API_KEY` (worker) — off pending privacy sign-off |

## 9. Quick answers

**Where is the mail I sent from the app?** In the Sent folder of the
mailbox it went out from — your own `@cbmentors.org` account for personal
sends, info@cbmentors.org for Submission Admin sends. Not your personal
Gmail.

**Why don't I see a conversation my co-mentor sees?** My Email only lists
records you manage; check the record itself — record conversations are
shared. If it's a *submission* conversation, it's in Submission Admin, not
the record tools.

**Why is a whole month of old threads bold?** They arrived in the last 30
days and you haven't opened them in the app yet. **Mark all as read** and
move on — from then on only genuinely new messages go bold.

**"Awaiting reply" won't go away after I read it.** Reading isn't
replying — the chip clears when the newest message in the thread is yours.

**A conversation is on the wrong record.** Open it there and use **"Not
related — remove"**; use **"Add emails…"** on the right record if it should
live somewhere else.

**Why did my template go out in a different font than I authored?** It
didn't — the app deliberately flattens template typography so the whole
message (template text, filled-in names, your own additions) reads as one
personally-written email.

**Can a submitter tell which admin replied?** No — Submission Admin mail is
from "CBM Info <info@cbmentors.org>" with no personal signature. The app's
logs (not the email) record which admin sent it.

**Someone emailed info@ — where did it go?** If it started a new thread, it
became a held submission in Submission Admin (approve it to create CRM
records). If it was a reply to an existing submission conversation, it's on
that submission.
