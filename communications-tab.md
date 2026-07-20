# The Communications Tab — how it works

A plain-language functional reference for the **Communications** tab in the
session tools (`/mentorsessions`, `/partnersessions`, `/sponsorsessions`),
in the style of `mentor-administration.md`. Technical design:
`prds/communications-gmail-integration.md`; setup:
`GMAIL-INTEGRATION-GUIDE.md`.

> **The bigger picture:** this tab is one surface of CBM's email system.
> [`email-management.md`](email-management.md) is the umbrella reference —
> the My Email unified inbox, the compose dialog's full feature set, the
> two sending identities, and Submission Admin's email handling (form
> submitters + the shared info@ mailbox) are documented there.

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

Every message in the thread is headed by **who wrote it** — the sender's
name (or address) for received *and* sent mail alike; a sent message shows
the recipients after an arrow ("Doug Bower → james@acme.test"). With a
mentor and a co-mentor both working the same engagement, the thread shows
which of you said what.

## The conversation list

One row per conversation: status chip, participants, subject with message
count, a one-line summary, and last activity. Click a row to open the
thread; **Refresh** happens automatically when the tab loads.

The list works like the other grids: **click a column header to sort**
(click again to reverse — Last activity sorts newest-first), and **drag the
grip on a header's right edge to resize columns**. Your column widths and
sort choice are kept while you move between tabs on the record.

**Participants** lists everyone who was on the emails — senders *and* To/Cc
recipients — so a person who was included but never replied still shows.
Each person appears once (matched by email address), as their name with
address when a message carried a display name, otherwise the bare address.
Conversations synced before this change listed only senders; they fill in
automatically as new messages arrive on the thread.

If the optional **AI summary** feature is enabled, each conversation also
carries a short summary, an Open / Closed status, action items, and topic
tags — refreshed automatically when new mail arrives. With the feature off
those fields are simply blank.

## Replying and composing

**↩ Reply** (inside a conversation) pre-fills the subject and pre-checks the
sender in the recipient list, threading your reply onto the real Gmail
conversation. **✉ Compose** starts a new email with **every contact on the
record (that has an email address) listed as a checked To recipient** —
uncheck anyone you don't want to include. An **"Other recipients"** field
takes addresses that aren't contacts on the record.

The **message box is a full rich-text editor**: bold, italics, lists, links,
text color, and tables, and you can paste formatted content straight in from
another email or document. Your message goes out as a normal formatted
(HTML) email; recipients whose mail client prefers plain text automatically
get a plain-text version of the same message.

**Your email signature is added automatically.** Every new message (and
reply) opens with your signature already at the bottom of the body — from
there it's ordinary text you can edit or delete for that one message. The
signature is your **EspoCRM signature**: set it up either in **My Mentor
Profile** (the "Email signature" panel) or in EspoCRM under your avatar
menu → Preferences → Email Signature — both edit the same signature. No
signature set = messages open with an empty body, exactly as before.
Choosing a template keeps the signature: the template text loads and your
signature is re-added below it (so templates themselves shouldn't include a
sign-off).

Mail you send goes out **as you** — from your own `@cbmentors.org` address —
and appears in the tab immediately. A copy also lands in Gmail's *Sent*
folder, but note **which** mailbox: the `@cbmentors.org` one. If you
normally read mail signed into a different Google account (personal,
admin@, …), its Sent folder will never show these — switch to your
`@cbmentors.org` account in Gmail to see them.

**If a recipient isn't a contact on the record**, the compose window looks
each address up across the whole CRM and shows one row per recipient, each
with an **"Add to this record" checkbox** (checked by default):

- **Already a CRM contact** (client, non-client, or CBM member — from any
  record): the row shows who they are — "*jane@chenco.test — Jane Chen
  (Chen Co, already in the CRM)*". Leave the box checked and they're linked
  to this record when you hit Send. No duplicate contact is ever created.
  A **CBM member** (matched by their `@cbmentors.org` address or a
  Mentor-typed contact) gets the same row with the checkbox labeled **"Add
  as CBM contact"** — on an engagement that adds them as a co-mentor rather
  than a client contact.
- **New to the CRM**: the row shows a small form — first name, last name,
  phone, and company (pick an existing company from the list, or choose
  "+ New company…" and type a name; the company is created in the CRM).
  Leave the box checked and fill it in; Send creates the contact on this
  record and sends.
- **Uncheck the box** on any row to send without adding that person — a
  one-off. The conversation still attaches to this record and their replies
  keep arriving (the thread is followed); they just don't become a contact.

One **Send** click does it all: checked rows are linked/created first, then
the email goes out.

## Email addresses anywhere in the apps are compose links

Wherever an email address appears in the staff tools — a contact table, a
pop-up card, the mentor roster, the attendee grid — **clicking it opens a
compose window** instead of your computer's mail program:

- **Inside an open engagement/partner/sponsor record**, it opens the full
  compose described above (recipient pre-filled, contact add/create routing,
  record linking).
- **Everywhere else** (the record lists' pop-ups, Client Administration,
  Mentor Administration), it opens a lighter quick-email window — To /
  Subject / Message, sent as your own `@cbmentors.org` address. The message
  isn't attached to a record directly; the regular sync files it onto the
  matching record from your Sent mail, exactly as if you'd sent it from
  Gmail.

If sending from the app isn't possible for you (no CBM mailbox on your
profile, or the Gmail integration is off on that deployment), the click
falls back to your computer's normal email handler. Middle-click /
copy-link-address still behave like a regular email link.

## Email templates

The compose window has a **Template** picker listing the email templates CBM
administrators maintain **in EspoCRM** (that's also where templates are
created and edited — not in this app). You only see the templates your CRM
role allows; type in the filter box to narrow the list. Templates filed
under a CRM category named *Engagement*, *Partner*, or *Sponsor* appear
only in that tool's compose window; templates with no category (or any
other category) appear everywhere.

Selecting a template loads a **fully personalized draft**: EspoCRM itself
fills in every placeholder (the client's name, your name, the record's
details) before the text reaches your screen. What you get is a plain
editable draft — rewrite anything, change the subject, delete paragraphs.
If you already had text in the window, the app asks **"Replace current
content?"** first, and choosing a template never silently destroys a draft.

**Placeholders template authors can rely on** (anything else stays as a
literal `{…}` token):

| Placeholder | Fills in with |
|---|---|
| `{CMentorProfile.name}` (or any profile field) | the record's **assigned mentor** (partner/sponsor manager on those records); when the record has none, the profile of whoever is composing. In the quick-compose it's always the sender's profile. |
| `{User.name}` | the person **sending** the email |
| `{Person.firstName}`, `{Person.name}`, … | the **recipient** (the first To address, when it matches a CRM contact) |
| `{Parent.name}` (or any record field) | the engagement / partner / sponsor record itself |

If a placeholder can't be filled (say the template mentions a field this
record doesn't have), the draft keeps the literal `{Something.field}` token
and the window shows a **review-before-send notice** listing them — read the
draft over and fix or remove them before sending.

**Attachments:** a template's standing attachments appear as **chips** under
the message — click ✕ to drop any of them. You can also **attach your own
files** with the "Attach files…" button (up to 20 MB per message). Template
attachments aren't downloaded until you actually hit Send; if one can't be
fetched at that moment, **the message is not sent** (you'll never send an
email that silently lost its attachment).

**Where the sent message is recorded:** every send from the app is stored
twice — as a message in the record's conversation here in the tab, **and**
as a native EspoCRM Email record (visible in the contact's History panel in
the CRM, attributed to you). If that CRM record can't be written after the
message already went out, the window tells you and offers a **Retry** —
it's never silently skipped.

The same template picker and attachments are in the **quick-compose**
dialog that opens when you click an email address in the staff grids
(Client/Mentor Administration and the session-tool grid pages). There the
personalization comes from the recipient's address — if it matches a CRM
contact, person placeholders fill in with their details.

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
| An email you sent from the tab isn't in your Gmail **Sent** folder | You're looking at the wrong account's Sent folder — the tab sends as your `@cbmentors.org` mailbox, so the Sent copy is there, not in a personal/other account you may be signed into |
| Two mentors see different conversation lists on the same record | They shouldn't — conversations are shared. If it happens, one mentor's profile is probably missing its CBM email / login link |

New mail appears within one sync cycle (~5 minutes); anything sent from the
tab appears immediately.
