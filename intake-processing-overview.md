# Intake processing — the end-to-end overview

*What happens to every submission, which CRM records each form creates, what
status each record starts with, and where staff work each kind of intake.
Written 2026-07-24 from Doug's walkthrough request; statuses verified against
the orchestrator code. Plain language; per-tool detail lives in the
functional references this links to.*

## The pipeline every submission goes through

1. **Capture.** The submission is written to the app's own Postgres database
   before anything else happens — nothing is lost if the CRM is down. This
   row carries the machine **delivery status** shown in Submission Admin:
   `pending` → `processing` → `completed`, with `retry` /
   `needs_attention` / `held_honeypot` / `held_review` / `discarded` for
   trouble. Delivery status is not hand-editable; Re-drive and Discard are
   its only controls.
2. **Delivery.** The background worker claims the row and runs that form's
   orchestrator, creating the CRM records below. Delivery is resumable and
   idempotent — a retry never duplicates records.
3. **Audit log.** Every delivery also writes a **CIntakeSubmission** record
   in the CRM — for all five forms and for email-originated submissions,
   success or failure:
   - `reason` — **Normal** (delivered), **Honeypot** (bot trap), or
     **OrchestratorError** (the CRM writes failed)
   - `status` — **Processed** for Normal; **New** for Honeypot /
     OrchestratorError (New is the CRM-side review marker)
4. **Queue disposition.** In Submission Admin, a **record-creating**
   submission (client intake, volunteer, partner, sponsor) **closes itself**
   on successful delivery with the system reason **"Process completed"** —
   the downstream admin team owns it from there. **Information requests**
   (web form or email to info@) stay **open** until staff close them with a
   reason; the grid's State column (Reply owed / Waiting on them / In
   progress / New / Closed) is derived from the conversation and staff
   activity, and a submitter replying after a Close auto-reopens the item.

So a healthy submission always ends as: app row `completed` +
CIntakeSubmission `Normal / Processed` + the form's own records (below).

## What each form creates, and where it gets worked

| Form | CRM records created | Starting status | Worked in |
|---|---|---|---|
| **client-intake** | Account (`cAccountType=["Client"]`) → Contact → CClientProfile → **CEngagement** | CEngagement `engagementStatus = "Submitted"` | **Client Administration** — the grid's default filter is the action-needed set (Submitted + Assignment Declined + Assignment Dormant); assigning a mentor moves it to Pending Acceptance |
| **volunteer** (mentor) | Contact (`cContactType=["Mentor"]`) → **CMentorProfile** | CMentorProfile `mentorStatus = "Candidate"` | **Mentor Administration** — approval flips the status and provisions the @cbmentors.org login |
| **info-request** | Contact (`["Prospect"]`), Account (`cClientStatus="Prospect"`) only when a company was given, + **CInformationRequest** | CInformationRequest `requestStatus = "New"` | **Submission Admin** — reply from the shared info@ identity; **Close with a reason** sets the CRM record's `requestStatus` to Closed too |
| **partner** | Account (`["Partner"]`) → Contact (`["Partner"]`) → **CPartnerProfile** (stamped with the Partner Management Team) | CPartnerProfile `partnershipStatus = "Candidate"` | **Partner Management** — the grid lists all partners; candidates are reviewed there and in the CRM |
| **sponsor** (funder) | Account (`["Donor/Sponsor"]`) → Contact (`["Sponsor"]`) → **CSponsorProfile** (stamped with the Sponsor Management Team) | No status field — the message lands in the profile's `description` | **Funder Management** — same review path as partners |
| **info-email** (mail to info@) | Held in Submission Admin (`held_review`) until staff **Approve** — then the info-request records above, with `source="Email"` | Same as info-request once approved | **Submission Admin** — Approve creates the records, Discard is the spam button (no CRM residue) |

A repeat submitter is matched by email: the existing Contact is reused (empty
fields back-filled, never overwritten), and an info-request appends its
message to the existing Contact's description.

**The partner/funder review path is deliberate and long-term** (Doug's ruling
2026-07-22): unlike clients (assignment queue) and mentors (approval screen),
partner and funder candidates have no dedicated approval tool — the Partner /
Funder Management grids plus the CRM **are** the intended review surface.

## Why one information request has three "statuses"

- **App submission row** — Submission Admin's delivery state: `completed`
  means "reached the CRM." Machine-managed.
- **CIntakeSubmission** — the CRM audit record: `Normal / Processed`. A log
  entry; nobody works it (its New/reason values feed the CRM-side alerting
  on honeypot/orchestrator holds).
- **CInformationRequest** — the workable record: starts `New`, and closing
  the item in Submission Admin sets it to `Closed` so the queue and the CRM
  never drift.

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
