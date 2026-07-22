# Submission Email — how it works, end to end

*A summary of the v0.110.0 design: how inbound email to
**info@cbmentors.org** becomes a submission, how staff respond to a form
submission by email, and exactly what has to change in Google Workspace to
turn it on. Companion docs: [`submission-admin.md`](submission-admin.md)
(the Submission Admin tool itself), [`email-management.md`](email-management.md)
(the umbrella email reference), `GMAIL-INTEGRATION-GUIDE.md` (the original
Google service-account setup, already live).*

## 1. The model in one paragraph

CBM's information-request process has two front doors — the **website form**
and the **info@cbmentors.org address** — and one back office: the
**Submission Admin queue**. Both doors feed the same queue; all email in the
process, inbound and outbound, lives in the **one shared info@ mailbox**
under the generic identity **"Cleveland Business Mentors"**. Each submission is tied to *its
own email threads* in that mailbox — the thread the submitter started, plus
any thread staff started from the submission page — so its conversation
shows exactly the correspondence about that request and nothing else, and
every admin sees the identical picture. The **inbound-requests table (the
submission queue) and the CRM's Information Request records are the single
source of truth**: everything that arrives is captured durably; the CRM
records are created for everything staff approve.

## 2. Inbound: an email to info@ becomes a submission

**Lifecycle:**

1. **Someone emails info@cbmentors.org.** Nothing is required of them — no
   form, no format.
2. **The worker polls the info@ inbox** (every 5 minutes,
   `OPS_INBOUND_SECONDS`). It looks at recent inbox threads and asks, for
   each: *is this thread already tied to a submission?*
   - **Yes** → it's a reply in an existing conversation (perhaps to a
     message staff sent from a form submission's page). It is **not**
     captured again — it simply appears in that submission's conversation,
     and flips the grid's Reply column to "↳ reply owed".
   - **No** → it's a **new request**. The app captures it durably as an
     **info-email submission**: sender name + address (parsed from the
     From header), subject, and the cleaned message text (signatures and
     quoted chains stripped; the original stays in Gmail). The row enters
     the queue in **held review** status.
3. **Staff triage in Submission Admin** — this is the deliberate
   *triage-first* rule: **nothing is written to the CRM at capture**,
   because a public mailbox receives spam.
   - **Approve** ("Create CRM records?") delivers the submission through
     the same pipeline as the website form: find-or-create the **Contact**
     (Prospect), the **Account** when a company is identifiable, the
     **Information Request** record (`form="info-email"`,
     `source="Email"`, the subject folded into the message), and the
     `CIntakeSubmission` audit log. Retries, resumability, and the
     idempotency guarantees of the form pipeline all apply.
   - **Discard** removes it with **zero CRM residue**. (Undoable —
     Re-drive brings it back.)
4. **The conversation continues** on the same thread (section 3), and when
   the request is done staff **Mark resolved**. If the same person emails
   again later on a *new* thread, that is a *new* queue item — by design: a
   resolved request stays resolved, and new contact means someone is
   waiting again.

**What is deliberately ignored:** delivery bounces (mailer-daemon /
postmaster), threads the mailbox itself started (staff writing from the
Gmail UI — outbound, not a request), and anything Gmail already classified
as spam (the poller reads only the inbox; a periodic glance at the spam
folder in Gmail is still wise). Deliberately **not** filtered: noreply /
newsletter mail — Discard is two clicks, and silent filtering risks losing
a real request.

**Dedup guarantees:** the submission's idempotency token *is* the Gmail
thread id, so a thread can never capture twice; and any thread anchored to
any existing submission is skipped. There is no sync cursor to corrupt —
every poll re-derives its picture from the inbox + the database.

**Edge cases:**
- *Form + email from the same person* → two queue items (correct: two
  requests until a human says otherwise). Handle one, discard or resolve
  the other, and say so in the submission notes.
- *Unparseable sender names* ("acme" with no surname) are captured with a
  placeholder last name — staff fix it in the CRM after approving.
- *A malformed email that can't validate* is still captured (never lose an
  email); approving it routes to needs-attention with the reason, where it
  can be discarded.

## 3. Outbound: responding to a form submission

**Lifecycle** (identical for all five forms; the info-request is the
primary case):

1. A form submission arrives and is delivered to the CRM as usual. It sits
   **open** in the Submission Admin queue with **"—"** in the Reply column
   (no conversation yet).
2. Staff open it and click **✉ Email the submitter**. The standard compose
   opens with the submitter's address pre-filled; on a fresh info-request
   conversation the **`InfoRequestReply`** EspoCRM template is pre-applied
   (subject + body, personalized to the recipient — edit freely). The
   template picker offers every other template too.
3. **The message sends as `Cleveland Business Mentors <info@cbmentors.org>`** — never the
   staffer's name, address, or personal signature. (Which admin clicked
   Send is logged internally, and the send is also written back as a native
   EspoCRM **Email** on the matching Contact's History panel.)
4. **The sent thread is anchored to the submission.** That anchor is the
   whole trick: the conversation view and the Reply column read *only
   anchored threads*, so the submission shows this exchange and nothing
   else — a volunteer who also corresponds with CBM about ten other things
   never pollutes the submission again.
5. **The submitter replies** — their reply lands on the same Gmail thread
   in the info@ inbox. The poller recognizes the anchored thread (no new
   queue item), the conversation shows it to every admin, and the Reply
   column flips to **↳ reply owed**. Later sends from the submission page
   are proper replies ("Re:" subject, same thread in both inboxes).
6. When the exchange is finished: **Mark resolved.**

**Notes:**
- For an **email-originated** submission, approve before replying if you
  want template personalization and the Contact-history write-back — both
  need the Contact to exist. Replying first still works (the thread is
  already anchored); it's just less connected in the CRM.
- Working **directly in the info@ Gmail UI** is a legitimate fallback:
  replies sent there are on the same threads, so they appear in the
  submission conversations too. They just skip the template machinery and
  the CRM Email write-back.
- Submission email is deliberately **outside** the record-level
  Communications sync (CConversation records): its home is the queue + the
  shared mailbox, and its CRM footprint is the Information Request +
  Contact + audit log, not per-record conversation entities.

## 4. What has to change in Google

The good news: almost nothing. The heavy Google lifting (the service
account, domain-wide delegation, `gmail.readonly` + `gmail.send`) was done
for the Communications integration and is already live in production.

1. **Make info@cbmentors.org a REAL user mailbox** (the one required
   change). Admin console → Directory → Users → Add new user, address
   `info@cbmentors.org`. This consumes one Workspace license.
   - **Why a real mailbox:** Gmail API delegation can only impersonate a
     licensed *user*. A Google **Group** or an **alias** cannot be read or
     sent-as through the API — if info@ today is a group or an alias on
     someone's account, that group/alias must be **removed first** so the
     address is free (allow up to ~24 h for the address to release).
   - **History does not migrate.** Mail previously received via a
     group/alias stays where it is (the group archive / members' inboxes).
     The new mailbox — and therefore the queue — sees mail from day one of
     the cutover. If old threads matter, they can be forwarded into the
     new mailbox manually after cutover (each becomes a queue item to
     triage).
   - Nobody needs to log into the account for the API to work. Set a
     strong random password, keep it in the password manager, and treat
     interactive sign-in as an admin fallback (it's also how you'd check
     the spam folder). Turn off any vacation responder / auto-forwarding.
   - If people currently *monitor* info@: after cutover the queue is the
     monitoring. Anyone who still wants raw copies can be given delegate
     access to the mailbox — but replies should go through Submission
     Admin (or the info@ account itself), **never from a personal
     mailbox**, or the submitter sees a personal address and the
     conversation forks out of info@.
2. **Domain-wide delegation: no change.** The existing DWD row (client id
   `109317126943210877831`) applies to every user in the domain — the new
   mailbox is covered automatically. No new scopes: inbound + outbound use
   the same `gmail.readonly` + `gmail.send` already authorized.
3. **Google Cloud console: no change.** The Gmail API is already enabled in
   project `espcrm-498315`.

**Related but NOT Google:** CRM-direct emails currently go out with the
**espo@cbmentors.org** return address (with the user's display name). That
is EspoCRM's own outbound SMTP / system email account configuration
(EspoCRM Administration → Outbound Emails / Group Email Accounts), and
Doug's ruling is to end it — a CRM-side change, independent of this app.

## 5. The rest of the activation (app + CRM)

| Step | Where | What |
|---|---|---|
| 1 | Google | info@ as a real mailbox (section 4) — **do this first** |
| 2 | Overlays (`doctl apps update`) | `OPS_MAILBOX=info@cbmentors.org` on **web AND worker** (optionally `OPS_MAILBOX_NAME`, `OPS_INBOUND_SECONDS`); the pre-deploy migrate job applies migration 0013 automatically |
| 3 | EspoCRM (Entity Manager) | Add an **"Email"** option to `CIntakeSubmission.form` — the audit log for approved email submissions writes `form="Email"`; until it exists that best-effort write logs a WARNING and the rest works |
| 4 | EspoCRM (Admin) | The espo@ outbound-address fix (section 4, "Related but NOT Google") |

Until step 2, the app runs the legacy mode unchanged (per-admin mailboxes,
no inbound capture) — activation is a config change, not a deploy.

## 6. First live verification (15 minutes)

1. Email info@cbmentors.org from a personal account → within a poll cycle a
   **held review / info-email** row appears in Submission Admin with the
   right name, subject, and message.
2. **Approve** it → worker delivers → Contact + Information Request in the
   CRM (source "Email"), deep links on the Details tab.
3. **Reply from the submission page** → arrives from "Cleveland Business Mentors
   <info@cbmentors.org>"; the conversation shows it; a second admin opens
   the same submission and sees the identical conversation.
4. Reply from the personal account → no new queue item; the message joins
   the conversation; the Reply column reads "↳ reply owed".
5. Send a **Discard** case: a junk email → Discard → confirm nothing was
   created in the CRM.
6. Fill the website info-request form, then "Email the submitter" from its
   row → template pre-applied, send, reply — same anchoring behavior.
