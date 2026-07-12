# The Communications Tab — how it works

A plain-language functional reference for the **Communications** tab in the
session tools (`/mentorsessions`, `/partnersessions`, `/sponsorsessions`),
in the style of `mentor-administration.md`. Technical design:
`prds/communications-gmail-integration.md`; setup:
`GMAIL-INTEGRATION-GUIDE.md`.

## What it is

Each engagement / partner / sponsor record has a Communications tab showing
the **email conversations between you and that record's contacts** — pulled
automatically from your `@cbmentors.org` Gmail, cleaned up, and saved in the
CRM on the record. You can read, reply, and compose without leaving the tool,
and other CBM staff with CRM access see the same conversations on the record.

## Where the conversations come from

Every ~5 minutes, the system reads each manager's CBM mailbox and keeps the
mail that belongs on a record:

1. **Who gets synced:** every manager whose CRM profile has a CBM email
   address AND a linked login user. (Missing either = that mailbox is
   skipped.)
2. **Which records:** only ACTIVE ones — engagements in Active / Assigned /
   Pending Acceptance / On-Hold, current partners, and sponsors.
3. **Which emails:** a message qualifies if either
   - it was exchanged with one of the record's **contacts' email addresses**
     (any address on their contact record), or
   - it's part of a conversation **already on the record** (so replies keep
     arriving even from an address the CRM doesn't know — e.g. after a
     confirmed send to a non-contact).
4. **What's kept out:** Gmail **drafts** (unsent mail never appears),
   spam/trash, and automated mail (no-reply senders, out-of-office
   auto-replies, newsletters with unsubscribe links).

New contact or record? Matching is **retroactive** — when a record becomes
active or a contact gains an address, that person's past mail history is
pulled in on the next cycle, not just future messages.

## What a message looks like (and why it's short)

Each stored message is **only the new text that person wrote**. Quoted
copies of earlier messages, signatures, legal disclaimers, and "sent from my
iPhone" lines are stripped. A reply that contained *nothing but* quoted text
shows as "(no new text — view the original in Gmail)".

Nothing is lost: every message has an **Open in Gmail** link to the complete
original, formatting and attachments included. The CRM copy is the readable
record; Gmail remains the source of truth.

The same email in two mentors' mailboxes (e.g. a CC'd co-mentor) is stored
**once** — both of you see the same conversation.

## The conversation list

One row per conversation: status chip, participants, subject with message
count, a one-line summary, and last activity. Click a row to open the
thread; **Refresh** happens automatically when the tab loads.

If the optional **AI summary** feature is enabled, each conversation also
carries a short summary, an Open / Closed status, action items, and topic
tags — refreshed automatically when new mail arrives. With the feature off
those fields are simply blank.

## Replying and composing

**↩ Reply** (inside a conversation) pre-fills the sender and subject and
threads your reply onto the real Gmail conversation. **✉ Compose** starts a
new email, pre-filled to the record's primary contact.

Mail you send goes out **as you** — from your own `@cbmentors.org` address —
lands in your real Gmail *Sent* folder, and appears in the tab immediately.

**If a recipient isn't a contact on the record**, the compose window stops
and asks what you want to do:

- **"This is a new address for…"** — pick the contact it belongs to. The
  address is saved on their contact record (so their mail auto-matches from
  now on, everywhere) and your email sends normally. *Use this when a client
  writes from a personal address the CRM doesn't know.*
- **"Create contact"** — enter their name; they're added as a contact on
  this record and your email sends. *Use this for a new person who belongs
  on the record — a bookkeeper, a co-founder.*
- **"Send anyway — attach this conversation only"** — a one-off. The
  conversation stays attached to this record and their replies will keep
  arriving (the thread is followed), but the person isn't added as a
  contact. *Use this for third parties — a banker, an outside advisor.*

Emailing another CBM person (`@cbmentors.org`) never triggers this prompt.

## Fixing the list

- **A conversation doesn't belong here:** open it → **"Not related —
  remove"** (click twice to confirm). It's hidden from this record for
  everyone, permanently — the sync won't re-attach it. The mail itself is
  untouched in Gmail.
- **An email is missing:** click **"+ Add emails…"**, search your own
  mailbox (sender, subject, any words), and **"Add to this record"**. The
  whole thread attaches, and future replies follow it automatically. If it
  was missing because the contact wrote from an unknown address, the better
  fix is adding that address to their contact record (see the compose
  options above) so everything auto-matches from then on.

## Who sees what

- You can only ever read **your own** mailbox's mail, and only the slice
  matching your records; the tab only shows conversations linked to records
  you can open.
- Conversations are CRM records (`Conversation` / `Communication`), so CRM
  users also see them in a panel on the engagement/partner/sponsor detail
  view in EspoCRM itself.
- Sending always uses your own address — there is no shared or system
  sender.

## "Why don't I see…?" (quick answers)

| Symptom | Usual reason |
|---|---|
| The tab shows sample data + a banner | The integration isn't enabled on this deployment (`GMAIL_SYNC`) |
| No conversations at all | Your profile lacks a CBM email or linked login user; or the record has no contacts with email addresses; or nothing matched yet |
| A specific email is missing | Sender's address isn't on any contact of this record (use "+ Add emails…" or add the address to the contact); or the record wasn't in an active status; or it's a draft/automated mail (excluded on purpose) |
| A message shows "(no new text…)" | That email contained only quoted text or only images — open it in Gmail |
| An email you sent moments ago isn't in Gmail's thread view yet | It is — the tab shows it instantly; Gmail's own UI can lag a few seconds |
| Two mentors see different conversation lists on the same record | They shouldn't — conversations are shared. If it happens, one mentor's profile is probably missing its CBM email / login link |

New mail appears within one sync cycle (~5 minutes); anything sent from the
tab appears immediately.
