# How Email Works — Executive Summary

*Cleveland Business Mentors application suite · current as of July 21, 2026*

Every email the system sends or receives goes through CBM's own Google
Workspace (Gmail). The application never runs its own mail server, so
deliverability, security, and retention are Google's — and every message,
inbound or outbound, also exists in a real Gmail mailbox that staff can open
directly if ever needed.

There are **two sending identities**, and knowing which one applies is the
key to understanding the whole system:

| Identity | Used for | Who sees replies |
|---|---|---|
| **The mentor's own mailbox** (e.g. jane.smith@cbmentors.org) | Relationship mail: mentors writing to their clients, partners, and funders | The mentor, in their own mailbox and in the app |
| **"Cleveland Business Mentors" (info@cbmentors.org)** | Organizational mail: responses to website inquiries, staff notices, and the CRM's own automated messages | The Marketing Admin team, in the shared queue and the info@ inbox |

The rule of thumb: **mail from a person comes from that person; mail from
the organization comes from Cleveland Business Mentors.**

---

## 1. The public website forms

The five intake forms (client intake, volunteer, request for information,
partner, sponsor) create records in the CRM when submitted. They do **not**
send the submitter a confirmation email — a deliberate choice. When a
response is warranted, staff send it personally from Submission Admin (below),
so the first email a prospect receives from CBM is a real answer, not an
autoresponder.

## 2. Submission Admin — the organizational inbox

Submission Admin is where form submissions and inbound email meet.

- **Inbound:** the system checks the info@cbmentors.org inbox every five
  minutes. Each new email thread appears in the queue as a held item. Staff
  either **Approve** it (creating the same CRM records a website
  information request would) or **Discard** it (spam leaves no trace in the
  CRM). Automated bounce notices and threads CBM itself started are filtered
  out automatically.
- **Outbound:** replies from Submission Admin are sent as **Cleveland Business Mentors**, with
  no personal signature. Because each conversation is anchored to its
  submission, every admin sees the same complete thread — who replied, what
  was said, and when — regardless of who handled it.
- **Follow-up at a glance:** each open item shows whether CBM owes a reply
  ("reply owed") or is waiting on the submitter. If a reply could not be
  delivered — a mistyped address, for example — the item is flagged in red
  ("delivery failed") and the conversation shows the mail system's reason.
  A failed delivery is never silent.

## 3. Mentor tools — Client, Partner, and Funder Management

Mail between a mentor and the people they serve is personal, and the system
keeps it that way.

- **Sending:** every compose window in these tools — replying in a record's
  Communications tab, or clicking any email address in the app — sends from
  the **mentor's own** @cbmentors.org mailbox, with their personal signature
  added automatically.
- **Receiving:** the system continuously reads each mentor's CBM mailbox and
  files correspondence with their clients, partners, and funders onto the
  matching record in the CRM — cleaned of signatures and quoted reply
  chains, with the original always one click away in Gmail. Only
  correspondence with people on the mentor's *active* records is captured;
  internal staff-to-staff mail and marketing/automated mail are excluded.
- **My Email** gives each mentor a single inbox view of these conversations
  across every record they manage, with unread and awaiting-reply markers.
- Every message sent from the app is also recorded in the CRM on the
  recipient's contact history, so the CRM remains the complete record.

## 4. Mentor-to-mentor email

When one mentor emails another — a co-mentor, or a colleague — the message
always goes out from **the sending mentor's own** @cbmentors.org mailbox,
never from Cleveland Business Mentors. Peer discussion is personal mail.

What differs is **whether the CRM keeps a copy**, and that depends on where
the message is written:

- **Written from a client record** (the Communications tab of an engagement,
  partner, or funder): the message is filed on that record, exactly like a
  message to the client. Writing from the record is the deliberate signal
  that the discussion belongs to it — for example, co-mentors coordinating
  about their shared client.
- **Written anywhere else** (Gmail directly, or a compose window not tied to
  a record): internal mail between @cbmentors.org addresses is **not**
  captured into the CRM at all. Private peer conversation stays in Gmail.

The rule of thumb for mentors: *if the discussion is about a client and
should be part of the client's history, write it from the client's record;
otherwise use Gmail and it stays between you.*

## 5. Staff administration tools — Client Administration and Mentor Administration

Notices sent from the staff tools — for example, the assignment notice a
mentor receives when a new client is assigned — go out as **Cleveland Business Mentors**.
These are organizational messages, not personal correspondence. Replies to
them arrive in the info@ inbox, which the Marketing Admin team monitors.

## 6. Meeting invitations

When a mentor schedules a session, the calendar invitation comes from
**Google Calendar** on the mentor's behalf — it is a calendar event, not an
app email. Clients are invited at their own addresses; CBM members are
always invited at their @cbmentors.org address, never a personal one, so
nobody receives a duplicate copy of their own meeting.

## 7. The CRM's own automated email

Messages EspoCRM generates itself — the welcome email when a new mentor
login is created, password-reset links — are sent from **info@cbmentors.org**
("Cleveland Business Mentors"). The old espo@ address has been retired from outgoing mail.

## 8. System monitoring

Operational alerts (delivery backlogs, integration problems) go to
**admin@cbmentors.org** and come from admin@ — internal plumbing,
deliberately kept off the customer-facing info@ identity.

---

## Who sees what

- **A mentor** sees the email conversations on their own records, and their
  My Email inbox. They never see another mentor's correspondence or the
  organizational queue.
- **The Marketing Admin team** works the Submission Admin queue and watches
  the info@ inbox. They see every organizational conversation, but not
  mentors' relationship mail.
- **Everything sent from the app is also in Gmail** — a mentor's sends in
  their own Sent folder, the organization's in the info@ account — so
  nothing depends on the application to be readable.

*Deeper references: `email-management.md` (the full system reference),
`communications-tab.md` (mentor-facing guide), `submission-admin.md`
(admin-facing guide).*
