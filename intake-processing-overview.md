# Intake processing — the end-to-end overview

*What happens to every submission, which CRM records each form creates, what
status each record starts with, and where staff work each kind of intake.
Written 2026-07-24 from Doug's walkthrough request; statuses verified against
the orchestrator code. Plain language; per-tool detail lives in the
functional references this links to.*

*Prefer a picture? **`intake-processing-flow.drawio`** (repo root; open in
draw.io / diagrams.net) diagrams the same material in plain language — one
tab per input source (the five forms + inbound info@ email), the shared
journey every form takes, and a "Start here" tab with the one status
vocabulary both Submission Admin and the CRM receipt speak.*

## The pipeline every submission goes through

1. **Capture.** The submission is written to the app's own Postgres database
   before anything else happens — nothing is lost if the CRM is down.
2. **The CRM receipt.** Every arrival gets an **Intake Submission receipt in
   EspoCRM** — created at capture and updated as things change (the
   intake-receipt redesign, 2026-07-27). One status vocabulary, used by the
   receipt AND every Submission Admin screen: **Received** (in hand, being
   processed — covers waiting/delivering/retrying) → **Completed** (all
   records created), with **Held-Spam** (bot trap), **Held-Email** (an info@
   email awaiting triage), **Error** (delivery failed; the receipt's message
   says exactly what happened and how to fix it), and **Discarded** (a
   person decided against it — with who/when/why stamped on the receipt).
   The receipt also carries the raw submitted content (for emails, the
   message itself + a Gmail link) and links the Contact once Completed. An
   hourly reconciliation sweep — plus the **Sync receipts** button in
   Submission Admin — guarantees the CRM matches reality even if a write
   failed at the time.
3. **Delivery.** The background worker claims the row and runs that form's
   orchestrator, creating the CRM records below. Delivery is resumable and
   idempotent — a retry never duplicates records.
4. **Queue disposition.** In Submission Admin, a **record-creating**
   submission (client intake, volunteer, partner, sponsor) **closes itself**
   on successful delivery with the system reason **"Process completed"** —
   the downstream admin team owns it from there. **Information requests**
   (web form or email to info@) stay **open** until staff close them with a
   reason; the grid's State column (Reply owed / Waiting on them / In
   progress / New / Closed) is derived from the conversation and staff
   activity, and a submitter replying after a Close auto-reopens the item.
   **Discarding requires a reason**, recorded on the receipt.

So a healthy submission always ends as: status **Completed** (in the app and
on its CRM receipt, same word) + the form's own records (below).

## What each form creates, and where it gets worked

| Form | CRM records created | Starting status | Worked in |
|---|---|---|---|
| **client-intake** | Account (`cAccountType=["Client"]`) → Contact → CClientProfile → **CEngagement** | CEngagement `engagementStatus = "Submitted"` | **Client Administration** — the grid's default filter is the action-needed set (Submitted + Assignment Declined + Assignment Dormant); assigning a mentor moves it to Pending Acceptance |
| **volunteer** (mentor) | Contact (`cContactType=["Mentor"]`) → **CMentorProfile** | CMentorProfile `mentorStatus = "Candidate"` | **Mentor Administration** — approval flips the status and provisions the @cbmentors.org login |
| **info-request** | Contact (`["Prospect"]`), Account (`cClientStatus="Prospect"`) only when a company was given, + **CInformationRequest** | CInformationRequest `requestStatus = "New"` | **Submission Admin** — reply from the shared info@ identity; **Close with a reason** sets the CRM record's `requestStatus` to Closed too |
| **partner** | Account (`["Partner"]`) → Contact (`["Partner"]`) → **CPartnerProfile** (stamped with the Partner Management Team) | CPartnerProfile `partnershipStatus = "Candidate"` | **Partner Management** — the grid lists all partners; candidates are reviewed there and in the CRM |
| **sponsor** (funder) | Account (`["Donor/Sponsor"]`) → Contact (`["Sponsor"]`) → **CSponsorProfile** (stamped with the Sponsor Management Team) | No status field — the message lands in the profile's `description` | **Funder Management** — same review path as partners |
| **info-email** (mail to info@) | A **Held-Email** receipt in the CRM immediately (the email content + Gmail link); staff **Approve** → the info-request records above, with `source="Email"` | Same as info-request once approved | **Submission Admin** — Approve creates the records; Discard (with a required reason) marks the receipt Discarded and creates nothing else |

A repeat submitter is matched by email: the existing Contact is reused (empty
fields back-filled, never overwritten), and an info-request appends its
message to the existing Contact's description.

**The partner/funder review path is deliberate and long-term** (Doug's ruling
2026-07-22): unlike clients (assignment queue) and mentors (approval screen),
partner and funder candidates have no dedicated approval tool — the Partner /
Funder Management grids plus the CRM **are** the intended review surface.

## The two statuses an information request carries

- **Intake Status** — how processing went (Received → Completed, or one of
  Held-Spam / Held-Email / Error / Discarded). Same word in Submission Admin
  and on the CRM receipt; machine-managed (staff act on it via Re-drive /
  Approve / Discard, never edit it directly).
- **Request Status** (on **CInformationRequest**, the workable record) — the
  conversation: starts `New`, and closing the item in Submission Admin sets
  it to `Closed` so the queue and the CRM never drift.

## Related references

- [`submission-admin.md`](submission-admin.md) — the Submission Admin
  workspace itself (State column, Discussion/Activity, Close reasons,
  the info@ conversation).
- [`email-management.md`](email-management.md) — the whole email system;
  [`submission-email-flow.md`](submission-email-flow.md) — the submission
  email lifecycles.
- [`mentor-administration.md`](mentor-administration.md) — mentor approval +
  record completeness.
- `cintake-submission-entity.md` / `cinformation-request-entity.md` — the
  CRM entity specs behind the audit log and the information request.
