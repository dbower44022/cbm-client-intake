# CIntakeSubmission — CRM holding entity for held intake submissions

The intake app holds a submission for admin review (instead of dropping it)
when it trips the spam honeypot — a guard against a real submission being lost
to a false positive (e.g. browser autofill). The held submission is written to
the CRM as a **`CIntakeSubmission`** record, so it is visible to every admin
and the CRM (not the app) owns alerting.

**Status:** modeled in the **V2 system** (engagement `CBM` / `ENG-002`) as
entity **`ENT-015` "Intake Submission"** with fields `FLD-215..219`, all
`candidate` (matching the other CBM entities). The remaining step is the
downstream **deploy to crm-test** — V2 is the upstream model and does not push
to EspoCRM itself; the entity is created in EspoCRM via the v1 crmbuilder
deploy or the EspoCRM admin UI. Until it exists in crm-test, the app's write
fails and it falls back to logging the full payload at WARNING (so nothing is
silently lost, and deploying the app never blocks on this).

## Entity

- **V2 name:** `Intake Submission` (natural label, `ENT-015`); **EspoCRM
  name:** `CIntakeSubmission` (EspoCRM adds the `C` prefix to custom entities).
  Custom object entity; show in the navbar so admins can find the queue.

## Fields

EspoCRM field api-names (custom fields on a custom entity are plain camelCase —
**no `c` prefix**, unlike custom fields on native Account/Contact):

| Field (api-name) | Type | Notes |
|---|---|---|
| `name` | varchar | Native record label. The app sets `"<form> — <email> — <YYYY-MM-DD>"`. |
| `form` | enum | Which form. Options: `client-intake`, `volunteer`, `info-request`. |
| `reason` | enum | Why it was held. Options: `Honeypot`, `OrchestratorError` (reserved for future use; only `Honeypot` is written today). |
| `submitterEmail` | email | The submitter's email, for quick scanning / dedupe. |
| `status` | enum | Review state. Options: `New`, `Approved`, `Rejected`, `Processed`. Default `New`. The app always writes `New`; admins advance it. |
| `description` | text | A human-readable note plus the full **reprocess-ready** JSON payload (honeypot field already cleared). |

Standard `assignedUser` / `teams` links come for free on a `Base`-type entity.

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
Re-POST that JSON to `/api/<form>/intake` (Content-Type: application/json) to
create the real records — honeypot hits never populate the app's idempotency
cache, so the original `submission_token` still processes. Then set `status`
to `Processed`. Spam is set to `Rejected` (or deleted).

## App-side references

- `core/quarantine.py` — builds and writes the record (entity/field names are
  the `Q_*` constants there; keep them in sync with this file).
- `core/app.py` — the honeypot branch that calls it.
