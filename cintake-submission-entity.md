# CIntakeSubmission — CRM log of every intake submission

The intake app writes a **`CIntakeSubmission`** record for **every** web
submission (all three forms), so admins have an audit trail of exactly what was
submitted — the processed Account/Contact/profile records are transformed
(phone normalized, multi-selects collapsed, fields dropped) — and a basis for
inbound-form analytics. The `reason` says why each was written:

- **`Normal`** — processed into CRM records (status `Processed`). The log.
- **`Honeypot`** — held: tripped the spam honeypot (status `New`). Review queue.
- **`OrchestratorError`** — the CRM write failed partway (status `New`). Review queue.

So the **review queue** is `status = New` (Honeypot + OrchestratorError); the
rest is the inbound log. The app writes create-only, *after* the outcome is
known (no edit grant needed).

**Status:** modeled in the **V2 system** (engagement `CBM` / `ENG-002`) as
entity **`ENT-015` "Intake Submission"**, fields `FLD-215..221`. Deployed to
crm-test as `CIntakeSubmission` via the v1 crmbuilder deploy (program
`ClevelandBusinessMentors/programs/MN-IntakeSubmission.yaml`). The v1.0 deploy
(entity + form/reason/submitterEmail/status/description) is live; **v1.1 adds
the `source` field, the `Normal` reason option, and the `contact` link — re-run
the deploy to apply.** Until a field/link exists in crm-test the app's write
fails on it and falls back to logging the payload at WARNING (deploying the app
never blocks on the CRM build).

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
| `createdAt` | datetime | Native. The submission time, used for over-time analytics (no separate field needed). |
| `form` | enum | Which form. Options: `client-intake`, `volunteer`, `info-request`. |
| `reason` | enum | Why written. Options: `Normal`, `Honeypot`, `OrchestratorError`. |
| `submitterEmail` | email | The submitter's email, for scanning / dedupe. |
| `status` | enum | Review state. Options: `New`, `Approved`, `Rejected`, `Processed`. `Normal` → `Processed`; held → `New`. |
| `source` | varchar | How the submitter heard about CBM (`how_did_you_hear`), for source analytics. |
| `description` | text | Human note plus the raw submission JSON (honeypot field cleared; reprocess steps for held records). |
| `contact` | link (manyToOne → Contact) | The Contact this submission produced; set on `Normal`. Enables verification + conversion analytics. |

Standard `assignedUser` / `teams` links come for free on a `Base`-type entity.

## API-user permission

Grant the dedicated intake API user **create** on `CIntakeSubmission` (same
create-only pattern as Account / Contact / CClientProfile / CEngagement) — done
2026-06-14. The app only ever *creates* these records; admins
edit/reject/delete them in the UI. No `edit` grant is needed (the app never
updates a record).

## Alerting (CRM-owned)

The app deliberately sends no alert — it is configured in EspoCRM so it is
visible and changeable by admins. crm-test has the Advanced Pack **Workflow
Manager** (verified 2026-06-14), so a single Workflow does it; full BPM is not
needed. The app does not set `assignedUser`/`teams` (the create-only API user
"customapps" has no user directory), so routing must come from the Workflow,
not the app payload — and do **not** notify "Created By" / "Followers" (that is
the API user).

**Two review reasons** trigger this alert (both are non-`Normal`, so both are
captured by the one condition below):
- **`Honeypot`** — the submission tripped the spam guard but passed all other
  validation. Usually a real person; process it without contacting them.
- **`OrchestratorError`** — the CRM write failed partway, so records may be
  missing/orphaned. The `description` holds the reprocess-ready payload.

**Relationship to V2 (`prds/v2`):** with V2 live, the durable submission store
and the **`/ops`** console are the primary place to see and *re-drive* failed
deliveries, and the worker raises its own alerts on delivery backlog/failures.
This CRM Workflow is complementary: it pings staff the moment a **held**
(`Honeypot`) or **errored** (`OrchestratorError`) `CIntakeSubmission` lands, so
the CRM remains a self-contained review queue. The email body is reason-aware so
it reads correctly for either case.

### Step 1 — Email Template (Administration → Email Templates)

- **Name:** `CIntakeSubmission New — Admin Alert`
- **Type:** Email · **Entity Type:** `CIntakeSubmission`
- **Subject:** `Intake submission needs review — {{form}} ({{reason}})`
- **Body:**
  ```
  A web intake submission needs review (reason: {{reason}}).

    • Honeypot          — tripped the spam guard but passed all other
                          validation; usually a real person. Process it
                          without contacting them.
    • OrchestratorError — the CRM write failed partway; some records may be
                          missing or orphaned. The payload below is
                          reprocess-ready.

  Form:      {{form}}
  Reason:    {{reason}}
  Submitter: {{submitterEmail}}
  Status:    {{status}}

  {{description}}

  Open in CRM: {{config.siteUrl}}/#CIntakeSubmission/view/{{id}}
  ```
  (`description` already contains the reprocess-ready JSON + instructions the
  app wrote. If `{{config.siteUrl}}` doesn't resolve in your version, hardcode
  `https://crm-test.clevelandbusinessmentors.org`.)

### Step 2 — Workflow (Administration → Workflows)

- **Name:** `CIntakeSubmission — notify on new submission`
- **Target Entity:** `CIntakeSubmission` · **Active:** yes
- **Trigger Type:** **After record created**
- **Conditions (required):** `reason != Normal` (equivalently `status = New`).
  The app logs *every* submission, and most are `Normal` (status `Processed`) —
  alerting on those would be constant noise. Only the review items (`Honeypot`,
  `OrchestratorError`) should ping anyone.
- **Actions:**
  1. **Send Email** — Template `CIntakeSubmission New — Admin Alert`; **To** =
     *Specified* (a shared/admin address, e.g. an intake-review distro) **or**
     *Team Users* of the admin team; **From** = system outbound address.
  2. *(recommended)* **Create Notification** — to the admin Team/users:
     `New intake submission held for review: {{name}}`. This is the in-app bell
     alert and needs no SMTP — a good fallback if outbound email isn't set up.
  3. *(optional)* **Update Target Record** → set `teams`/`assignedUser` to the
     admin team so it shows in their list/Kanban (Kanban groups on `status`).

### Gotchas

- **Send Email needs outbound SMTP** configured (Administration → Outbound
  Emails). If that's not set, rely on action 2 (Create Notification).
- Placeholders are `{{fieldName}}` for the record's own fields.
- For an at-a-glance queue, add a saved filter / list-view dashlet on
  `CIntakeSubmission` where `status = New`.

## Processing a valid submission

If an admin decides a held record is a real person, the `description` field
contains the original submission as JSON with the honeypot field cleared.
Re-POST that JSON to `/api/<form>/intake` (Content-Type: application/json) to
create the real records — honeypot hits never populate the app's idempotency
cache, so the original `submission_token` still processes. Then set `status`
to `Processed`. Spam is set to `Rejected` (or deleted).

## Retention / PII

These records duplicate submitter PII that also lives on the Contact/Account.
Set a retention rule so it doesn't accumulate indefinitely — e.g. periodically
delete `Rejected` records and `Normal` records older than N months (the Contact
remains the system of record). The `contact` link lets you keep the analytics
(counts) while pruning the raw payloads if desired.

## App-side references

- `core/submission_log.py` — builds and writes the record (entity/field names
  are the `S_*` constants there; keep them in sync with this file).
- `core/app.py` — the handler writes one per submission: `Normal` on success
  (linked to the Contact), `OrchestratorError` on a CRM failure, `Honeypot` on
  a honeypot hit.
