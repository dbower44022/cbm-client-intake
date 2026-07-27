# CIntakeSubmission redesign — CRM build handoff

*Approved by Doug 2026-07-27. Design record: `prds/intake-receipt-redesign-plan.md`.
This supersedes the `reason`/`status` field model in
`cintake-submission-entity.md` (that doc now carries a supersede banner; its
entity/`form`/`submitterEmail`/`source`/`contact` sections remain accurate).*

**What this achieves:** every arrival (all five web forms AND every email to
info@) gets one `CIntakeSubmission` receipt in the CRM, updated as it moves
through processing, with the human disposition (who / when / why) recorded on
it — the CRM as the auditable single source of truth. The confusing
`reason` + `status` pair is replaced by ONE `intakeStatus` field and then
deleted.

Build on **crm-test first**, verify with the app, then **prod**. All work is
in **Administration → Entity Manager → Intake Submission → Fields** unless
stated otherwise.

> **STATUS 2026-07-27: DEPLOYED AND CONVERGED ON BOTH ENVIRONMENTS**
> (v0.181.0 + the v0.182.1 dangling-contact fix). Fields built on both CRMs
> (Doug); both environments' edit grants proven live. The reconciliation
> sweep converged everything on its own at first boot (the console migration
> dry-runs then found **nothing left to do** — crm-test 63 receipts current,
> prod 102); post-fix sweeps report **0 failed** on both (crm-test 38 rows,
> prod 112 — prod: 96 Completed / 4 Held-Email / 1 Discarded / 1 Error,
> GET-verified). **Remaining (Doug, tracked in OPEN-ITEMS.md):** delete
> `reason`/`status` in Entity Manager (§6, both CRMs); the §7 live pass;
> delete the ZZTEST probe receipt `6a66f5b4bbe3805ee` (crm-test).

---

## 1. Fields to CREATE

Custom fields on a custom entity: plain camelCase api-names, no `c` prefix.

| # | Field (api-name) | Type | Settings |
|---|---|---|---|
| 1 | `intakeStatus` | Enum | Options (exact values, exact casing): `Received`, `Completed`, `Held-Spam`, `Held-Email`, `Error`, `Discarded`. Default: `Received`. Required: no (older records are filled by migration). |
| 2 | `intakeMessage` | Text | No default. Plain-language explanation written by the app (spam-trap notice, "All emails need review", or the long Error description). |
| 3 | `payload` | Text | No default. The raw form input (JSON) or, for emails, the email content (From / Subject / Date / body). |
| 4 | `emailLink` | Url | No default. Only set on email receipts — deep link to the original message in the shared info@ mailbox. |
| 5 | `dispositionedBy` | Varchar (150) | The staff user who Approved / Re-drove / Discarded. |
| 6 | `dispositionedAt` | Date-Time | When they did it. |
| 7 | `dispositionReason` | Varchar (255) | Why — the app REQUIRES this on Discard (do not mark it required in the CRM; it is legitimately empty until a disposition happens). |

After creating fields: **Administration → Rebuild.**

## 2. Layouts

**Entity Manager → Intake Submission → Layouts:**

- **Detail:** top panel = `name`, `intakeStatus`, `intakeMessage`, `form`,
  `submitterEmail`, `source`, `contact`, `emailLink`; a second panel
  "Disposition" = `dispositionedBy`, `dispositionedAt`, `dispositionReason`;
  a third panel = `payload` (full width). Remove `reason`, `status`, and
  `description` from the layout now (fields deleted later, §6).
- **List:** `name`, `intakeStatus`, `form`, `submitterEmail`, `createdAt`,
  `dispositionedBy`.
- **Search/filters:** ensure `intakeStatus` and `form` are filterable
  (enum fields are by default).

## 3. Role change — the intake API user needs EDIT

**Administration → Roles → CustomAppAPIRole** (the role on the intake API
user, same name both CRMs): for the **Intake Submission** scope set
**Edit = yes** (Create and Read are already yes). Without this every receipt
UPDATE (outcome, disposition, migration, sweep) fails with a 403.

Reminder from past incidents: verify the change took effect via
**Administration → Users → (the API user) → Access** — that merged table is
the truth about what the user can actually do.

## 4. What the app will write (for reference)

| Moment | Write |
|---|---|
| Web form arrives | CREATE: `intakeStatus=Received` (or `Held-Spam` + message `The <form type> spam trap was triggered`), `payload` = form JSON, plus name/form/submitterEmail/source as today. |
| info@ email captured | CREATE: `intakeStatus=Held-Email`, message `All emails need review`, `payload` = email content, `emailLink` set. |
| Delivery succeeds | UPDATE: `intakeStatus=Completed`, `contact` linked. |
| Delivery fails for good | UPDATE: `intakeStatus=Error`, `intakeMessage` = the long what-happened-and-how-to-fix description. |
| Staff Approve / Re-drive | UPDATE: `dispositionedBy/At` (+ optional reason); status then follows delivery (`Received` → `Completed`/`Error`). |
| Staff Discard | UPDATE: `intakeStatus=Discarded`, `dispositionedBy/At`, `dispositionReason` (always present — the app refuses a reasonless discard). |

The app never writes `reason`/`status`/`description` again. Only humans ever
produce `Discarded`; every other value is app-written — that distinction is
the audit answer to "was this a person or a software error?"

## 5. Migration of existing records (app-side script; needs §1 + §3 done)

A one-off script (dry-run by default) run per environment; the app team owns
it. What it does, for the CRM team's awareness:

1. `intakeStatus` from `reason`: `Normal`→`Completed`, `Honeypot`→`Held-Spam`,
   `OrchestratorError`→`Error`; `intakeMessage` per the table above;
   `payload` = the JSON block copied out of the old `description`.
2. Back-links each receipt to its app-store row (via the submission token in
   the stored JSON) so the reconciliation sweep never creates duplicates.
3. Receipts whose app-store row was already discarded get
   `intakeStatus=Discarded` + `dispositionedBy` = the stored actor,
   `dispositionReason` = `migrated — predates disposition reasons`.

## 6. Field DELETION (only after §5 is verified on that environment)

**Entity Manager → Intake Submission → Fields:** delete **`reason`** and
**`status`**. (Historical values are fully captured in `intakeStatus` by the
migration; nothing is lost.) `description` is NOT deleted — historical
records keep theirs; the app just stops writing it. Rebuild after deleting.

If the planned alert-on-create workflow (old doc §Alerting) is ever built, it
keys on `intakeStatus` in (`Held-Spam`, `Held-Email`, `Error`) — not on the
deleted `reason`.

## 7. Verification (per environment, after the app deploys)

1. Submit a test web form → a receipt appears at `Received` then flips to
   `Completed` with the Contact linked; `payload` holds the form JSON.
2. Submit with the spam trap filled (POST with `company_url` set) →
   `Held-Spam` + the spam-trap message; Re-drive in Submission Admin →
   `Completed` + disposition stamps.
3. Send an outside email to info@ → within the poll interval a `Held-Email`
   receipt exists with the email content in `payload` and a working
   `emailLink` — BEFORE anyone touches it. Approve → same record reaches
   `Completed`. Send another and Discard with a reason → `Discarded` +
   who/when/why on the record.
4. Force a delivery failure (e.g. an invalid enum via direct POST) →
   `Error` with a readable, specific `intakeMessage`.
5. Break the CRM write once (or just pick a receipt and blank a field by
   hand) → the hourly sweep (or the manual "Sync receipts" action) heals it;
   the drift count shows in the admin alert metrics.
6. Confirm the old `reason`/`status` columns are gone and Submission Admin's
   Status column shows only the new vocabulary.
