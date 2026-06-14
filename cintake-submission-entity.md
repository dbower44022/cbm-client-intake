# CIntakeSubmission — CRM holding entity for held intake submissions

The intake app holds a submission for admin review (instead of dropping it)
when it trips the spam honeypot — a guard against a real submission being lost
to a false positive (e.g. browser autofill). The held submission is written to
the CRM as a **`CIntakeSubmission`** record, so it is visible to every admin
and the CRM (not the app) owns alerting.

This file is the contract the **CRM team** builds to. Until the entity and the
API user's create grant exist, the app's write fails and it falls back to
logging the full payload at WARNING (so nothing is silently lost, and
deploying the app never blocks on this build).

## Entity

- **Name:** `CIntakeSubmission` (custom object entity; show in the navbar so
  admins can find the queue).

## Fields

| Field | Type | Notes |
|---|---|---|
| `name` | varchar | Record label. The app sets `"<form> — <email> — <YYYY-MM-DD>"`. |
| `cForm` | enum | Which form. Options: `client-intake`, `volunteer`, `info-request`. |
| `cReason` | enum | Why it was held. Options: `Honeypot`, `OrchestratorError` (reserved for a future use; only `Honeypot` is written today). |
| `cSubmitterEmail` | varchar | The submitter's email, for quick scanning / dedupe. |
| `cStatus` | enum | Review state. Options: `New`, `Approved`, `Rejected`, `Processed`. Default `New`. The app always writes `New`; admins advance it. |
| `description` | text | A human-readable note plus the full **reprocess-ready** JSON payload (honeypot field already cleared). |

Standard `assignedUser` / `teams` links should be enabled for routing.

## API-user permission

Grant the dedicated intake API user **create** on `CIntakeSubmission` (same
create-only pattern as Account / Contact / CClientProfile / CEngagement). The
app only ever *creates* these records; admins edit/reject/delete them in the
UI.

## Alerting (CRM-owned)

The app deliberately does not send any alert — that is configured here so it is
visible and changeable by admins:

- **Recommended:** a Workflow (or BPM flow) **on `CIntakeSubmission` create**
  that emails the admin team and/or assigns the record to a team. This is the
  "the CRM sends the alert" path.
- The app does not set `assignedUser` (the create-only API user has no user
  directory), so assignment-based notifications must come from the workflow /
  a default-team rule, not from the app payload.

## Processing a valid submission

If an admin decides a held record is a real person, the `description` field
contains the original submission as JSON with the honeypot field cleared.
Re-POST that JSON to `/api/<cForm>/intake` (Content-Type: application/json) to
create the real records — honeypot hits never populate the app's idempotency
cache, so the original `submission_token` still processes. Then set `cStatus`
to `Processed`. Spam is set to `Rejected` (or deleted).

## App-side references

- `core/quarantine.py` — builds and writes the record (entity/field names are
  the `Q_*` constants there; keep them in sync with this file).
- `core/app.py` — the honeypot branch that calls it.
